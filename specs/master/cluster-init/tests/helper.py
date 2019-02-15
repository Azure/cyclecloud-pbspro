# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
#
from jetpack import config
import subprocess
import os
import sys
import traceback
import StringIO
import logging
import platform

if platform.system() != 'Windows':
    import pwd


logger = logging.getLogger(__name__)


def get_user_profile(user_name, cwd=None):
    '''Get user id, group id, and environment variables for specified user'''
    pw_record = pwd.getpwnam(user_name)
    user_name = pw_record.pw_name
    user_home_dir = pw_record.pw_dir
    user_uid = pw_record.pw_uid
    user_gid = pw_record.pw_gid
    env = os.environ.copy()
    env['HOME'] = user_home_dir
    env['LOGNAME'] = user_name
    env['PWD'] = cwd or user_home_dir
    env['USER'] = user_name
    return user_uid, user_gid, env


def demote_to_user(user_uid, user_gid):
    '''Demote current process to given user and group'''
    def result():
        os.setgid(user_gid)
        os.setuid(user_uid)
    return result


def sudo_check_call(cmd_args, username, cwd=None, env=None):
    uid, gid, user_env = get_user_profile(username, cwd=cwd)
    user_env.update(env)
    subprocess.check_call(cmd_args, cwd=cwd, env=env, preexec_fn=demote_to_user(uid, gid))
    return True


def sudo_check_output(cmd_args, username, cwd=None, env={}):
    uid, gid, user_env = get_user_profile(username, cwd=cwd)
    user_env.update(env)
    return subprocess.check_output(cmd_args, cwd=cwd, env=user_env, preexec_fn=demote_to_user(uid, gid))


def get_chef_role(role_name):
    return role_name in config.get('roles', [])


def exception_to_str():
    t, e, tb = sys.exc_info()
    f = StringIO.StringIO()
    traceback.print_tb(tb, None, f)
    stack_trace = f.getvalue()
    if e.message == '':
        exception_message = getattr(e, 'strerror', '')
    else:
        exception_message = e.message
    message = "Encountered exception of type %s with error message:" % type(e)

    if exception_message != '':
        message = message + '\n' + exception_message
    message = message + '\n' + 'Stacktrace:\n%s' % stack_trace
    return message


def count_nodes_by_os(output, operating_system):
    nodes = output.strip().split('\n\n')
    if len(nodes) < 1:
        return 0
    opsys = operating_system.upper()
    return len(filter(lambda node: 'OpSys = "%s"' % opsys in node, nodes))
