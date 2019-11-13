import unittest
import os
import mockpbs
import sys
import json

os.environ["_UNITTEST_"] = "true"

from submit_hook import QSELECT_EXE, QSTAT_EXE, QRLS_EXE, QALTER_EXE
import submit_hook


class Job:
    
    def __init__(self, job_id=1, Hold_Types=None, queue="workq", **resource_list):
        self.job_id = str(job_id)
        self.id = self.job_id
        self.interactive = False
        self.Resource_List = mockpbs.ResourceList(resource_list)
        self.Hold_Types = Hold_Types
        self.queue = queue
        
    def to_dict(self):
        return {"queue": self.queue, "Resource_List": dict(self.Resource_List)}
    

def standard_job(**resource_list):
    resource_list["select"] = resource_list.get("select", "2:ncpus")
    return Job(Hold_Types="so", **resource_list)


class Event:
    
    def accept(self):
        pass
    
    
class MockRunCmd:
    
    def __init__(self, responses=None):
        self.responses = responses or []
        self.orig_run_cmd = submit_hook.run_cmd
        
    def add_call(self, expected, response):
        if not isinstance(response, basestring):
            response = json.dumps(response)
        self.responses.append((expected, response))
        
    def __call__(self, cmd):
        expected_cmd, response = self.responses.pop(0)
        assert expected_cmd == cmd, "%s != %s" % (expected_cmd, cmd)
        return response
    
    def __enter__(self):
        submit_hook.run_cmd = self
        return self
    
    def __exit__(self, exception_type, exception, tb):
        submit_hook.run_cmd = self.orig_run_cmd
        if exception_type is None:
            # if an exception is thrown, we expect that some responses aren't returned
            assert len(self.responses) == 0, "remaining responses %s" % self.responses
        
        
class Queue:
    
    def __init__(self, name="workq", **resources_default):
        self.name = name
        self.resources_default = resources_default or {}
        
    def to_dict(self):
        return {"resources_default": self.resources_default}
    

