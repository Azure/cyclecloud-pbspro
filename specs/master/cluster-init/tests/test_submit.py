# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
#
import unittest
import os
import time
import logging
import helper
import jetpack
from tryme import retry, Stop, Again

jetpack.util.setup_logging()

logger = logging.getLogger()

# this is only part of the full calculation
EXPECTED_RESULT = 'all done'

STATUS_NOTREADY = 'notready'
STATUS_SUCCESS = 'success'
STATUS_FAILURE = 'failure'

CLUSTER_USER = jetpack.config.get("cyclecloud.cluster.user.name")


def readfile_if_exist(filename):
    if not os.path.exists(filename):
        return ''
    
    with open(filename) as f:
        content = f.read()
    return content


def get_job_status(output_file, err_file):
    err_content = readfile_if_exist(err_file).strip()
    content = readfile_if_exist(output_file).strip()
    if content != '':
        content = content.split('\n')[-1]
        
    if content == EXPECTED_RESULT:
        return STATUS_SUCCESS, ''
    elif content != '' and content != EXPECTED_RESULT:
        return STATUS_FAILURE, \
            'Job completed with incorrect result. Expected %s but received %s' % (EXPECTED_RESULT, content)
    elif err_content != '':
        return STATUS_FAILURE, 'Job failed with error message: %s' % err_content
    else:
        return STATUS_NOTREADY, ''


@retry(timeout=1200)
def job_succeeds_or_fails(output_file, err_file):
    status, err_message = get_job_status(output_file, err_file)
    if status in [STATUS_SUCCESS, STATUS_FAILURE]:
        return Stop(status, message=err_message)
    else:
        return Again(status)


def write_sleep_script():
    uid, gid, _ = helper.get_user_profile(CLUSTER_USER)
    sleep_script = '/shared/home/%s/sleep.sh' % CLUSTER_USER
    if not(os.path.exists(sleep_script)):
        with open(sleep_script, 'w') as f:
            f.write('''
#!/bin/bash
sleep 10
echo 'all done'
''')
            os.chown(sleep_script, uid, gid)

    return sleep_script


class TestSubmit(unittest.TestCase):

    def setUp(self):
        self.userhome = "/shared/home/" + CLUSTER_USER

    def test_simple(self):
        sleep_script = write_sleep_script()
        jobtime = str(int(time.time()))
        output_file = '%s/sleep.%s.out' % (self.userhome, jobtime)
        err_file = '%s/sleep.%s.err' % (self.userhome, jobtime)
        helper.sudo_check_output(['/opt/pbs/bin/qsub', '-o',
                                  output_file, '-e', err_file, sleep_script],
                                 CLUSTER_USER, cwd=self.userhome)

        result = job_succeeds_or_fails(output_file, err_file)
        if result.failed():
            message = 'Job timed out after %d seconds' % result.elapsed
            status = STATUS_NOTREADY
        else:
            status = result.get()
            message = result.message
            
        self.assertEqual(status, STATUS_SUCCESS, msg=message)
