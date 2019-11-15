# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
#
import logging_init
import unittest

from autostart import PBSAutostart
from cyclecloud import machine, autoscale_util
from cyclecloud.job import Job
from cyclecloud.machine import MachineRequest
from cyclecloud.autoscale_util import Record
import time
from itertools import chain
from cyclecloud.config import InstanceConfig
import random
import pbscc
from pbscc import InvalidSizeExpressionError


class MockDriver:
    def __init__(self, queues=None, jobs=None, hosts=None):
        self._queues = queues or ["workq"]
        self._jobs = jobs or {}
        assert isinstance(self._jobs, dict)
        self._hosts = hosts or []
        self._declared_resources = {"resources": ["ncpus", "mem", "arch", "host", "vnode", "aoe", "slot_type", 
                                                  "group_id", "ungrouped", "instance_id", "ipv4", "disk", "scratch",
                                                  "swlicense", "graphics", "dyna"]}
        
    def queues(self):
        return self._queues
    
    def queued_jobs(self):
        # TODO multiple queues
        return [x for x in self._jobs.get("workq", []) if x["job_state"] == "Q"], lambda x: x
    
    def running_jobs(self):
        return [x for x in self._jobs.get("workq", []) if x["job_state"] == "R"], lambda x: x
    
    def scheduler_config(self):
        return self._declared_resources
    
    def pbsnodes(self, grouping=None):
        ret = {None: {}}
        for host in self._hosts:
            state = host.get(grouping)
            if state not in ret:
                ret[state] = {}
            ret[state][host["resources_available"]["vnode"]] = host
        return ret
    
    def set_offline(self, hostname):
        try:
            host = self.get_host(hostname)
        except:
            return
        if "offline" not in host["state"]:
            if host["state"] == "free":
                host["state"] = "offline"
            else:
                host["state"] = host["state"] + ",offline"
                    
    def delete_host(self, hostname):
        self._hosts = [x for x in self._hosts if x["resources_available"]["vnode"] != hostname]
        
    def get_host(self, hostname):
        select = [x for x in self._hosts if x["resources_available"]["vnode"].lower() == hostname.lower()]
        assert len(select) == 1, "%s %s %s" % (select, hostname, [x["hostname"].lower() for x in self._hosts])
        return select[0]
        
    def add_host(self, hostname, state="free", **resources):
        host = {"host": hostname, "hostname": hostname, "state": state}
        resources_assigned = resources.pop("resources_assigned", {})
        if state == "job-busy" and not resources_assigned:
            raise RuntimeError("define resources_assigned")
        
        host["resources_available"] = resources
        host["resources_available"]["host"] = hostname.upper()
        host["resources_available"]["vnode"] = host["resources_available"]["host"].lower() 
        host["resources_assigned"] = resources_assigned
        host["jobs"] = resources.pop("jobs", [])
        host["last_state_change_time"] = time.time()
        self._hosts.append(host)
        

class MockClustersAPI:
    
    def __init__(self, cluster_def, nodes=None):
        self.cluster_def = cluster_def
        nodes = nodes or {}
        self._nodes = nodes
        if not hasattr(nodes, "keys"):
            self._nodes = {"execute": []}
            for node in nodes:
                # node.get_attr("instance_id", autoscale_util.uuid("instance_id"))] = node
                self._nodes["execute"].append(node)
        
    def status(self, nodes=False):
        if nodes:
            self.cluster_def["nodes"] = nodes = []
            for node_list in self._nodes.itervalues():
                nodes.extend(node_list)
        else:
            self.cluster_def.pop("nodes", [])
        return self.cluster_def
    
    def nodes(self):
        for key in self._nodes:
            random.shuffle(self._nodes[key])
        return self._nodes
    
    def add_nodes(self, request):
        for request_set in request["sets"]:
            for _ in range(request_set["count"]):
                select = [x for x in self.cluster_def["nodearrays"] if x["name"] == request_set["nodearray"]]
                assert select, "%s not in %s" % (request_set["nodearray"], [x["name"] for x in self.cluster_def["nodearrays"]])
                nodearray = select[0]
                select = [b for b in nodearray["buckets"] if b["definition"] == request_set["definition"]]
                assert select, "No matching bucket found for request %s" % request
                mt = select[0]["virtualMachine"]
                mt_name = select[0]["definition"]["machineType"]
                node = Record({"vcpuCount": mt["vcpuCount"],
                               "memory": mt["Memory"], 
                               "machineType": mt_name,
                               "placementGroupId": request_set.get("placementGroupId")})
                node.update(request_set["nodeAttributes"])
                node["nodearray"] = request_set["nodearray"]
                node["Template"] = request_set["nodearray"]
                node["InstanceId"] = autoscale_util.uuid("instance")
                
                if node["nodearray"] not in self._nodes:
                    self._nodes[node["nodearray"]] = []
                self._nodes[node["nodearray"]].append(node)
                
    def shutdown(self, instance_ids):
        instance_ids = list(instance_ids)
        for key in self._nodes:
            self._nodes[key] = [x for x in self._nodes[key] if x["InstanceId"] not in instance_ids]


def _nodearray_definitions(*machinetypes):
    machinetypes = sorted(machinetypes, key=lambda x: -x.get("priority", 100))
    cluster_status = {}
    ret = {}
    
    for machinetype in machinetypes:
        nodearray = machinetype.get("nodearray")
        if nodearray not in ret:
            ret[nodearray] = {"nodearray": {},
                              "name": nodearray,
                              "buckets": []}
        
        name = machinetype.get("machinetype")
        ret[nodearray]["buckets"].append({"definition": {"machineType": name},
                                          "virtualMachine": machinetype})

    cluster_status["nodearrays"] = ret.values()
    return cluster_status


class MockClock:
    def __init__(self, now=0):
        self.now = now
        
    def time(self):
        return self.now
    
    
class PBSQ:
    
    def __init__(self):
        self.queues = {"workq": []}
        self.job_id = 1
        self.hosts = []
    
    def qsub(self, job_id=None, job_state="Q", J=None, select_expr=None, **resource_list):
        assert "select" not in resource_list
        if not job_id:
            job_id = str(self.job_id)
            self.job_id += 1
            
        jobdef = {"resource_list": {},
                  "job_id": job_id,
                  "job_state": job_state}
        
        for key, value in resource_list.iteritems():
            jobdef["resource_list"][key] = value
            
        jobdef["resource_list"]["nodect"] = 1      
            
        if "job_state" not in jobdef:
            jobdef["job_state"] = "Q"
            
        if "ncpus" not in jobdef["resource_list"]:
            jobdef["resource_list"]["ncpus"] = jobdef.get("nodes", 1)
        
        if J:
            jobdef["array"] = True
            jobdef["array_state_count"] = J
            
        if select_expr:
            jobdef["resource_list"]["select"] = select_expr
            chunk_totals = {}
            for chunk in pbscc.parse_select(jobdef):
                chunk["ncpus"] = chunk.get("ncpus", 1)
                for key, value in chunk.iteritems():
                    if key == "select":
                        continue
                    try:
                        if key == "nodect":
                            value = pbscc.parse_gb_size(key, value)
                        else:
                            value = pbscc.parse_gb_size(key, value) * int(chunk["select"])
                        chunk_totals[key] = chunk_totals.get(key, 0) + value
                    except InvalidSizeExpressionError:
                        chunk_totals[key] = value
                        
            for key, value in chunk_totals.iteritems():
                if key != "select":
                    jobdef["resource_list"][key] = value
        
        self.queues["workq"].append(jobdef)
        
    def qdel(self, jobid):
        to_delete = [x for x in self.queues["workq"] if x["job_id"] == str(jobid)]
        assert len(to_delete) >= 1
        self.queues["workq"] = [x for x in self.queues["workq"] if x not in to_delete]
        
    def query_jobs(self):
        cluster = MockClustersAPI({})
        a = PBSAutostart(MockDriver(["workq"], self.queues), cluster, {})
        return a.query_jobs()
    
    def set_running(self, job_id, exec_vnode):
        '''
            Testing: change the job state and set exec_vnode expression so that autoscale knows where the jobs are placed
        '''
        for job in chain(*self.queues.values()):
            if str(job["job_id"]) == str(job_id):
                job["exec_vnode"] = exec_vnode
                job["job_state"] = "R"
                return
        raise AssertionError("Could not find job_id %s" % job_id)
    
        
