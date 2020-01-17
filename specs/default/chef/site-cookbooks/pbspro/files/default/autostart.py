# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
#
import logging_init  # import first to ensure other modules (requests) don't define logging.basicConfig first

import collections
import json
import os
import sys
import traceback

from cyclecloud import machine, clustersapi, autoscale_util, autoscaler as autoscalerlib,\
    nodearrays
from cyclecloud.autoscale_util import Record
import cyclecloud.config
from cyclecloud.job import Job, PackingStrategy
import mockpbs
import pbs_driver
from pbscc import InvalidSizeExpressionError
import pbscc
from copy import deepcopy
import numbers


class PBSAutostart:
    '''
    1) Converts existing pbsnodes into cyclecloud.machine.Machine instances
    2) Performs a 'true up' of the machine instances reported by the autoscale lib vs the machines discovered in step 1) using InstanceId.
    3) Converts PBS jobs into cyclecloud.job.Job instances.
    4) Uses the current state of the cluster (steps 1 and 2) to construct a cyclecloud.autoscaler.Autoscaler instance.
    5) Feeds in jobs from step 3) into the Autoscaler, which performs a demand calculation of exactly which new machines are needed and which are idle.
    6) Does a soft shutdown of idle nodes - first it sets them offline - `pbsnodes -o` - then, on subsequent iterations, if no jobs running on the node it
       performs a shutdown.
       
       
       To disable
       sudo qmgr -c 'set hook autoscale enabled=false'
    
    '''
    
    def __init__(self, driver, clusters_api, cc_config, clock=None):
        self.cc_config = cc_config
        self.disable_grouping = cc_config.get("cyclecloud.cluster.autoscale.use_node_groups", True) is not True
        self.driver = driver
        self.clusters_api = clusters_api
        self.clock = clock or Clock()
        self.default_placement_attrs = self.cc_config.get("cyclecloud.placement_group.defaults", {"group_id": "single"})
        
    def query_jobs(self):
        '''
            Converts PBS jobs into cyclecloud.job.Job instances. It will also compress jobs that have the exact same requirements.
        '''
        scheduler_config = self.driver.scheduler_config()
        scheduler_resources = [] + scheduler_config["resources"]
        # special case for hostname so we can automatically place jobs onto the appropriate host
        scheduler_resources.append("hostname")
        scheduler_resources.append("instance_id")
        
        group_jobs = not self.disable_grouping
        running_autoscale_jobs = []
        idle_autoscale_jobs = []
    
        # get the raw string outputs first, and convert it second. This somewhat limits the
        # race condition of asking the status of the queue twice.
        running_raw_jobs_str, running_converter = self.driver.running_jobs()
        queued_raw_jobs_str, queued_converter = self.driver.queued_jobs()
        queued_raw_arr_obs_str, queued_arr_converter = self.driver.queued_array_jobs()
        
        running_raw_jobs = running_converter(running_raw_jobs_str)
        # ignore any array jobs in here - this returns only idle array jobs that haven't started a single task.
        # so instead, in our next call we will get all job arrays and just ignore those with Queued:0 in array state count.
        queued_raw_single_jobs = [x for x in queued_converter(queued_raw_jobs_str) if not x.get("array")]
        queued_raw_arr_jobs = queued_arr_converter(queued_raw_arr_obs_str)
        
        def sort_by_job_id(raw_job):
            job_id = raw_job.get("job_id")
            if not job_id:
                return -1
            for i in range(len(job_id)):
                if not job_id[i].isdigit():
                    break
            
            return int(job_id[:i])
        
        queued_raw_jobs = sorted(queued_raw_single_jobs + queued_raw_arr_jobs, key=sort_by_job_id)
        raw_jobs = []
        
        for raw_job in running_raw_jobs:
            # it is only running on a single node
            if '+' not in raw_job["exec_vnode"]:
                raw_jobs.append(raw_job)
                continue
            
            for vnode in raw_job["exec_vnode"].split("+"):
                sub_raw_job = deepcopy(raw_job)
                sub_raw_job["exec_vnode"] = vnode
                raw_jobs.append(sub_raw_job)
        
        for raw_job in queued_raw_jobs:
            if not raw_job["resource_list"].get("select"):
                raw_jobs.append(raw_job)
            else:
                # pbspro, like many schedulers, allows a varying set requirements for nodes in a single submission.
                # we will break it apart here as if they had split them individually.
                
                place = raw_job["resource_list"].get("place")
                slot_type = raw_job["resource_list"].get("slot_type")

                chunks = pbscc.parse_select(raw_job)
                for n, chunk in enumerate(chunks):
                    # only pay the penalty of copies when we actually have multi-chunk jobs
                    sub_raw_job = deepcopy(raw_job)

                    if len(chunks) > 1:
                        sub_raw_job["job_id"] = "%s.%d" % (sub_raw_job["job_id"], n) 
                    
                    sub_raw_job["resource_list"] = {}
                    if place:
                        sub_raw_job["resource_list"]["place"] = place
                        
                    if slot_type:
                        sub_raw_job["resource_list"]["slot_type"] = slot_type
                        
                    sub_raw_job["resource_list"]["select"] = pbscc.format_select(chunk)
                    chunk["nodect"] = int(chunk["select"])
                    if "ncpus" not in chunk:
                        chunk["ncpus"] = "1"
                    
                    for key, value in chunk.iteritems():
                        if key not in ["select", "nodect"]:
                            try:
                                value = pbscc.parse_gb_size(key, value) * chunk["nodect"]
                            except InvalidSizeExpressionError:
                                pass
                            
                            sub_raw_job["resource_list"][key] = value
                    
                    sub_raw_job["nodect"] = sub_raw_job["resource_list"]["nodect"] = chunk["nodect"]
                    raw_jobs.append(sub_raw_job)
        
        warnings = set()
        raw_jobs = [x for x in raw_jobs if x["job_state"].upper() in [pbscc.JOB_STATE_QUEUED,
                                                                      pbscc.JOB_STATE_RUNNING,
                                                                      pbscc.JOB_STATE_BATCH]]
        
        for raw_job in raw_jobs:
            pbs_job = mockpbs.mock_job(raw_job)
            nodect = int(pbs_job.Resource_List["nodect"])
            
            if pbs_job["job_state"].upper() == pbscc.JOB_STATE_RUNNING:
                # update running job
                live_resources = pbscc.parse_exec_vnode(raw_job["exec_vnode"])
                for key, value in live_resources.iteritems():
                    # live resources are calculated on a per node basis, but the Resource_List is based
                    # on a total basis.
                    # we will normalize this below
                    
                    if isinstance(value, numbers.Number):
                        pbs_job.Resource_List[key] = value * nodect
                    else:
                        pbs_job.Resource_List[key] = value
                pbs_job["executing_hostname"] = live_resources["hostname"]
                
            is_array = bool(pbs_job.get("array", False))
            
            slots_per_job = int(pbs_job.Resource_List['ncpus']) / nodect 
            slot_type = pbs_job.Resource_List["slot_type"]  # can be None, similar to {}.get("key"). It is a pbs class.
            pbscc.info("found slot_type %s." % slot_type)
            
            placement = pbscc.parse_place(pbs_job.Resource_List.get("place"))
                    
            # Note: not sure we will ever support anything but group_id for autoscale purposes.
            # User could pick, say, group=host, which implies an SMP job, not a parallel job.
            
            if placement.get("grouping", "group=group_id") != "group=group_id":
                placement.pop("grouping")

            if placement.get("arrangement", "").lower() in ["scatter", "vscatter"]:
                pack = "scatter"
            else:
                pack = "pack"
            
            exclusive = placement.get("sharing", "").lower() in ["excl", "exclhost"]
            # we may need to support sharing at some point, but it seems that we can ignore it for now.
            _shared = placement.get("sharing") in ["sharing"]
            placeby = placement.get("grouping")
            
            autoscale_job = Job(name=pbs_job["job_id"],
                                nodearray=slot_type,
                                nodes=nodect,
                                packing_strategy=pack,
                                exclusive=exclusive,
                                resources={"ncpus": 0},
                                executing_hostname=pbs_job.get("executing_hostname"))

            if placeby:
                autoscale_job.placeby = placeby.split("=", 1)[-1]
            
            if is_array:
                array_tasks = raw_job["array_state_count"]
                # we only want the remaining number that are queued. The running tasks are handled separately.
                # example: "Queued:6 Running:2 Exiting:0 Expired:0"
                array_count = int(str(array_tasks).split(" ")[0].split(":")[1])
                if array_count == 0:
                    pbscc.debug("Job {} has no remaining tasks. Skipping.".format(raw_job["job_id"]))
                    continue
                # Multiply the number of slots needed by number of tasks in the array
                slots_per_job *= array_count
            else:
                array_count = 1
                    
            # If it's an MPI job and grouping is enabled
            # we want to use a grouped autoscale_job to get tightly coupled nodes

            if group_jobs and placement.get("grouping"): 
                autoscale_job['grouped'] = True
                autoscale_job["nodes"] *= array_count
                autoscale_job.placeby_value = pbs_job.Resource_List.get("group_id") or None
            elif is_array:
                autoscale_job["nodes"] *= array_count

            autoscale_job.ncpus += slots_per_job
            
            for attr, value in pbs_job.Resource_List.iteritems():
                if attr not in scheduler_resources:
                    # if it isn't a scheduler level attribute, don't bother 
                    # considering it for autoscale as the scheduler won't respect it either.
                    continue
                try:
                    value = pbscc.parse_gb_size(attr, value)
                    value = value / nodect
                except InvalidSizeExpressionError:
                    if value.lower() in ["true", "false"]:
                        value = value.lower() == "true"

                autoscale_job.resources[attr] = value
                
            if raw_job["job_state"] == pbscc.JOB_STATE_QUEUED:
                idle_autoscale_jobs.append(autoscale_job)
            else:
                running_autoscale_jobs.append(autoscale_job)
                
        for warning in warnings:
            format_string, values = warning[0], warning[1:]
            pbscc.error(format_string % values)
        
        # leave an option for disabling this in case it causes issues.
        if self.cc_config.get("pbspro.compress_jobs", False):
            all_autoscale_jobs = running_autoscale_jobs + compress_queued_jobs(idle_autoscale_jobs)
        else:
            all_autoscale_jobs = running_autoscale_jobs + idle_autoscale_jobs
            
        return all_autoscale_jobs
    
    def fetch_nodearray_definitions(self):
        '''
            A wrapper around the autoscale library function to parse Configuration.autoscale.* chef attributes and add
            the 'ungrouped' attribute to the machine types.
            
            See cyclecloud.nodearrays.NodearrayDefinitions for more info.
        '''
        nodearray_definitions = machine.fetch_nodearray_definitions(self.clusters_api, self.default_placement_attrs)
        nodearray_definitions.placement_group_optional = True

        filtered_nodearray_definitions = nodearrays.NodearrayDefinitions()
        
        for machinetype in nodearray_definitions:
            if machinetype.get("disabled", False):
                continue
                
            # ensure that any custom attribute the user specified, like disk = 100G, gets parsed correctly
            for key, value in machinetype.iteritems():
                try:
                    machinetype[key] = pbscc.parse_gb_size(key, value)
                except InvalidSizeExpressionError:
                    pass
                
            # kludge: there is a strange bug where ungrouped is showing up as a string and not a boolean.
            if not machinetype.get("group_id"):
                machinetype["ungrouped"] = "true"
                filtered_nodearray_definitions.add_machinetype(machinetype)
            else:
                machinetype["ungrouped"] = "false"
                filtered_nodearray_definitions.add_machinetype_with_placement_group(machinetype.get("group_id"), machinetype)
            
        return filtered_nodearray_definitions
                
    def autoscale(self):
        '''
            The main loop described at the top of this class. 
            Returns machine_requests, idle_machines and total_machines for ease of unit testing.
        '''
        pbscc.info("Begin autoscale cycle")
        
        nodearray_definitions = self.fetch_nodearray_definitions()
        
        pbsnodes_by_hostname, existing_machines, booting_instance_ids, instance_ids_to_shutdown = self.get_existing_machines(nodearray_definitions)
        
        start_enabled = "true" == str(self.cc_config.get("cyclecloud.cluster.autoscale.start_enabled", "true")).lower()
        
        if not start_enabled:
            pbscc.warn("cyclecloud.cluster.autoscale.start_enabled is false, new machines will not be allocated.")
        
        autoscaler = autoscalerlib.Autoscaler(nodearray_definitions, existing_machines, self.default_placement_attrs, start_enabled)
        
        # throttle how many jobs we attempt to match. When pbspro.compress_jobs is true (default) this shouldn't really be an issue
        # unless the user has over $pbspro.max_unmatched_jobs unique sets of requirements.
        max_unmatched_jobs = int(self.cc_config.get("pbspro.max_unmatched_jobs", 10000))
        unmatched_jobs = 0
        
        for job in self.query_jobs():
            if job.executing_hostname:
                try:
                    autoscaler.get_machine(hostname=job.executing_hostname).add_job(job, force=True)
                    continue
                except RuntimeError as e:
                    pbscc.error(str(e))
                    pass
                    
            if not autoscaler.add_job(job):
                unmatched_jobs += 1
                pbscc.info("Can not match job %s." % job.name)
                if max_unmatched_jobs > 0 and unmatched_jobs >= max_unmatched_jobs:
                    pbscc.warn('Maximum number of unmatched jobs reached - %s. To configure this setting, change {"pbspro": "max_unmatched_jobs": N}} in %s' % (unmatched_jobs, pbscc.CONFIG_PATH))
                    break
        
        machine_requests = autoscaler.get_new_machine_requests()
        idle_machines = autoscaler.get_idle_machines()
        
        autoscale_request = autoscale_util.create_autoscale_request(machine_requests)
        for request_set in autoscale_request["sets"]:
            configuration = request_set["nodeAttributes"]["Configuration"]
            
            if "pbspro" not in configuration:
                    configuration["pbspro"] = {}
            
            configuration["pbspro"]["slot_type"] = request_set["nodearray"]
            if not request_set.get("placementGroupId"):
                configuration["pbspro"]["is_grouped"] = False
            else:
                configuration["pbspro"]["is_grouped"] = True
                
        autoscale_util.scale_up(self.clusters_api, autoscale_request)
        
        for r in machine_requests:
            if r.placeby_value:
                pbscc.info("Requesting %d %s machines in placement group %s for nodearray %s" % (r.instancecount, r.machinetype, r.placeby_value, r.nodearray))
            else:
                pbscc.info("Requesting %d %s machines in nodearray %s" % (r.instancecount, r.machinetype, r.nodearray))
        
        if pbscc.is_fine():
            pbscc.fine("New target state of the cluster, including booting nodes:")
            
            for m in autoscaler.machines:
                pbscc.fine("    %s" % str(m))
        
        if instance_ids_to_shutdown:
            pbscc.info("Shutting down instance ids %s" % instance_ids_to_shutdown.keys())
            self.clusters_api.shutdown(instance_ids_to_shutdown.keys())
            
            for hostname in instance_ids_to_shutdown.itervalues():
                pbscc.info("Deleting %s" % hostname)
                self.driver.delete_host(hostname)
        
        now = self.clock.time()
        
        stop_enabled = "true" == str(self.cc_config.get("cyclecloud.cluster.autoscale.stop_enabled", "true")).lower()
        
        if not stop_enabled:
            pbscc.warn("cyclecloud.cluster.autoscale.stop_enabled is false, idle machines will not be terminated")
        
        if stop_enabled:
            idle_before_threshold = float(self.cc_config.get("cyclecloud.cluster.autoscale.idle_time_before_jobs", 3600))
            idle_after_threshold = float(self.cc_config.get("cyclecloud.cluster.autoscale.idle_time_after_jobs", 300))
        
            for m in idle_machines:
                if m.get_attr("keep_alive", False):
                    pbscc.debug("Ignoring %s for scaledown because KeepAlive=true", m.hostname)
                    continue
                
                if m.get_attr("instance_id", "") not in booting_instance_ids:
                    pbscc.debug("Could not find instance id in CycleCloud %s" % m.get_attr("instance_id", ""))
                    continue
                
                pbsnode = pbsnodes_by_hostname.get(m.hostname)
                
                # the machine may not have converged yet, so
                if pbsnode:
                    if "busy" in pbsnode["state"]:
                        if "down" in pbsnode["state"]:
                            pbscc.warn("WARNING: %s is down but busy with jobs %s", m.hostname, pbsnode.get("jobs", []))
                        else:
                            pbscc.error("WARNING: Falsely determined that %s is idle!" % m.hostname)
                        continue
                    
                    last_state_change_time = pbsnode["last_state_change_time"]
                    last_used_time = pbsnode.get("last_used_time")
                    if last_used_time:
                        # last_used_time can be stale while a job is exiting, e.g. last_state_change_time could be < 5 minutes but
                        # somehow last_used_time > 5 minutes, causing us to prematurely terminate the node just because a job took a long time
                        # to exit.
                        last_used_time = max(last_state_change_time, last_used_time)
                    else:
                        last_used_time = self.clock.time()

                    if now - last_used_time > idle_after_threshold:
                        pbscc.info("Setting %s offline after %s seconds" % (m.hostname, now - last_used_time))
                        self.driver.set_offline(m.hostname)
                    elif now - last_state_change_time > idle_before_threshold:
                        pbscc.info("Setting %s offline after %s seconds" % (m.hostname, now - last_state_change_time))
                        self.driver.set_offline(m.hostname)
        
        pbscc.info("End autoscale cycle")
        # returned for testing purposes
        return machine_requests, idle_machines, autoscaler.machines
    
    def get_existing_machines(self, nodearray_definitions):
        '''
            Queries pbsnodes and CycleCloud to get a sane set of cyclecloud.machine.Machine instances that represent the current state of the cluster.
        '''
        pbsnodes = self.driver.pbsnodes().get(None)
        existing_machines = []
        
        booting_instance_ids = autoscale_util.nodes_by_instance_id(self.clusters_api, nodearray_definitions)
        
        instance_ids_to_shutdown = Record()
        
        nodes_by_instance_id = Record()
        
        for pbsnode in pbsnodes.values():
            instance_id = pbsnode["resources_available"].get("instance_id", "")
            # use this opportunity to set some things that can change during the runtime (keepalive) or are not always set
            # by previous versions (machinetype/nodearray)
            if instance_id and booting_instance_ids.get(instance_id):
                node = booting_instance_ids.get(instance_id)
                pbsnode["resources_available"]["keep_alive"] = node.get("KeepAlive", False)
                pbsnode["resources_available"]["machinetype"] = pbsnode["resources_available"].get("machinetype") or node.get("MachineType")
                pbsnode["resources_available"]["nodearray"] = pbsnode["resources_available"].get("nodearray") or node.get("Template")
                
            inst = self.process_pbsnode(pbsnode, instance_ids_to_shutdown, nodearray_definitions)
            if not inst:
                continue
            existing_machines.append(inst)
            
            # we found the pbsnode that matches the cyclecloud node, so let's remove the duplicate 
            instance_id = inst.get_attr("instance_id", "")
            if instance_id in booting_instance_ids:
                booting_instance_ids.pop(instance_id)
            nodes_by_instance_id[instance_id] = pbsnode
        
        for instance_id, node in list(booting_instance_ids.iteritems()):
            nodearray_name = node["Template"]
            machinetype_name = node["MachineType"]
            
            try:
                machinetype = nodearray_definitions.get_machinetype(nodearray_name, machinetype_name, node.get("PlacementGroupId"))
            except KeyError as e:
                raise ValueError("machine is %s, key is %s, rest is %s" % (nodearray_name, str(e), nodearray_definitions))
            
            inst = machine.new_machine_instance(machinetype, hostname=node.get("hostname"), instance_id=node.get("InstanceId"), group_id=node.get("placementGroupId"), keep_alive=node.get("KeepAlive", False))
            existing_machines.append(inst)
            nodes_by_instance_id[instance_id] = node
        
        return pbsnodes, existing_machines, nodes_by_instance_id, instance_ids_to_shutdown
    
    def process_pbsnode(self, pbsnode, instance_ids_to_shutdown, nodearray_definitions):
        '''
            If the pbsnode is offline, will handle evaluating whether the node can be shutdown. See instance_ids_to_shutdown, which
            is an OUT parameter here.
            
            Otherwise convert the pbsnode into a cyclecloud.machine.Machine instance.
        '''
        
        states = set(pbsnode["state"].split(","))
        resources = pbsnode["resources_available"]
        # host has incorrect case
        hostname = resources["vnode"]
        
        instance_id = resources.get("instance_id", autoscale_util.uuid("instanceid"))
        
        def try_shutdown_pbsnode():
            if not instance_id:
                pbscc.error("instance_id was not defined for host %s, can not shut it down" % hostname)
            elif "down" in states:
                # don't immediately remove down nodes, give them time to recover from network failure.
                remove_down_nodes = float(self.cc_config.get("pbspro.remove_down_nodes", 300))
                since_down = self.clock.time() - pbsnode["last_state_change_time"]
                if since_down > remove_down_nodes:
                    pbscc.error("Removing down node %s after %.0f seconds", hostname, since_down)
                    instance_ids_to_shutdown[instance_id] = hostname
                    return True
                else:
                    omega = remove_down_nodes - since_down
                    pbscc.warn("Not removing down node %s for another %.0f seconds", hostname, omega)
            else:
                instance_ids_to_shutdown[instance_id] = hostname
                return True
            
            return False
        
        if "offline" in states:
            if not pbsnode.get("jobs", []):
                pbscc.fine("%s is offline and has no jobs, may be able to shut down" % hostname)
                if try_shutdown_pbsnode():
                    return
            else:
                pbscc.fine("Host %s is offline but still running jobs" % hostname)
        
        # if the node is just in the down state, try to shut it down. 
        if set(["down"]) == states and try_shutdown_pbsnode():
            return
        
        # just ignore complex down nodes (down,job-busy etc) until PBS decides to change the state.
        if "down" in states:
            return
        
        # convert relevant resources from bytes to floating point (GB)
        for key in resources:
            
            value = resources[key]
            if isinstance(value, basestring) and value.lower() in ["true", "false"]:
                value = value.lower() == "true"
            elif isinstance(value, list):
                # TODO will need to support this eventually
                continue
            else:
                try:
                    resources[key] = pbscc.parse_gb_size(key, resources[key])
                except InvalidSizeExpressionError:
                    pass
        
        resources["hostname"] = hostname
        
        nodearray_name = resources.get("nodearray") or resources.get("slot_type")
        group_id = resources.get("group_id")

        if resources.get("machinetype") and nodearray_name:
            machinetype = nodearray_definitions.get_machinetype(nodearray_name, resources.get("machinetype"), group_id)
        else:
            # rely solely on resources_available
            pbscc.debug("machinetype is not defined for host %s, relying only on resources_available" % hostname)
            machinetype = {"availableCount": 1, "name": "undefined"}
            
        inst = machine.new_machine_instance(machinetype, **pbsnode["resources_available"])

        return inst
    

