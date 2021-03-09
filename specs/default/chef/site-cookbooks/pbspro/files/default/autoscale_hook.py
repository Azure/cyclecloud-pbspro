
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
#

import json
import os
import shutil
import subprocess
import traceback

import pbs


def debug(msg):
    pbs.logmsg(pbs.EVENT_DEBUG, "azpbs_autoscale - %s" % msg)


def error(msg):
    pbs.logmsg(pbs.EVENT_ERROR, "azpbs_autoscale - %s" % msg)


def perform_hook():
    """
    See /var/spool/pbs/server_logs/* or /opt/cycle/jetpack/logs/autoscale.log for log messages
    """
    try:
        if not pbs.hook_config_filename:
            raise RuntimeError("Hook config for this plugin was not defined.")

        with open(pbs.hook_config_filename) as fr:
            hook_config = json.load(fr)

        azpbs_path = hook_config.get("azpbs_path")
        if not azpbs_path:
            azpbs_path = shutil.which("azpbs")
        if not azpbs_path:
            default_azpbs_path = "/opt/cycle/pbspro/venv/bin/azpbs"
            if not os.path.exists(default_azpbs_path):
                raise RuntimeError("Could not find azpbs in the path: %s" % os.environ)
            debug("Using default az path: %s" % default_azpbs_path)
            azpbs_path = default_azpbs_path

        cmd = [azpbs_path, "autoscale"]
        if hook_config.get("autoscale_json"):
            cmd.append("-c")
            cmd.append(hook_config["autoscale_json"])

        environ = {}
        environ.update(os.environ)

        assert pbs.pbs_conf.get(
            "PBS_EXEC"
        ), "PBS_EXEC was not defined in pbs.pbs_conf. This is a PBS error."
        pbs_bin = pbs.pbs_conf["PBS_EXEC"] + os.sep + "bin"
        environ["PATH"] = environ.get("PATH", ".") + os.pathsep + pbs_bin

        debug("Running %s with env %s" % (cmd, environ))

        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=environ
        )
        stdout, stderr = proc.communicate()
        if hasattr(stdout, "decode"):
            stdout = stdout.decode()
            stderr = stderr.decode()

        debug(stderr)
        if proc.returncode != 0:
            raise RuntimeError(
                'autoscale failed!\n\tstdout="%s"\n\tstderr="%s"' % (stdout, stderr)
            )
    except Exception as e:
        error(str(e))
        error(traceback.format_exc())
        raise


# hooks must not have a __name__ == "__main__" guard
perform_hook()