class Test(unittest.TestCase):
    def __init__(self, methodName='runTest'):
        unittest.TestCase.__init__(self, methodName=methodName)
        self.maxDiff = None
    
    def setUp(self):
        unittest.TestCase.setUp(self)
        autoscale_util.set_uuid_func(autoscale_util.IncrementingUUID())
        
    def tearDown(self):
        unittest.TestCase.tearDown(self)
        autoscale_util.set_uuid_func(__import__("uuid").uuid4)
        
    def test_qsub(self):
        q = PBSQ()
        # q.qsub(nodes=2, ncpus=2)
        # this ^ is just tranlsated into the following
        q.qsub(select_expr="2:ncpus=2:mpiprocs=2", place="scatter")
        q.qsub(select_expr="2:ncpus=2", place="excl")
        
        self.assertEquals([Job(name="1", nodes=2, packing_strategy="scatter", exclusive=False, resources={"ncpus": 2}),
                           Job(name="2", nodes=2, packing_strategy="pack", exclusive=True, resources={"ncpus": 2})],
                           q.query_jobs())
        
        # 4 cpus packed onto one machine and 2 exclusive
        cluster_def = _nodearray_definitions(machine.new_machinetype("execute", "a2", 32, 100, 100))
        self.assertEquals([self._machine_request(machine_type="a2", count=3)], self._autoscale(q, cluster_def))
        
    def test_qsub_scatter_excl(self):
        cluster_def = _nodearray_definitions(machine.new_machinetype("execute", "a2", 32, 100, 100))
        
        for strategy in ["scatter", "vscatter"]:
            for modifier in [":excl", ":exclhost"]:
                place = strategy + modifier
                q = PBSQ()
                q.qsub(select_expr="2:ncpus=2", place=place)
                self.assertEquals([Job(name="1", nodes=2, packing_strategy="scatter", exclusive=True, resources={"ncpus": 2})],
                                   q.query_jobs())
                
                self.assertEquals([self._machine_request(machine_type="a2", count=2)], self._autoscale(q, cluster_def))
                
        for strategy in ["pack", "free"]:
            for modifier in [":excl", ":exclhost"]:
                place = strategy + modifier
                q = PBSQ()
                q.qsub(select_expr="2:ncpus=2", place=place)
                pack = "pack" if strategy in ["pack", "free"] else "scatter"
                self.assertEquals([Job(name="1", nodes=2, packing_strategy=pack, exclusive=True, resources={"ncpus": 2})],
                                   q.query_jobs())
                
                self.assertEquals([self._machine_request(machine_type="a2", count=1)], self._autoscale(q, cluster_def))
                
        for scatter in ["scatter", "vscatter"]:
            for modifier in [":shared", ""]:
                place = scatter + modifier
                q = PBSQ()
                q.qsub(select_expr="2:ncpus=2", place=place)
                self.assertEquals([Job(name="1", nodes=2, packing_strategy="scatter", exclusive=False, resources={"ncpus": 2})],
                                   q.query_jobs())
                
                self.assertEquals([self._machine_request(machine_type="a2", count=2)], self._autoscale(q, cluster_def))
                
        for scatter in ["pack", "free"]:
            for modifier in [":shared", ""]:
                place = scatter + modifier
                q = PBSQ()
                q.qsub(select_expr="2:ncpus=2", place=place)
                self.assertEquals([Job(name="1", nodes=2, packing_strategy="pack", exclusive=False, resources={"ncpus": 2})],
                                   q.query_jobs())
                
                self.assertEquals([self._machine_request(machine_type="a2", count=1)], self._autoscale(q, cluster_def))
            
    def test_pbsuserguide_too_many_cpus(self):
        cluster_def = _nodearray_definitions(machine.new_machinetype("execute", "a4", 32, 100, 100))
        
        q = PBSQ()
        q.qsub(select_expr="1:ncpus=33:mem=1G", place="pack", _can_be_added=False)
        self.assertEquals([], self._autoscale(q, cluster_def))
        
        q = PBSQ()
        q.qsub(select_expr="33:ncpus=1:mem=1G", place="pack", machinetype="a4")
        self.assertEquals([self._machine_request(machine_type="a4", count=2)], self._autoscale(q, cluster_def))
        
    def _rebalance(self, q, cluster_def=None, hosts=None, cc_config=None):
        cluster_def = cluster_def or _nodearray_definitions(machine.new_machinetype("execute", "a4", 32, 100, 100))
        pbs_autostart = PBSAutostart(MockDriver(jobs=q.queues, hosts=hosts), MockClustersAPI(cluster_def), cc_config or {})
        return pbs_autostart.autoscale()
    
    def _autoscale(self, q, cluster_def=None, hosts=None, cc_config=None):
        return self._rebalance(q, cluster_def, hosts, cc_config)[0]
    
    def _idle_nodes(self, q, cluster_def=None, hosts=None, cc_config=None):
        return [x.hostname for x in self._rebalance(q, cluster_def, hosts, cc_config)[1]]
    
    def _machine_request(self, nodearray=None, machine_type="a4", count=1, placeby="", placeby_value=""):
        nodearray = nodearray or "execute"
        
        return MachineRequest(nodearray, machine_type, count, placeby, placeby_value)
    
    def _host(self, machinetype, hostname, **resources):
        machinetype = machinetype or {}
        host = {"state": resources.pop("state", "idle"),
                "jobs": resources.pop("jobs", []),
                "resources_assigned": {},
                "resources_available": {"vnode": hostname,
                                        "host": hostname,
                                        "machinetype": machinetype.get("name", "")}}
        host["resources_available"].update(machinetype)
        host["last_state_change_time"] = resources.get("last_state_change_time") or time.time()
        host["resources_available"].update(resources)
        return host
    
    def test_pbsuserguide_ex1(self):
        '''
            1. A job that will fit in a single host but not in any of the vnodes, packed into the fewest vnodes:
                -l select=1:ncpus=10:mem=20gb
                -l place=pack
            In earlier versions, this would have been:
                -lncpus=10,mem=20gb
        '''
        q = PBSQ()
        q.qsub(select_expr="1:ncpus=16:mem=20G", place="pack")
        self.assertEquals([self._machine_request(count=1)], self._autoscale(q))
        
    def test_pbsuserguide_ex1_assume_single(self):
        '''
            same as test_pbsuserguide_ex1 but assume -l select=ncpus=16:mem=20G instead of -l select=1...
        '''
        q = PBSQ()
        q.qsub(select_expr="ncpus=16:mem=20G", place="pack")
        self.assertEquals([self._machine_request(count=1)], self._autoscale(q))
        
    def test_pbsuserguide_ex2(self):
        '''
            2. Request four chunks, each with 1 CPU and 4GB of memory taken from anywhere.
            -l select=4:ncpus=1:mem=4GB
            -l place=free
        '''
        q = PBSQ()
        q.qsub(select_expr="4:ncpus=1:mem=4G", place="pack", machinetype="a4")
        self.assertEquals([self._machine_request(count=1)], self._autoscale(q))
        
        q = PBSQ()
        q.qsub(select_expr="4:ncpus=1:mem=4G", place="pack", machinetype="a4")
        self.assertEquals([self._machine_request(count=1)], self._autoscale(q))
        
    def test_pbsuserguide_ex3(self):
        '''
            3. Allocate 4 chunks, each with 1 CPU and 2GB of memory from between one and four vnodes which have an arch of "linux".
            -l select=4:ncpus=1:mem=2GB:arch=linux -l place=free
        '''
        q = PBSQ()
        q.qsub(select_expr="4:ncpus=1:mem=2G:arch=linux", place="free")
        cluster_def = _nodearray_definitions(machine.new_machinetype("execute", "a2win", 16, 8, 100, arch="windows"),
                                             machine.new_machinetype("execute", "a2linux", 16, 8, 100, arch="linux"))
        self.assertEquals([self._machine_request(machine_type="a2linux", count=1)], self._autoscale(q, cluster_def))
        
        # slightly different take, just so that we see the spill over.
        q.qsub(select_expr="6:ncpus=1:mem=2G:arch=linux", place="free")
        self.assertEquals([self._machine_request(machine_type="a2linux", count=3)], self._autoscale(q, cluster_def))

    def test_pbsuserguide_ex4(self):
        '''
        4. Allocate four chunks on 1 to 4 vnodes where each vnode must have 1 CPU, 3GB of memory and 1 node-locked dyna
            license available for each chunk.
            -l select=4:dyna=1:ncpus=1:mem=3GB -l place=free
        '''
        q = PBSQ()
        q.qsub(select_expr="4:dyna=1:ncpus=1:mem=3G", place="free")
        cluster_def = _nodearray_definitions(machine.new_machinetype("execute", "a2nodyna", 16, 8, 100),
                                             machine.new_machinetype("execute", "a2dyna", 16, 8, 100, dyna=4))
        # 3gb with 8gb per machine, so we need 2 machines
        self.assertEquals([self._machine_request(machine_type="a2dyna", count=2)], self._autoscale(q, cluster_def))
        
        q = PBSQ()
        q.qsub(select_expr="4:dyna=1:ncpus=1:mem=1G", place="free")
        cluster_def = _nodearray_definitions(machine.new_machinetype("execute", "a2nodyna", 16, 8, 100),
                                             machine.new_machinetype("execute", "a2dyna", 16, 8, 100, dyna=4))
        # 1gb with 8gb per machine, so we need 1 machine
        self.assertEquals([self._machine_request(machine_type="a2dyna", count=1)], self._autoscale(q, cluster_def))
    
    @unittest.skip("need shared value to do this correctly")
    def test_pbsuserguide_ex5(self):
        '''
        5. Allocate four chunks on 1 to 4 vnodes, and 4 floating dyna licenses. This assumes "dyna" is specified as a server
            dynamic resource.
            -l dyna=4 -l select=4:ncpus=1:mem=3GB -l place=free
        '''
        self.fail("we need a shared value to do this correctly")
        
        q = PBSQ()
        q.qsub(select_expr="4:dyna=1, ncpus=2:mem=1G", place="free")
        dyna_license = machine.NumericValue(2, "dyna")
        cluster_def = _nodearray_definitions(machine.new_machinetype("execute", "a2nodyna", 8, 8, 100),
                                             machine.new_machinetype("execute", "a2dyna", 2, 8, 100, dyna=dyna_license))
        
        self.assertEquals([self._machine_request(machine_type="a2dyna", count=2)], self._autoscale(q, cluster_def))
        
    def test_pbsuserguide_ex6(self):
        '''
            6. This selects exactly 4 vnodes where the arch is linux, and each vnode will be on a separate host. Each vnode will
            have 1 CPU and 2GB of memory allocated to the job.
            -lselect=4:mem=2GB:ncpus=1:arch=linux -lplace=scatter
        '''
        q = PBSQ()
        q.qsub(select_expr="4:mem=2G:ncpus=1:arch=linux", place="scatter:excl")
        cluster_def = _nodearray_definitions(machine.new_machinetype("execute", "a2", 32, 128, 100, arch="linux"))
        self.assertEquals([self._machine_request(machine_type="a2", count=4)], self._autoscale(q, cluster_def))
    
    def test_pbsuserguide_ex6_scatter(self):
        q = PBSQ()
        q.qsub(select_expr="4:mem=2G:ncpus=1:arch=linux", place="scatter")
        cluster_def = _nodearray_definitions(machine.new_machinetype("execute", "a2", 32, 128, 100, arch="linux"))
        self.assertEquals([self._machine_request(machine_type="a2", count=4)], self._autoscale(q, cluster_def))
        
    def test_pbsuserguide_ex7(self):
        '''
            7. This will allocate 3 chunks, each with 1 CPU and 10GB of memory. This will also reserve 100mb of scratch space if
            scratch is to be accounted . Scratch is assumed to be on a file system common to all hosts. The value of "place"
            depends on the default which is "place=free".
            -l scratch=100mb -l select=3:ncpus=1:mem=10GB
        '''
        q = PBSQ()
        q.qsub(select_expr="3:ncpus=1:mem=10G:scratch=100M")
        
        cluster_def = _nodearray_definitions(machine.new_machinetype("execute", "a2", 32, 128, 100, scratch=.333))
        self.assertEquals([self._machine_request(machine_type="a2", count=1)], self._autoscale(q, cluster_def))
        
        cluster_def = _nodearray_definitions(machine.new_machinetype("execute", "a2", 32, 128, 100, scratch=.225))
        self.assertEquals([self._machine_request(machine_type="a2", count=2)], self._autoscale(q, cluster_def))

    def test_pbsuserguide_ex8(self):
        '''
            8. This will allocate 2 CPUs and 50GB of memory on a host named zooland. The value of "place" depends on the
            default which defaults to "place=free":
            -l select=1:ncpus=2:mem=50gb:host=zooland
        '''
        q = PBSQ()
        q.qsub(select_expr="1:ncpus=2:mem=50G:host=zooland")
        
        a2_mt = machine.new_machinetype("execute", "a2", 32, 128, 100)
        cluster_def = _nodearray_definitions(a2_mt)
        
        # pbs calls the hostname resource host, so we have to duplicate
        
        zooland = self._host(a2_mt, hostname="zooland", host="zooland")
        notzooland = self._host(a2_mt, hostname="notzooland", host="notzooland")
        self.assertEquals([], self._autoscale(q, cluster_def))
        self.assertEquals(["notzooland"], self._idle_nodes(q, cluster_def, hosts=[zooland, notzooland]))
    
    def test_pbsuserguide_ex9(self):
        '''
           9. This will allocate 1 CPU and 6GB of memory and one host-locked swlicense from each of two hosts:
            -l select=2:ncpus=1:mem=6gb:swlicense=1
            -lplace=scatter
        '''
        q = PBSQ()
        cluster_def = _nodearray_definitions(machine.new_machinetype("execute", "a2", 8, 32, 100, swlicense=0),
                                                machine.new_machinetype("execute", "a4", 16, 64, 100, swlicense=1))
        q.qsub(select_expr="2:ncpus=2:mem=6G:swlicense=1", place="scatter:excl")
        self.assertEquals([self._machine_request(machine_type="a4", count=2)], self._autoscale(q, cluster_def))
        
    def test_pbsuserguide_ex10(self):
        '''
           10. Request free placement of 10 CPUs across hosts:
            -l select=10:ncpus=1
            -l place=free
        '''
        q = PBSQ()
        q.qsub(select_expr="10:ncpus=1", place="free")
        
        a2_mt = machine.new_machinetype("execute", "a2", 32, 128, 100, priority=100)
        a4_mt = machine.new_machinetype("execute", "a4", 32, 128, 100, priority=50)
        
        cluster_def = _nodearray_definitions(a2_mt, a4_mt)
        
        # if there aren't any machines, request an a2 as this has the highest priority
        self.assertEquals([self._machine_request(machine_type="a2", count=1)], self._autoscale(q, cluster_def))
