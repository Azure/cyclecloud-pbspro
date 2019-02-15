# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
#

import json
import os
import subprocess
import traceback

try:
    import pbs
except ImportError:
    import mockpbs as pbs


def perform_hook():
    """
        See /var/spool/pbs/server_logs/* or /opt/cycle/jetpack/logs/autoscale.log for log messages
    """
    try:
        if not pbs.hook_config_filename:
            raise RuntimeError("Hook config for this plugin was not defined.")

        with open(pbs.hook_config_filename) as fr:
            hook_config = json.load(fr)
            
        log_dir = os.path.join(hook_config.get("cyclecloud_home"), "logs")
        
        if not os.path.exists(log_dir):
            log_dir = os.getcwd()
        
        env_with_src_dirs = {"PYTHONPATH": os.pathsep.join(hook_config.get("src_dirs", [])),
                             "AUTOSTART_HOOK": "1",
                             "AUTOSTART_LOG_FILE": os.path.join(log_dir, "autoscale.log"),
                             "AUTOSTART_LOG_FILE_LEVEL": hook_config.get("autostart_log_file_level") or "DEBUG",
                             "AUTOSTART_LOG_LEVEL": hook_config.get("autostart_log_level") or "DEBUG"}

        jetpack_config = hook_config.get("jetpack_python")
        if not jetpack_config:
            if not hook_config.get("cyclecloud_home"):
                raise RuntimeError("Please specify either jetpack_python or cyclecloud_home in the hook config.")

            hook_config["jetpack_python"] = os.path.join(hook_config["cyclecloud_home"], "system", "embedded", "bin", "python")

        pbs_bin_dir = os.path.join(pbs.pbs_conf["PBS_EXEC"], "bin")

        cmd = [hook_config["jetpack_python"], "-m", "autostart", pbs.hook_config_filename, pbs_bin_dir]
        
        pbs.logmsg(pbs.LOG_DEBUG, "Running %s with environment %s" % (cmd, env_with_src_dirs))
        
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env_with_src_dirs)
        stdout, stderr = proc.communicate()
        pbs.logmsg(pbs.LOG_DEBUG, stderr)
        if proc.returncode != 0:
            raise RuntimeError('autostart failed!\n\tstdout="%s"\n\tstderr="%s"' % (stdout, stderr))
    except:
        pbs.logmsg(pbs.LOG_ERROR, traceback.format_exc())
        raise

# hooks must not have a __name__ == "__main__" guard
perform_hook()