def compress_queued_jobs(autoscale_jobs):
    '''
        assuming nodearray, num nodes, placeby/placeby_value, exclusivity, packing stategy and of course the requested resources.
        
        A compressed job will have the name of the first job with ".compressed" appended to it.
        
        i.e. the goal is that if someone does
        `qsub -l mem=1g` 
        1000 times, we can compress that so that it appears as if they did
        `qsub -l select=1000:mem=1g`
        
        We do not compress SCATTER jobs.
    '''
    ret = []
    compression_buckets = collections.defaultdict(lambda: [])
    
    for job in autoscale_jobs:
        if job.packing_strategy == PackingStrategy.SCATTER:
            # for now, we will only worry about compressing PACK jobs as an optimization.
            ret.append(job)
            continue
        
        comp_bucket = (job.nodearray, job.nodes, job.placeby, job.placeby_value, job.exclusive, job.packing_strategy) + tuple(job.resources.items())
        compression_buckets[comp_bucket].append(job)
        
    for comp_bucket, job_list in compression_buckets.iteritems():
        if len(job_list) == 1:
            ret.extend(job_list)
            continue
        
        first_job = job_list[0]
        pseudo_job = Job(first_job.name + ".compressed", first_job.nodes * len(job_list), first_job.nodearray, first_job.exclusive, first_job.packing_strategy,
                         first_job.resources, first_job.placeby, first_job.placeby_value)
        ret.append(pseudo_job)
        
        pbscc.debug("Compressed jobs matching job id %s from %d jobs down to a single job" % (first_job.name, len(job_list)))
    
    return ret


