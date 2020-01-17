#!/usr/bin/python
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
#
import cStringIO
from collections import OrderedDict

import tandem_utils
import tandem_driver_main
import json
from tandem_driver_main import TandemDriver
import os
import re
import pbscc

#     E -     Job is    exiting    after having run.
#     H -     Job is    held.
#     Q -     job is    queued,    eligable to run    or routed.
#     R -     job is    running.
#     T -     job is    being moved to new location.
#     W -     job is    waiting    for its    execution time
#      (-a option) to    be reached.
#     S -     (Unicos only) job is suspend.
_PBS_STATES = {"E": "e",
               "H": "h",
               "Q": "i",
               "R": "r",
               "W": "i",
               "S": "i"
               }

_PBS_NOT_FOUND = 153

JOB_STATE_EXITING = "E"
JOB_STATE_FINISHED = "F"
JOB_STATE_HELD = "H"
JOB_STATE_QUEUED = "Q"
JOB_STATE_RUNNING = "R"
JOB_STATE_SUSPEND = "S"
JOB_STATE_TRANSIT = "T"
JOB_STATE_USER_SUSPEND = "U"
JOB_STATE_WAITING = "W"
JOB_STATE_EXPIRED = "X"


class PBSDriver(TandemDriver):

    def __init__(self, bin_dir=None, version=None):
        TandemDriver.__init__(self)
        self.bin_dir = bin_dir
        self.version = version if version else self._version()
        
    def capabilities(self):
        return {
                    "format": ["native"],
                    "version": self.version,
                    "schedulerType": "pbs"
                }

    def _version(self):
        try:
            version_line = tandem_utils.check_call(["qmgr", "--version"]).split("\n")[0]
            return version_line.split("=")[1].strip()
        except:
            return "-1"

    def _bin(self, name):
        return name if self.bin_dir is None else os.path.join(self.bin_dir, name)

    def queues(self):
        lines = tandem_utils.check_call([self._bin("qstat"), "-Q"]).split("\n")
        return [x.split()[0] for x in lines[2:] if x.strip()]

    def jobstatus(self, scheduler_name, marker=None, local_job_id_query=None):
        marker = float(marker) if marker else 0
        stdout, stderr, code, converter = self._jobstatus()
        if code == 0:
            return converter(stdout)
        elif code == _PBS_NOT_FOUND:
            return []
        else:
            tandem_utils.error_and_exit(stderr)
            
    def scheduler_config(self):
        sched_config = "/var/spool/pbs/sched_priv/sched_config"
        pattern = re.compile(r"^\s*resources\s*: .+$")
        try:
            if os.path.exists(sched_config):
                for line in open(sched_config):
                    line = line.strip()
                    if pattern.match(line):
                        expr = line.split(":", 1)[1].strip()
                        expr = expr.replace('\"', "")
                        toks = expr.split(",")
                        resources = [x.strip() for x in toks]
                        return {"resources": resources}
        except Exception as e: 
            pbscc.error("Could not parse %s, using default resources. Error was %s" % (sched_config, str(e)))
        
        # just return default values
        return {"resources": ["ncpus", "mem", "arch", "host", "vnode", "aoe", "slot_type", "group_id", "ungrouped", "instance_id", "ipv4", "disk"]}
            
    def _jobstatus(self, local_job_id_query=None):
        stdout, stderr, code = tandem_utils.call(self.qstat_args(local_job_id_query))
        return stdout, stderr, code, _from_qstat

    def submit(self, scheduler_name, format, submit_data):
        if format == "tandem":
            parsed_submit_data = submit_data
        elif format == "tandem":
            buf = cStringIO.StringIO()
            jobs_data = json.loads(submit_data)
            for job in jobs_data:
                transform_tandem_job(job, buf)
            submit_data = buf.getvalue()
        jobid = tandem_utils.check_call([self._bin("qsub"), "-"], parsed_submit_data)
        return [job[tandem_utils.LOCAL_JOB_ID_KEY] for job in self.jobstatus(scheduler_name, 0, jobid.strip())]
    
    def logs(self, scheduler_name, local_job_id_query):
        jobs = self.jobstatus(scheduler_name, 0, local_job_id_query)
        if not jobs:
            return {}
        job = jobs[0]
        
        stdout_path = job["Output_Path"].replace("\"", "").split(":")[1]
        stderr_path = job["Error_Path"].replace("\"", "").split(":")[1]
        return tandem_utils.make_std_logs(stdout_path, stderr_path)
    
    def schedstatus(self, scheduler_name):
        # TODO
        return [{tandem_utils.SCHED_NAME_KEY: scheduler_name}]
    
    def hold(self, scheduler_name, local_job_ids):
        return self._hold_release_remove(self._bin("qhold"), local_job_ids)
    
    def release(self, scheduler_name, local_job_ids):
        return self._hold_release_remove(self._bin("qrls"), local_job_ids)
        
    def remove(self, scheduler_name, local_job_ids):
        return self._hold_release_remove(self._bin("qdel"), local_job_ids)
    
    def _hold_release_remove(self, cmd, local_job_ids):
        out, err, code = tandem_utils.call([cmd] + local_job_ids)
        if code == 0:
            return {"status": "success"}
        elif code == _PBS_NOT_FOUND:
            return {"status": "not_found", "details": err}
        else:
            return {"status": "error", "details": err}
        
    def qstat_args(self, jobid=None):
        return [self._bin("qstat"), "-f", "-w"] + ([jobid] if jobid else [])
    
    def running_jobs(self):
        return self._get_jobs([self._bin("qstat"), "-f", "-w", "-t", "-r"])
    
    def queued_jobs(self):
        return self._get_jobs([self._bin("qstat"), "-f", "-w", "-i"])
        
    def queued_array_jobs(self):
        return self._get_jobs([self._bin("qstat"), "-f", "-w", "-J"])
    
    def _get_jobs(self, args):
        stdout, stderr, code = tandem_utils.call(args)
        if code == 0:
            return stdout, _from_qstat
        elif code == _PBS_NOT_FOUND:
            return "[]", json.loads
        else:
            tandem_utils.error_and_exit(stderr)
    
    def hosts(self, grouping=None, keyformatter=lambda x: x):
        return self.pbsnodes(grouping, keyformatter)

    def pbsnodes(self, grouping=None, keyformatter=lambda x: x):
        stdout, stderr, ret = tandem_utils.call([self._bin("pbsnodes"), "-a", "-F", "json"])
        
        if ret == 1 and 'Server has no node list' in stderr:
            return {None: {}}
        
        if ret != 0:
            raise RuntimeError(stderr)
        
        nodes = json.loads(stdout)["nodes"]
        
        if not grouping:
            return {None: nodes}
        
        if isinstance(grouping, basestring):
            grouping = (grouping, )
        
        grouped = OrderedDict()
        for _node_name, node in nodes.iteritems():
            res_avail = node["resources_available"]
            
            def flat_get(node, g):
                return res_avail.get(g, node.get(g))
            
            key = keyformatter(tuple([flat_get(node, g) for g in grouping]))
            if key not in grouped:
                grouped[key] = []
            grouped[key].append(node)
            
        return grouped
    
    def set_offline(self, hostname):
        tandem_utils.check_call([self._bin("pbsnodes"), "-o", hostname])
        
    def delete_host(self, hostname):
        tandem_utils.check_call([self._bin("qmgr"), "-c", "delete node %s" % hostname])

    def alter(self, jobs):
        resources = {}
        for job in jobs: 
            resource_arg = ":".join(["%s=%s" % (x, y) for x, y in job.iteritems()])
            if resource_arg not in resources:
                resources[resource_arg] = []
            resources[resource_arg].append(job["job_id"])
        for resource_arg, job_ids in resources.iteritems():
            tandem_utils.check_call(". /etc/cluster-setup.sh && qalter %s -l %s" % (",".join([str(j) for j in job_ids]), resource_arg))

    def parse_select(self, job):
        # Need to detect when slot_type is specified with `-l select=1:slot_type`
        selectdict = {}
        select_expression = str(job.Resource_List['select'])
        
        for expr in select_expression.split(":"):
            key_val = expr.split("=", 1)
            if len(key_val) == 1:
                # this shouldn't ever happen, but log it in case.
                if "select" in selectdict:
                    continue
                key_val = ("select", key_val[0])
            selectdict[key_val[0]] = key_val[1]
            
        slot_type = selectdict.get('slot_type') or job.Resource_List.get('slot_type')
        
        return slot_type, selectdict
    
    def parse_place(self, place):
        '''
        arrangement is one of free | pack | scatter | vscatter
        sharing is one of excl | shared | exclhost
        grouping can have only one instance of group=resource
        '''
        placement = {"arrangement": "free"}
        
        if not place:
            return placement
        
        toks = place.split(":")
        
        for tok in toks:
            if tok in ["free", "pack", "scatter", "vscatter"]:
                placement["arrangement"] = tok
            elif tok in ["excl", "shared", "exclhost"]:
                placement["sharing"] = tok
            elif tok.startswith("group="):
                placement["grouping"] = tok
        
        return placement


def transform_tandem_job(job, stream):
    # TODO can do other things like add defaults or translate TandemArguments == Arguments etc.
    _to_jobad(job, stream)
    

def _to_jobad(job, stream):
    for key, value in job.iteritems():
        stream.write("%s = %s\n" % (key, value))
    stream.write("queue\n")


def _from_qstat(stdout, clz=OrderedDict):
    ads = [clz()]
    delim = ":"
    for line in stdout.strip().split("\n"):
        line = line.strip()
        if not line:
            if ads[-1]:
                ads.append(clz())
                delim = ":"
        else:
            if delim in line:
                key, value = [x.strip() for x in line.split(delim, 1)]
                keys = key.split(".")
                parent = ads[-1]

                def fmt_key(key):
                    return key.replace(" ", "_").lower()

                for parent_key in keys[:-1]:
                    parent_key = fmt_key(parent_key)
                    if parent_key not in parent:
                        parent[parent_key] = clz()
                    parent = parent[parent_key]
                parent[fmt_key(keys[-1])] = value
                delim = "="
    return [ad for ad in ads if ad]


if __name__ == "__main__":
    tandem_driver_main.main(driver=PBSDriver())