class SubmitHookTest(unittest.TestCase):

    def setUp(self):
        pass

    def tearDown(self):
        pass

    def test_run_cmd(self):
        try:
            submit_hook.run_cmd(["test"])
        except SystemExit:
            pass
        submit_hook.run_cmd(["test", "fail"])
        
    def test_placement_hook(self):
        select_job = Job(select="2:ncpus=2")
        plain_job = Job()
        select_job_i = Job(select="2:ncpus=2")
        plain_job_i = Job()
        select_job_i.interactive = True
        plain_job_i.interactive = True
        
        submit_hook.hold_on_submit({}, select_job)
        submit_hook.hold_on_submit({}, plain_job)
        submit_hook.hold_on_submit({}, select_job_i)
        submit_hook.hold_on_submit({}, plain_job_i)
        
        self.assertEquals("so", select_job.Hold_Types)
        self.assertEquals("so", plain_job.Hold_Types)
        
        # interactive jobs should be held as well.
        self.assertEquals("so", select_job_i.Hold_Types)
        self.assertEquals("so", plain_job_i.Hold_Types)
        
    def test_periodic_release_hook_select(self):
        '''No queue defaults, no user defined group, add group=group_id'''
        job = Job(Hold_Types="so", select="2:ncpus")
        q = Queue()
        with MockRunCmd() as run_cmd:
            _initialize_run_cmd(run_cmd, q, job, "group=group_id")
            submit_hook.periodic_release_hook({}, Event())
            
    def test_periodic_release_hook_select_with_grouping(self):
        ''' User picked group=host so we should respect that'''
        job = Job(Hold_Types="so", select="2:ncpus=2", place="scatter:excl:group=host")
        q = Queue(place="pack")
        with MockRunCmd() as run_cmd:
            # no qalter, user defined all 3 place arguments
            _initialize_run_cmd(run_cmd, q, job, expected_qalter_place=None)
            submit_hook.periodic_release_hook({}, Event())
            
        job = Job(Hold_Types="so", select="2:ncpus=2", place="group=host")
        q = Queue(place="scatter:excl")
        with MockRunCmd() as run_cmd:
            _initialize_run_cmd(run_cmd, q, job, expected_qalter_place="scatter:excl:group=host")
            submit_hook.periodic_release_hook({}, Event())
            
        job = Job(Hold_Types="so", select="2:ncpus=2", place="scatter:group=host")
        q = Queue(place="scatter:excl")
        with MockRunCmd() as run_cmd:
            # no qalter, user defined arrangement and grouping arguments
            _initialize_run_cmd(run_cmd, q, job, expected_qalter_place=None)
            submit_hook.periodic_release_hook({}, Event())
            
        job = Job(Hold_Types="so", select="2:ncpus=2", place="excl:group=host")
        q = Queue(place="scatter:excl")
        with MockRunCmd() as run_cmd:
            # no qalter, user defined sharing and grouping arguments
            _initialize_run_cmd(run_cmd, q, job, expected_qalter_place=None)
            submit_hook.periodic_release_hook({}, Event())
            
    def test_periodic_release_hook_select_with_place(self):
        ''' We should respect the user's -l place= when modifying group'''
        job = Job(Hold_Types="so", select="2:ncpus=2", place="scatter:excl")
        q = Queue()
        with MockRunCmd() as run_cmd:
            _initialize_run_cmd(run_cmd, q, job, "scatter:excl:group=group_id")
            submit_hook.periodic_release_hook({}, Event())
            
    def test_periodic_release_hook_nodes(self):
        ''' We will ignore -lplace=scatter because the user picked -l nodes=, which auto-converts to -l place=scatter'''
        job = Job(Hold_Types="so", select="2:ncpus=2", place="scatter", nodes="2:ppn=2")
        q = Queue(place="scatter:excl")
        
        with MockRunCmd() as run_cmd:
            _initialize_run_cmd(run_cmd, q, job, "scatter:excl:group=group_id")
            submit_hook.periodic_release_hook({}, Event())
            
        job = Job(Hold_Types="so", select="2:ncpus=2", place="scatter", nodes="2:ppn=2")
        q = Queue(place="pack:shared")
        
        with MockRunCmd() as run_cmd:
            _initialize_run_cmd(run_cmd, q, job, "pack:shared:group=group_id")
            submit_hook.periodic_release_hook({}, Event())
            
        job = Job(Hold_Types="so", select="2:ncpus=2", place="scatter", nodes="2:ppn=2")
        q = Queue(place="excl")
        
        with MockRunCmd() as run_cmd:
            _initialize_run_cmd(run_cmd, q, job, "excl:group=group_id")
            submit_hook.periodic_release_hook({}, Event())
            
    def test_periodic_release_hook_nodes_excl_default(self):
        ''' We should respect the user's -l place= when modifying group - pack:shared is not overridden by queue default scatter:excl'''
        job = Job(Hold_Types="so", select="2:ncpus=2", place="pack:shared")
        q = Queue(place="scatter:excl")
        
        with MockRunCmd() as run_cmd:
            _initialize_run_cmd(run_cmd, q, job, "pack:shared:group=group_id")
            submit_hook.periodic_release_hook({}, Event())
            
        # not that arrangement and exclusivity go together here
        job = Job(Hold_Types="so", select="2:ncpus=2", place="pack")
        q = Queue(place="scatter:excl")
        
        with MockRunCmd() as run_cmd:
            _initialize_run_cmd(run_cmd, q, job, "pack:group=group_id")
            submit_hook.periodic_release_hook({}, Event())
            
    def test_periodic_release_hook_missing_select(self):
        ''' We convert simple qsubs into select=1:ncpus=1 - note we should set the default to free in this case'''
        job = Job(Hold_Types="so")
        q = Queue()
        q.resources_default["place"] = "scatter:excl"
        
        with MockRunCmd() as run_cmd:
            _initialize_run_cmd(run_cmd, q, job, expected_qalter_place="scatter:excl:group=group_id")
            # nothing to hold
            submit_hook.periodic_release_hook({}, Event())
            
    def test_chunked(self):
        ''' There shouldn't be anything special about a chunked expression.'''
        job = Job(Hold_Types="so", select="2:ncpus=2+1:mem=20g")
        q = Queue()
        
        with MockRunCmd() as run_cmd:
            _initialize_run_cmd(run_cmd, q, job, expected_qalter_place="group=group_id")
            # nothing to hold
            submit_hook.periodic_release_hook({}, Event())
            
    def test_two_queues(self):
        hpc_job = Job(job_id=1, Hold_Types="so", queue="workq", select="2:ncpus=2+1:mem=20g")
        hpcq = Queue("workq")
        # we don't pick up on defaults from the queue, so just set ungrouped on both.
        htc_job = Job(job_id=2, Hold_Types="so", queue="htcq", ungrouped=True)
        htcq = Queue("htcq", ungrouped=True, place="pack")
        
        with MockRunCmd() as run_cmd:
            _initialize_run_cmd(run_cmd, [hpcq, htcq], [hpc_job, htc_job],
                                # we won't bother running qalter because ungrouped==true
                                expected_qalter_place=["group=group_id", None])
            # nothing to hold
            submit_hook.periodic_release_hook({}, Event())
            

def _initialize_run_cmd(run_cmd, queues, jobs, expected_qalter_place):
    if not isinstance(queues, list):
        queues = [queues]
        
    if not isinstance(jobs, list):
        jobs = [jobs]
        
    if not isinstance(expected_qalter_place, list):
        expected_qalter_place = [expected_qalter_place]
        
    job_ids = [job.job_id for job in jobs]
        
    run_cmd.add_call([QSELECT_EXE, "-h", "so"], " ".join([job.job_id for job in jobs]))
    
    queues_response = {"Queue": {}}
    for q in queues:
        queues_response["Queue"][q.name] = q.to_dict()
    
    run_cmd.add_call([QSTAT_EXE, "-Qf", "-F", "json"], queues_response)
    
    jobs_response = {"Jobs": {}}
    for job in jobs:
        jobs_response["Jobs"][job.job_id] = job.to_dict()
        
    run_cmd.add_call([QSTAT_EXE, "-f", "-F", "json"] + job_ids, jobs_response)
    
    if not job_ids:
        assert not expected_qalter_place
    
    for job, eqp in zip(jobs, expected_qalter_place):
        select = job.Resource_List["select"] or "1:ncpus=1"
        if eqp:
            run_cmd.add_call([QALTER_EXE, "-lselect=" + select, "-lplace=" + eqp, job.job_id], "qalter successful")
        run_cmd.add_call([QRLS_EXE, "-h", "so", job.job_id], "qrls successful")
        

if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    unittest.main()