#         self.assertEquals([MachineRequest("execute", "a2", 1, "")], q.autoscale_requests(cluster_def, existing_machines=[]))
        
        existing_a4 = self._host(a4_mt, hostname="host123")
        
        # we already have an a4 up, so just use that.
        self.assertEquals([], self._autoscale(q, cluster_def, hosts=[existing_a4]))
        
    def test_pbsuserguide_ex11(self):
        '''
           11. Here is an odd-sized job that will fit on a single SGI system, but not on any one node-board. We request an odd
                number of CPUs that are not shared, so they must be "rounded up":
                -l select=1:ncpus=3:mem=6gb
                -l place=pack:excl
        '''
        q = PBSQ()
        # for allocation testing purposes, I'm going to add a free job here too to ensure we don't try to use that one.
        q.qsub(select_expr="1:ncpus=1:mem=1G", place="free")
        q.qsub(select_expr="1:ncpus=3:mem=6G", place="pack:excl")
        cluster_def = _nodearray_definitions(machine.new_machinetype("execute", "a2", 8, 24, 100, priority=100))
         
        self.assertEquals([self._machine_request(machine_type="a2", count=2)], self._autoscale(q, cluster_def))
        
        q = PBSQ()
        q.qsub(select_expr="1:ncpus=1:mem=1G", place="free")
        q.qsub(select_expr="3:ncpus=3:mem=6G", place="pack:excl")
        cluster_def = _nodearray_definitions(machine.new_machinetype("execute", "a2", 8, 24, 100, priority=100))
        
        self.assertEquals([self._machine_request(machine_type="a2", count=3)], self._autoscale(q, cluster_def))
    
    def test_pbsuserguide_ex12(self):
        '''
           12. Here is an odd-sized job that will fit on a single SGI system, but not on any one node-board. We are asking for small
                number of CPUs but a large amount of memory:
                -l select=1:ncpus=1:mem=25gb
                -l place=pack:excl
        '''
        #  this isn't really any different than ex11
        q = PBSQ()
        cluster_def = _nodearray_definitions(machine.new_machinetype("execute", "a2", 8, 50, 100, priority=100))
        q.qsub(select_expr="1:ncpus=1:mem=25G", place="pack:excl")
        
        self.assertEquals([self._machine_request(machine_type="a2", count=1)], self._autoscale(q, cluster_def))
        
        q.qsub(select_expr="1:ncpus=1:mem=1G", place="free")
        self.assertEquals([self._machine_request(machine_type="a2", count=2)], self._autoscale(q, cluster_def))
        
    def test_pbsuserguide_ex13(self):
        '''
           13. Here is a job that may be run across multiple SGI systems, packed into the fewest vnodes:
            -l select=2:ncpus=10:mem=12gb
            -l place=free
        '''
        q = PBSQ()
        q.qsub(select_expr="2:ncpus=10:mem=12G", place="free")
        cluster_def = _nodearray_definitions(machine.new_machinetype("execute", "a2", 16, 36, 100, priority=100))
        self.assertEquals([self._machine_request(machine_type="a2", count=2)], self._autoscale(q, cluster_def))
        
        cluster_def = _nodearray_definitions(machine.new_machinetype("execute", "a2", 20, 36, 100, priority=100))
        self.assertEquals([self._machine_request(machine_type="a2", count=1)], self._autoscale(q, cluster_def))
    
    def test_pbsuserguide_ex14(self):
        '''
            14. Submit a job that must be run across multiple SGI systems, packed into the fewest vnodes:
            -l select=2:ncpus=10:mem=12gb
            -l place=scatter
        '''
        q = PBSQ()
        q.qsub(select_expr="2:ncpus=10:mem=12G", place="scatter")
        cluster_def = _nodearray_definitions(machine.new_machinetype("execute", "a2", 16, 36, 100, priority=100))
        self.assertEquals([self._machine_request(machine_type="a2", count=2)], self._autoscale(q, cluster_def))
         
        # add enough CPUs and it still requests 2 machines
        cluster_def = _nodearray_definitions(machine.new_machinetype("execute", "a2", 24, 36, 100, priority=100))
        self.assertEquals([self._machine_request(machine_type="a2", count=2)], self._autoscale(q, cluster_def))
        
        q = PBSQ()
        q.qsub(select_expr="2:ncpus=10:mem=12G", place="scatter")
        # add another job
        q.qsub(select_expr="2:ncpus=10:mem=12G", place="scatter")
        cluster_def = _nodearray_definitions(machine.new_machinetype("execute", "a2", 24, 36, 100, priority=100))
        self.assertEquals([self._machine_request(machine_type="a2", count=2)], self._autoscale(q, cluster_def))
    
    def test_pbsuserguide_ex15(self):
        '''
            15. Request free placement across nodeboards within a single host:
            -l select=1:ncpus=10:mem=10gb
            -l place=group=host 
        '''
        # group=host is meaningless without existing machines... and group=host is pretty pointless.
        q = PBSQ()
        q.qsub(select_expr="1:ncpus=10:mem=10G", place="group=host")
        cluster_def = _nodearray_definitions(machine.new_machinetype("execute", "a2", 16, 36, 100, priority=100, host=123))
        # we ignore any group that isn't group_id
        self.assertEquals([self._machine_request(machine_type="a2", count=1)], self._autoscale(q, cluster_def))
