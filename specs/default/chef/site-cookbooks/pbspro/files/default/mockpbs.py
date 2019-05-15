# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
#
import logging
import os
import time
from UserDict import UserDict
from copy import deepcopy

LOG_DEBUG = logging.DEBUG
LOG_WARNING = logging.WARN
LOG_ERROR = logging.ERROR

QUEUEJOB = "QUEUEJOB"
PERIODIC = "PERIODIC"
EVENT_ERROR = logging.ERROR


def hold_types(h):
    return h


# feel free to change as needed
hook_config_filename = "hook_config_file.json"

pbs_conf = {"PBS_EXEC": os.getcwd()}


def logmsg(level, msg):
    logging.log(level, msg)


class _Repr:
    def __init__(self, expr):
        self.expr = expr
        
    def __repr__(self):
        return self.expr


def place(expr):
    return _Repr(expr)


def select(expr):
    return _Repr(expr)


_job_queue = []


def testing_add_job(job):
    _job_queue.append(job)


class _Event:
    def __init__(self, job):
        self.job = job
    
    
def event():
    return _Event(_job_queue.pop())


pbs_str = str


class _MockJob:
    
    def __init__(self, resource_list=None):
        # match the behavior of PBS
        self._data = {}
        self.Resource_List = self._data["resource_list"] = ResourceList()
        if resource_list:
            self.Resource_List.update(resource_list)
        
    def get(self, key, default=None):
        return self._data.get(key, default)
        
    def __getitem__(self, attr):
        return self._data[attr]
    
    def __setitem__(self, attr, value):
        self._data[attr] = value
        
    def iteritems(self):
        return self._data.iteritems()
    
    def __contains__(self, key):
        return key in self._data
    

class ResourceList(UserDict):
    
    def __init__(self, *args, **kwargs):
        UserDict.__init__(self, *args, **kwargs)
    
    def __getitem__(self, key):
        if key in self:
            return UserDict.__getitem__(self, key)
        return None
    
    def __setitem__(self, key, item):
        # same failure occurs with the pbs ResourceList
        assert item is not None, "attempted to set %s to '%s'" % (key, item)
        UserDict.__setitem__(self, key, item)
    
    def __repr__(self):
        return UserDict.__repr__(self)
    
    def __str__(self):
        return UserDict.__repr__(self)
    

def mock_job(raw_job):
    '''
    Create a job object that matches the interface (duck typing) of the internal pbs job class, which
    is only accessible in the submit_hook currently.
    '''
    raw_job = deepcopy(raw_job)
    job = _MockJob(raw_job.pop("resource_list", None))
    
    job["job_id"] = raw_job.pop("job_id", str(time.time()))
    job["job_state"] = raw_job.pop("job_state", "Q")
    job["array"] = raw_job.pop("array", False)
   
    if job["array"]:
        job["array_state_count"] = raw_job.pop("array_state_count")
    
    # remaining things are assumed to be resources
    return job
