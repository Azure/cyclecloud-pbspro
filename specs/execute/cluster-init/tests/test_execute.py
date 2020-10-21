# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
#
import unittest
import subprocess

    
class TestExecute(unittest.TestCase):

    def test_simple(self):
        p = subprocess.Popen(['/opt/pbs/bin/qstat'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = p.communicate()
        if hasattr(stdout, "decode"):
            stdout = stdout.decode()
            stderr = stderr.decode()
        
        self.assertEqual(0, p.returncode, msg="Call to qstat failed with Stderr: %s\nStdout%s"
                         % (stderr, stdout))
        