#         self.assertEquals([MachineRequest("execute", "a2", 1, "")], q.autoscale_requests(cluster_def))
        
    def test_pbsuserguide_ex16(self):
        '''
            16. Request free placement across vnodes on multiple SGI systems:
            -l select=10:ncpus=1:mem=1gb
            -l place=free
        '''
        # not really that interesting
        q = PBSQ()
        q.qsub(select_expr="10:ncpus=1:mem=1G", place="free")
        cluster_def = _nodearray_definitions(machine.new_machinetype("execute", "a2", 16, 36, 100, priority=100))
        self.assertEquals([self._machine_request(machine_type="a2", count=1)], self._autoscale(q, cluster_def))
        
    def test_pbsuserguide_ex17(self):
        '''
            17. Here is a small job that uses a shared cpuset:
            -l select=1:ncpus=1:mem=512kb
            -l place=pack:shared
        '''
        # not really that interesting
        q = PBSQ()
        q.qsub(select_expr="1:ncpus=1:mem=1G", place="pack:shared")
        cluster_def = _nodearray_definitions(machine.new_machinetype("execute", "a2", 16, 36, 100, priority=100))
        self.assertEquals([self._machine_request(machine_type="a2", count=1)], self._autoscale(q, cluster_def))
        
    def test_pbsuserguide_ex18(self):
        '''
            18. Request a special resource available on a limited set of nodeboards, such as a graphics card:
            -l select= 1:ncpus=2:mem=2gb:graphics=True + 1:ncpus=20:mem=20gb:graphics=False
            -l place=pack:excl
        '''
        q = PBSQ()
        q.qsub(place="pack:excl",
                      select_expr="1:ncpus=2:mem=2G:graphics=true+1:ncpus=20:mem=20G:graphics=false")

        cluster_def = _nodearray_definitions(machine.new_machinetype("execute", "a2g", 16, 10, 100, priority=100, graphics=True),
                                                machine.new_machinetype("execute", "a2", 32, 36, 100, priority=100, graphics=False))
        
        self.assertEquals([self._machine_request(machine_type="a2", count=1),
                           self._machine_request(machine_type="a2g")], sorted(self._autoscale(q, cluster_def), key=lambda x: x.machinetype))
        
    @unittest.skip("same as ex20")
    def test_pbsuserguide_ex19(self):
        '''
            19. Align SMP jobs on c-brick boundaries:
            -l select=1:ncpus=4:mem=6gb
            -l place=pack:group=cbrick 
        '''
        q = PBSQ()
        q.qsub(select_expr="1:ncpus=4:mem=6G", place="pack:group=cbrick")
        
        #  cbrick isn't defined
        # TODO due to the single placement group hack, cbrick is set to single for this example
        
        cluster_def = _nodearray_definitions(machine.new_machinetype("execute", "a2", 16, 36, 100, priority=100),
                                                machine.new_machinetype("execute", "a2c", 16, 36, 100, priority=50, cbrick="abc"))
        cc_config = {"cyclecloud": {"placement_group": {"defaults": {"cbrick": "ccc"}}}}
        self.assertEquals([self._machine_request(machine_type="a2c", count=1, placeby="cbrick", placeby_value="ccc")], self._autoscale(q, cluster_def, cc_config=cc_config))