class Clock:
    
    def time(self):
        import time
        return time.time()


def _hook():
    pbscc.set_application_name("cycle_autoscale")
    # allow local overrides of jetpack.config or allow non-jetpack masters to define the complete set of settings.
    overrides = {}
    
    if os.path.exists(pbscc.CONFIG_PATH):
        try:
            pbscc.warn("overrides exist in file %s" % pbscc.CONFIG_PATH)
            with open(pbscc.CONFIG_PATH) as fr:
                overrides = json.load(fr)
        except Exception:
            pbscc.error(traceback.format_exc())
            sys.exit(1)
    else:
        pbscc.debug("No overrides exist in file %s" % pbscc.CONFIG_PATH)
    
    cc_config = cyclecloud.config.new_provider_config(overrides=overrides)
    
    if len(sys.argv) < 3:
        # There are no env variables for this as far as I can tell.
        bin_dir = "/opt/pbs/bin"
    else:
        bin_dir = sys.argv[2]
        if not os.path.isdir(bin_dir):
            bin_dir = os.path.dirname(bin_dir)
    
    clusters_api = clustersapi.ClustersAPI(cc_config.get("cyclecloud.cluster.name"), cc_config)
    autostart = PBSAutostart(pbs_driver.PBSDriver(bin_dir), clusters_api, cc_config=cc_config)
    
    autostart.autoscale()


# Since this is invoked from a hook, __name__ is not "__main__", so we rely on a special env variable. Otherwise unit testing would be impossible.
if os.getenv("AUTOSTART_HOOK"):
    try:
        _hook()
    except:
        pbscc.error(traceback.format_exc())