#         self.assertEquals([MachineRequest("execute", "a2c", 1, "")], q.autoscale_requests(cluster_def))
    
    @unittest.skip("This test will only make sense when we are using multiple placement groups")
    def test_placement_group(self):
        q = PBSQ()
        q.qsub(select_expr="4:ncpus=4:mem=6G", place="scatter:excl:group=group_id")
        
        # ok, define placement_group _and_ add a placement_group that doesn't have enough machines
        a2p_def_mt = machine.new_machinetype("execute", "a2p_def", 16, 36, 100, priority=50,
                                             placeby="group_id", group_id="def")
        a2p_abc_mt = machine.new_machinetype("execute", "a2p_abc", 16, 36, 100, priority=49,
                                             placeby="group_id", group_id="abc")
        cluster_def = _nodearray_definitions(a2p_def_mt, a2p_abc_mt)
        
        other_pg = self._host(a2p_abc_mt, hostname="otherpg")
        
        self.assertEquals([self._machine_request(nodearray="execute", machine_type="a2p_def", count=3, placeby="group_id", placeby_value="def")], 
                          self._autoscale(q, cluster_def, [other_pg]))
        
        # duplicate test - if you run the same request twice, do you get the same result?
        self.assertEquals([self._machine_request(nodearray="execute", machine_type="a2p_def", count=3, placeby="group_id", placeby_value="def")], 
                          self._autoscale(q, cluster_def, [other_pg])) 
        
        q.qsub(select_expr="1:ncpus=4:mem=6G", place="scatter:excl:group=group_id")
        self.assertEquals([self._machine_request(nodearray="execute", machine_type="a2p_def", count=4, placeby="group_id", placeby_value="def")], 
                          self._autoscale(q, cluster_def, [other_pg]))
        
        # bump up the priority of a2p_abc so that one is allocated for the second job
        cluster_def["execute"]["abc"]["machinetype"]["a2p_abc"]["priority"] = 100
        self.assertEquals([self._machine_request(nodearray="execute", machine_type="a2p_def", count=3, placeby="group_id", placeby_value="def"),
                           self._machine_request(nodearray="execute", machine_type="a2p_abc", count=1, placeby="group_id", placeby_value="abc")], 
                          self._autoscale(q, cluster_def, [other_pg]))
    
    @unittest.skip("For now this seems pointless - just use group_id. WIll need to figure out behavior around non-group_id groupings")
    def test_pbsuserguide_ex20(self):
        '''
            20. Align a large job within one router, if it fits within a router:
            -l select=1:ncpus=100:mem=200gb
            -l place=pack:group=router 
        '''
        self.fail()
        q = PBSQ()
        q.qsub(select_expr="1:ncpus=100:mem=200G", place="pack:group=router")
        
        cluster_def = _nodearray_definitions(machine.new_machinetype("execute", "a2r", 100, 200, 100, priority=100,
                                                                                    placeby="router", router="router-123"),
                                                machine.new_machinetype("execute", "a2r0", 100, 200, 100, priority=100,
                                                                                    placeby="router", router="router-123"),
                                                machine.new_machinetype("execute", "a2", 100, 200, 100, priority=200))
        
        self.assertEquals([self._machine_request(machine_type="a2r", count=1, placeby="router", placeby_value="router-123")], self._autoscale(q, cluster_def))
        self.assertEquals([MachineRequest("execute", "a2r", 1, "router-123")], q.autoscale_requests(cluster_def))
        
        q = PBSQ()
        q.qsub(select_expr="5:ncpus=100:mem=200G", place="scatter:excl:group=placement_group")
        
        self.assertEquals([MachineRequest("execute", "a2r", 5, "router-123")], q.autoscale_requests(cluster_def))
        
        cluster_def = _nodearray_definitions(machine.new_machinetype("execute", "a2r", 100, 200, 100, priority=100,
                                                                                     availableCount=4,
                                                                                    placeby="placement_group", placement_group="router-123"),
                                                machine.new_machinetype("execute", "a2r0", 100, 200, 100, priority=50,
                                                                                    placeby="placement_group", placement_group="router-234"),
                                                machine.new_machinetype("execute", "a2", 100, 200, 100, priority=200))
        
        self.assertEquals([MachineRequest("execute", "a2r0", 5, "router-234")], q.autoscale_requests(cluster_def))
        
    def test_pbsuserguide_ex22(self):
        '''
            22. To submit an MPI job, specify one chunk per MPI task. For a 10-way MPI job with 2gb of memory per MPI task:
            -l select=10:ncpus=1:mem=2gb
        '''
        q = PBSQ()
        q.qsub(select_expr="10:ncpus=1:mem=2G", place="free")

        cluster_def = _nodearray_definitions(machine.new_machinetype("execute", "a2", 16, 32, 100, priority=100))
        self.assertEquals([self._machine_request(machine_type="a2", count=1)], self._autoscale(q, cluster_def))
        
        q = PBSQ()
        q.qsub(select_expr="10:ncpus=1:mem=2G", place="free")
        
        cluster_def = _nodearray_definitions(machine.new_machinetype("execute", "a2", 8, 32, 100, priority=100))
        self.assertEquals([self._machine_request(machine_type="a2", count=2)], self._autoscale(q, cluster_def))
        
        q = PBSQ()
        q.qsub(select_expr="10:ncpus=1:mem=2G", place="scatter")
        
        cluster_def = _nodearray_definitions(machine.new_machinetype("execute", "a2", 8, 32, 100, priority=100))

        self.assertEquals([self._machine_request(machine_type="a2", count=10)], self._autoscale(q, cluster_def))
        
        q = PBSQ()
        q.qsub(select_expr="10:ncpus=1:mem=2G", place="scatter")
        q.qsub(select_expr="10:ncpus=1:mem=2G", place="scatter")
        
        cluster_def = _nodearray_definitions(machine.new_machinetype("execute", "a2", 8, 32, 100, priority=100))
        self.assertEquals([self._machine_request(machine_type="a2", count=10)], self._autoscale(q, cluster_def))
        
        q = PBSQ()
        q.qsub(select_expr="10:ncpus=1:mem=2G", place="scatter")
        q.qsub(select_expr="10:ncpus=1:mem=2G", place="scatter:excl")
        
        cluster_def = _nodearray_definitions(machine.new_machinetype("execute", "a2", 8, 32, 100, priority=100))
        self.assertEquals([self._machine_request(machine_type="a2", count=20)], self._autoscale(q, cluster_def))
    
    def test_pbsuserguide_ex23(self):
        '''
            23. To submit a non-MPI job (including a 1-CPU job or an OpenMP or shared memory) job, use a single chunk. For a
            2-CPU job requiring 10gb of memory:
            -l select=1:ncpus=2:mem=10gb
        '''
        q = PBSQ()
        q.qsub(select_expr="1:ncpus=2:mem=10G")
        cluster_def = _nodearray_definitions(machine.new_machinetype("execute", "a2", 2, 32, 100, priority=100))
        self.assertEquals([self._machine_request(machine_type="a2", count=1)], self._autoscale(q, cluster_def))
        
        cluster_def = _nodearray_definitions(machine.new_machinetype("execute", "a2", 1, 32, 100, priority=100))
        self.assertEquals([], self._autoscale(q, cluster_def))
        
    def test_pack_available(self):
        q = PBSQ()
        q.qsub(select_expr="2:ncpus=2:mem=2G", place="pack")
        cluster_def = _nodearray_definitions(machine.new_machinetype("execute", "a2", 4, 32, 100, priority=100, availableCount=1))
        self.assertEquals([self._machine_request(machine_type="a2", count=1)], self._autoscale(q, cluster_def))
        
        q = PBSQ()
        q.qsub(select_expr="2:ncpus=2:mem=2G", place="pack")
        cluster_def = _nodearray_definitions(machine.new_machinetype("execute", "a2", 2, 32, 100, priority=100, availableCount=2))
        self.assertEquals([self._machine_request(machine_type="a2", count=2)], self._autoscale(q, cluster_def))
        
        q.qsub()
        cluster_def = _nodearray_definitions(machine.new_machinetype("execute", "a2", 1, 32, 100, priority=100, availableCount=1))
        self.assertEquals([self._machine_request(machine_type="a2", count=1)], self._autoscale(q, cluster_def))
        
        q = PBSQ()
        q.qsub()
        q.qsub()
        cluster_def = _nodearray_definitions(machine.new_machinetype("execute", "a2", 1, 32, 100, priority=100, availableCount=2))
        self.assertEquals([self._machine_request(machine_type="a2", count=2)], self._autoscale(q, cluster_def))
    
    def _test_live(self, live_jobstatus, expected):
        q = PBSQ()
        q.qsub(select_expr="2:ncpus=2", place="scatter:excl")
        
        cluster_def = _nodearray_definitions(machine.new_machinetype("execute", "a2", 16, 8))
        
        mock_driver = MockDriver(["workq"], q.queues)
        mock_driver.queued_jobs = lambda: (live_jobstatus, lambda x: x)
        cluster = MockClustersAPI(cluster_def)
        a = PBSAutostart(mock_driver, cluster, {})
        
        autoscale_requests = a.autoscale()[0]
        
        if not isinstance(expected, list):
            expected = [expected]
            
        self.assertEquals(expected, autoscale_requests)
    
    def test_live(self):
        queued = [{'job_id': '11.ip-0A030005',
                      'job_state': 'Q',
                      'queue': 'workq',
                      'resource_list': {'ncpus': '2',
                                        'nodect': '2',
                                        'place': 'scatter:excl:group=group_id',
                                        'select': '2:ncpus=1:slot_type=execute'}}]
        self._test_live(queued, MachineRequest("execute", "a2", 2, "group_id", "single"))

    def test_live2(self):
        queued = [{'job_id': '27.ip-0A030005',
                      'job_state': 'Q',
                      'queue': 'workq',
                      'resource_list': {'ncpus': '4',
                                        'nodect': '2',
                                        'place': 'scatter:group=group_id',
                                        'select': '2:ncpus=2:slot_type=execute'}},
                     {'job_id': '28.ip-0A030005',
                      'job_state': 'Q',
                      'queue': 'workq',
                      'resource_list': {'ncpus': '4',
                                        'nodect': '2',
                                        'place': 'scatter:group=group_id',
                                        'select': '2:ncpus=2:slot_type=execute'}}]
        self._test_live(queued, MachineRequest("execute", "a2", 2, "group_id", "single"))
        
    def test_live3(self):
        queued = [{'job_id': '27.ip-0A030005',
                      'job_state': 'Q',
                      'resource_list': {'mem': '2mb',
                                        'ncpus': '4',
                                        'nodect': '2',
                                        'place': 'scatter:group=group_id',
                                        'select': '2:ncpus=2:slot_type=execute'}}]
        self._test_live(queued, MachineRequest("execute", "a2", 2, "group_id", "single"))
        
    def test_old_style_nodes(self):
        queued = [{'job_id': '123',
                   'job_state': 'Q',
                   'exec_host': 'cazlrss28/0*8',
                   'exec_vnode': '(cazlrss28:ncpus=8)',
                   'resource_list': {
                       'mpiprocs': '8',
                       'ncpus': '8',
                       'nodect': '1',
                       'nodes': '1:ppn8',
                       'place': 'scatter',
                       'select': '1:ncpus=8:mpiprocs=8',
                       'ungrouped': 'true'}}]
        self._test_live(queued, MachineRequest("execute", "a2", 1, "", ""))
        
    def test_forced_assignment(self):
        queued = [{'job_id': '1',
                      'job_state': 'Q',
                      'resource_list': {'mem': '2gb',
                                        'ncpus': '2',  # too many ncpus
                                        'nodect': '1',
                                        'place': 'scatter:group=group_id',
                                        'select': '1:ncpus=2:slot_type=execute'}}]
            
        running = [{'job_id': '2',
                      'job_state': 'R',
                      'exec_vnode': '(hostname-0:ncpus=18)',
                      'resource_list': {'mem': '2gb',
                                        'ncpus': '18',  # too many ncpus
                                        'nodect': '1',
                                        'arbitrary_string': 'abc', # undefined
                                        'arbitrary_bool': False,  # undefined
                                        'place': 'scatter:group=group_id',
                                        'select': '1:ncpus=18:slot_type=execute'}}]
        
        hosts = [{"state": "job-busy", "jobs": ['2'], "resources_assigned": {"ncpus": 2}, "resources_available": {"vnode": "hostname-0", "group_id": "single", "ncpus": 16, "mem": 8, "slot_type": "execute", "machinetype": "a2"}},
                 {"state": "job-idle", "resources_assigned": {}, "resources_available": {"vnode": "hostname-1", "group_id": "single", "ncpus": 16, "mem": 8, "slot_type": "execute", "machinetype": "a2"}}]
        
        for host in hosts:
            host["last_state_change_time"] = time.time()
        
        q = PBSQ()
        cluster_def = _nodearray_definitions(machine.new_machinetype("execute", "a2", 16, 8, 100, placeby="group_id", group_id="single"))
        
        mock_driver = MockDriver(["workq"], q.queues, hosts=hosts)
        mock_driver.queued_jobs = lambda: (queued, lambda x: x)
        mock_driver.running_jobs = lambda: (running, lambda x: x)
        cluster = MockClustersAPI(cluster_def)
        a = PBSAutostart(mock_driver, cluster, {})
        
        autoscale_requests, idle_machines, all_machines = a.autoscale()
        
        self.assertEquals([], autoscale_requests)
        self.assertEquals([], idle_machines)
        
        machine_0 = [x for x in all_machines if x.hostname == "hostname-0"][0]
        machine_1 = [x for x in all_machines if x.hostname == "hostname-1"][0]
        self.assertEquals(["1"], machine_1.assigned_job_ids())

        self.assertEquals(["2"], machine_0.assigned_job_ids())
        
    def test_live4(self):
        q = PBSQ()
        q.qsub(select_expr="2:ncpus=2", place="scatter:group=group_id")
        q.qsub(select_expr="2:ncpus=2", place="scatter:group=group_id")
        q.qsub(select_expr="2:ncpus=2", place="scatter:group=group_id")
        
        q.qsub(select_expr="2:ncpus=2", place="scatter:excl:group=group_id")
        
        cluster_def = _nodearray_definitions(machine.new_machinetype("execute", "a2", 4, 8))
        
        q.qsub(select_expr="2:ncpus=2", place="scatter:group=group_id")
        pbs_autostart = PBSAutostart(MockDriver(jobs=q.queues), MockClustersAPI(cluster_def), {})
        self.assertEquals([MachineRequest("execute", "a2", 6, "group_id", "single")], pbs_autostart.autoscale()[0])
        
    def test_pbsuserguide_ex8_p2(self):
        '''
            8. This will allocate 2 CPUs and 50GB of memory on a host named zooland. The value of "place" depends on the
            default which defaults to "place=free":
            -l select=1:ncpus=2:mem=50gb:host=zooland
        '''
        q = PBSQ()
        q.qsub(select_expr="1:ncpus=2:mem=2G:host=zooland")
        
        a2_mt = machine.new_machinetype("execute", "a2", 32, 128, 100)
        cluster_def = _nodearray_definitions(a2_mt)
        
        zooland = self._host(hostname="zooland", machinetype=a2_mt, ncpus=32, mem=128)
        notzooland = self._host(hostname="notzooland", machinetype=a2_mt, ncpus=32, mem=128)
        
        new, idle, all = self._rebalance(q, cluster_def, [zooland, notzooland])
        self.assertEquals([], new)
        self.assertEquals(1, len(idle))
        self.assertEquals("notzooland", idle[0].get_attr("host"))
        
        q.qsub(select_expr="1:ncpus=2:mem=2G:host=notzooland")
        
        new, idle, all = self._rebalance(q, cluster_def, [zooland, notzooland])
        self.assertEquals([], new)
        self.assertEquals(0, len(idle))
        
        q.qdel(1)
        
        new, idle, all = self._rebalance(q, cluster_def, [zooland, notzooland])
        self.assertEquals([], new)
        self.assertEquals(1, len(idle))
        self.assertEquals("zooland", idle[0].get_attr("host"))
        
    def test_arrays(self):
        q = PBSQ()
        q.qsub(J="1:100")
        # 100 * 1 core / 32 core boxes
        self.assertEquals([self._machine_request(count=4)], self._autoscale(q))
        
        q = PBSQ()
        q.qsub(J="1:100", ncpus=16)
        # 100 * 16 cores / 32 core boxes
        self.assertEquals([self._machine_request(count=50)], self._autoscale(q))
        
        q = PBSQ()
        q.qsub(J="1:25", mem=30)
        # 25 * 30 GB ram / 100 GB boxes - 3 jobs per box, so 9 boxes are required
        self.assertEquals([self._machine_request(count=9)], self._autoscale(q))
        
    def test_booleans_as_strings(self):
        ''' caught a bug where booleans show up as strings in the resources. We needed to auto-convert it'''
        job_status = [{"job_id": "7.ip-0A03000A", 
                        "job_state": "Q", 
                        "resource_list": {
                          "ncpus": "1", 
                          "nodect": "1", 
                          "place": "pack", 
                          "select": "1:ncpus=1:slot_type=execute:ungrouped=True", 
                          "slot_type": "execute", 
                          "ungrouped": "True"
                        }}]
                          
        self._test_live(job_status, [self._machine_request(machine_type="a2", count=1)])
        
    def test_custom_attribute_on_booting_instance(self):
        mt = machine.new_machinetype("execute", "a2", 4, 128, 100, availableCount=1000 * 1000 * 100)
        cluster_def = _nodearray_definitions(mt)
        q = PBSQ()
        q.qsub(ungrouped=True)
        driver = MockDriver(jobs=q.queues)
        cluster = MockClustersAPI(cluster_def, nodes=[{"MachineType": "a2", "InstanceId": "123", "Template": "execute"}])
        autoscale_requests, idle_machines, all_machines = PBSAutostart(driver, cluster, {}).autoscale()
        self.assertEquals([], autoscale_requests)
        self.assertEquals([], idle_machines)
        self.assertTrue(list(all_machines)[0].get_attr("ungrouped"))
        
    def test_no_nodearray_on_job(self):
        q = PBSQ()
        q.qsub()
        requests = self._autoscale(q)
        self.assertEquals([self._machine_request(count=1)], requests)
        
    def test_host_lifecycle(self):
        q = PBSQ()
        cc_config = InstanceConfig({}, {})
        q.qsub(select_expr="2:ncpus=16", place="scatter:excl:group=group_id")
        cluster_def = _nodearray_definitions(machine.new_machinetype("execute", "a4", 32, 100, 100))
        cluster = MockClustersAPI(cluster_def)
        driver = MockDriver(jobs=q.queues, hosts=[])
        
        def run_test(num_idle, num_request):
            
            pbs_autostart = PBSAutostart(driver, cluster, cc_config)
            
            autoscale_requests, idle_machines, machines = pbs_autostart.autoscale()
            expected_requests = [self._machine_request(count=num_request, machine_type="a4", placeby="group_id", placeby_value="single")] if num_request else []
            self.assertEquals(expected_requests, autoscale_requests)
            self.assertEquals(num_idle, len(idle_machines))
            return machines
        
        # first time we request 2 machines
        run_test(num_idle=0, num_request=2)
        # second time they are already booting
        machines = run_test(num_idle=0, num_request=0)
        
        # create them as hosts, but the jobs still aren't running...
        for n, m in enumerate(machines):
            host_attrs = {}
            for name, attr in m.iterattrs():
                host_attrs[name] = attr.current_value
        
            host_attrs.pop("hostname", "")
            host_attrs.pop("host", "")
            host_attrs["instance_id"] = "instance-%s" % n
        
            driver.add_host("hostname-%s" % n, state="free", **host_attrs)
        
        run_test(num_idle=0, num_request=0)
        
        # turns out the job ended up only running on one host... weird! But we need to respect it.
        host1 = driver.get_host("hostname-0")
        host1["jobs"] = ["1", "2"]
        host1["resources_assigned"] = {"ncpus": 16}
        host1["state"] = "job-busy"
        host1["last_state_change_time"] = time.time()
        
        q.set_running("1", "(hostname-0:ncpus=1)+(hostname-0:ncpus=1)")
        
        run_test(num_idle=1, num_request=0)
        host2 = driver.get_host("hostname-1")
        host2["last_state_change_time"] = time.time() - 3000
        # default is 300 seconds for idle machines t hat have run at least one job.
        host2["last_used_time"] = time.time() - 301
        
        self.assertEquals(host2["state"], "free")
        
        cc_config.set("cyclecloud.cluster.autoscale.stop_enabled", False)
        run_test(num_idle=1, num_request=0)
        self.assertEquals(host2["state"], "free")
        
        cc_config.set("cyclecloud.cluster.autoscale.stop_enabled", True)
        run_test(num_idle=1, num_request=0)
        self.assertEquals(host2["state"], "offline")
        # FYI idle nodes are actually terminated, but it still returns this. This isn't part of the API, this is just exposing
        # the internals of PBS autostart for testing purposes.
        machines = run_test(num_idle=1, num_request=0)
        machines = run_test(num_idle=0, num_request=0)
        # shutdown hostname-2
        self.assertEquals(1, len(machines))
        
    def test_disable_start(self):
        q = PBSQ()
        q.qsub(select_expr="1:ncpus=16:mem=20G", place="pack")
        cc_config = InstanceConfig({}, {})
        cc_config.set("cyclecloud.cluster.autoscale.start_enabled", False)
        self.assertEquals([], self._autoscale(q, cc_config=cc_config))
    
    def test_packed_multi_chunk(self):
        q = PBSQ()
        cc_config = InstanceConfig({}, {})
        q.qsub(select_expr="2:mem=15G+2:ncpus=4", place="group=group_id")
        
        cluster_def = _nodearray_definitions(
            machine.new_machinetype("execute", "a2", 2, 16, 100),
            machine.new_machinetype("execute", "a4", 4, 8, 100))
        cluster = MockClustersAPI(cluster_def)
        driver = MockDriver(jobs=q.queues, hosts=[])
        
        def run_test(num_idle, num_request):
            
            pbs_autostart = PBSAutostart(driver, cluster, cc_config)
            
            autoscale_requests, idle_machines, machines = pbs_autostart.autoscale()
            autoscale_requests = sorted(autoscale_requests, key=lambda x: x.machinetype)
            expected_requests = [self._machine_request(count=2, machine_type="a2", placeby="group_id", placeby_value="single"),
                                self._machine_request(count=2, machine_type="a4", placeby="group_id", placeby_value="single")] if num_request else []
            self.assertEquals(expected_requests, autoscale_requests)
            self.assertEquals(num_idle, len(idle_machines))
            return machines
        
        # first time we request 2 machines
        run_test(num_idle=0, num_request=4)
        # second time they are already booting
        assert len(run_test(num_idle=0, num_request=0)) == 4
        
    def test_chunk_scatter_excl(self):
        q = PBSQ()
        cc_config = InstanceConfig({}, {})
        q.qsub(select_expr="1:ncpus=4+4:ncpus=4", place="scatter:excl:group=group_id")
        
        cluster_def = _nodearray_definitions(
            machine.new_machinetype("execute", "a2", 2, 16, 100),
            machine.new_machinetype("execute", "a4", 4, 8, 100))
        cluster = MockClustersAPI(cluster_def)
        driver = MockDriver(jobs=q.queues, hosts=[])
        
        def run_test(num_idle, num_request):
            
            pbs_autostart = PBSAutostart(driver, cluster, cc_config)
            
            autoscale_requests, idle_machines, machines = pbs_autostart.autoscale()
            autoscale_requests = sorted(autoscale_requests, key=lambda x: x.machinetype)
            expected_requests = [self._machine_request(count=5, machine_type="a4", placeby="group_id", placeby_value="single")] if num_request else []
            self.assertEquals(expected_requests, autoscale_requests)
            self.assertEquals(num_idle, len(idle_machines))
            return machines
        
        # first time we request 2 machines
        run_test(num_idle=0, num_request=4)
        # second time they are already booting
        assert len(run_test(num_idle=0, num_request=0)) == 5
        
    def test_shutdown_down_nodes(self):
        '''
        Create three nodes - one that is up and busy, one that is down but presumed busy, and one that is just down.
        Test that the down node goes away after 100 seconds but that the 'down,job-busy' node does not until it is in the 'down' state.
        '''
        mt = machine.new_machinetype("execute", "a2", 4, 128, 100, availableCount=1000 * 1000 * 100)
        cc_config = InstanceConfig({}, {})
        cc_config.set("pbspro.remove_down_nodes", "100")
        clock = MockClock(time.time())
        
        q = PBSQ()
        # create one job for an up and busy node, and one for a down yet busy node 
        q.qsub(job_id="1")
        q.qsub(job_id="2")
        q.set_running("1", "(jobbusy:ncpus=1)")
        q.set_running("2", "(downjobbusy:ncpus=1)")
        
        cluster_def = _nodearray_definitions(mt)
        busy = self._host(mt, hostname="jobbusy", host="jobbusy", state="job-busy", instance_id="i123", jobs=["1"])
        down = self._host(mt, hostname="down", host="down", state="down", instance_id="i234", last_state_change_time=clock.time() - 99)
        # make it so this state is very old - we are asserting that it isn't treated as idle by PBS autostart (though it is returned as isdle by the autoscaler) 
        downjobbusy = self._host(mt, hostname="downjobbusy", host="downjobbusy", state="down,job-busy", instance_id="i345", jobs=["2"], last_state_change_time=clock.time() - 10000)
        
        driver = MockDriver(jobs=q.queues, hosts=[busy, down, downjobbusy])
        
        cluster = MockClustersAPI(cluster_def, nodes=[{"MachineType": "a2", "InstanceId": "i123", "Template": "execute", "hostname": "jobbusy"},
                                                      {"MachineType": "a2", "InstanceId": "i234", "Template": "execute", "hostname": "down"},
                                                      {"MachineType": "a2", "InstanceId": "i345", "Template": "execute", "hostname": "downjobbusy"}])
        
        # we haven't hit the timeout threshold
        autoscale_requests, idle_machines, all_machines = PBSAutostart(driver, cluster, cc_config, clock=clock).autoscale()
        self.assertEquals([], autoscale_requests)
        self.assertEquals(set(["down", "jobbusy", "downjobbusy"]), set([m.hostname for m in all_machines]))
        self.assertEquals(["down"], [m.hostname for m in idle_machines])
        
        # we have hit the timeout threshold, though autoscale will still return the idle_machine here for testing.
        clock.now += 2
        autoscale_requests, idle_machines, all_machines = PBSAutostart(driver, cluster, cc_config, clock=clock).autoscale()
        self.assertEquals([], autoscale_requests)
        self.assertEquals(set(["down", "jobbusy", "downjobbusy"]), set([m.hostname for m in all_machines]))
        self.assertEquals(["down"], [m.hostname for m in idle_machines])
        
        # rerun autoscale and the down node is gone.
        autoscale_requests, idle_machines, all_machines = PBSAutostart(driver, cluster, cc_config, clock=clock).autoscale()
        self.assertEquals([], autoscale_requests)
        self.assertEquals(set(["jobbusy", "downjobbusy"]), set([m.hostname for m in all_machines]))
        self.assertEquals([], [m.hostname for m in idle_machines])
        
        # the node is now just down, as PBS has rescheduled the job or removed it. Run autoscale twice to check it is removed.
        downjobbusy["state"] = "down"
        PBSAutostart(driver, cluster, cc_config, clock=clock).autoscale()
        autoscale_requests, idle_machines, all_machines = PBSAutostart(driver, cluster, cc_config, clock=clock).autoscale()
        
        self.assertEquals([], autoscale_requests)
        self.assertEquals(set(["jobbusy"]), set([m.hostname for m in all_machines]))
        self.assertEquals([], [m.hostname for m in idle_machines])
        

if __name__ == "__main__":
    unittest.main()
