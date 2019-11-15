# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
#
'''
Utility class for parsing pbs specific expressions and dealing with logging inside and outside the pbs hook. 
'''
import numbers
import os
import collections
import logging
try:
    import pbs
    # there is no info in the actual pbs implementation.
    pbs_LOG_INFO = pbs.LOG_DEBUG
except ImportError:
    import mockpbs as pbs
    pbs_LOG_INFO = __import__("logging").INFO
    

_PBS_NOT_FOUND = 153
    
JOB_STATE_EXITING = "E"
JOB_STATE_FINISHED = "F"
JOB_STATE_HELD = "H"
JOB_STATE_QUEUED = "Q"
JOB_STATE_RUNNING = "R"
JOB_STATE_BATCH = "B"
JOB_STATE_SUSPEND = "S"
JOB_STATE_TRANSIT = "T"
JOB_STATE_USER_SUSPEND = "U"
JOB_STATE_WAITING = "W"
JOB_STATE_EXPIRED = "X"


CONFIG_PATH = os.path.join(os.getenv("CYCLECLOUD_BOOTSTRAP", "."), "pbs", "config.json")
    

def parse_select(raw_job):
    # Need to detect when slot_type is specified with `-l select=1:slot_type`
    chunks = []
    if not raw_job["resource_list"]['select']:
        return {}
    select_expression = str(raw_job["resource_list"]['select'])
    
    for chunk_expr in select_expression.split("+"):
        chunk = collections.OrderedDict()
        # give a default of 1 in case the user assumes 1 with their select
        # i.e. -l select=1:mem=16gb == -l select=mem=16gb
        # if they picked a number it will be overridden below
        chunk["select"] = "1"
        for expr in chunk_expr.split(":"):
            key_val = expr.split("=", 1)
            if len(key_val) == 1:
                key_val = ("select", key_val[0])
            chunk[key_val[0]] = key_val[1]
        chunks.append(chunk)
    
    return chunks


def format_select(chunk):
    expr = "%s" % chunk["select"]
    
    for key, value in chunk.iteritems():
        if key == "select":
            continue
        expr += ":%s=%s" % (key, value)
    
    return expr
        

def parse_place(place):
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


def parse_exec_vnode(expr):
    '''
    Example:  "(ip-0A030008:ncpus=1)"
    '''
    expr = expr[1:-1]
    host, resource_expr = expr.split(":", 1)
    resources = {}
    for res_sub_expr in resource_expr.split(":"):
        attr, value = res_sub_expr.split("=", 1)
        try:
            value = parse_gb_size(attr, value)
        except InvalidSizeExpressionError:
            if value.lower() in ["true", "false"]:
                value = value.lower() == "true"
            
        resources[attr] = value
    resources["hostname"] = host
    return resources


class InvalidSizeExpressionError(RuntimeError):
    pass


def parse_gb_size(attr, value):
    if isinstance(value, numbers.Number):
        return value
    try:
        
        value = value.lower()
        if value.endswith("pb"):
            value = float(value[:-2]) * 1024
        elif value.endswith("p"):
            value = float(value[:-1]) * 1024
        elif value.endswith("gb"):
            value = float(value[:-2])
        elif value.endswith("g"):
            value = float(value[:-1])
        elif value.endswith("mb"):
            value = float(value[:-2]) / 1024
        elif value.endswith("m"):
            value = float(value[:-1]) / 1024
        elif value.endswith("kb"):
            value = float(value[:-2]) / (1024 * 1024)
        elif value.endswith("k"):
            value = float(value[:-1]) / (1024 * 1024)
        elif value.endswith("b"):
            value = float(value[:-1]) / (1024 * 1024 * 1024)
        else:
            try:
                value = int(value)
            except:
                value = float(value)
        
        return value
    except ValueError:
        raise InvalidSizeExpressionError("Unsupported size for %s - %s" % (attr, value))


__FINE = 0
__DEBUG = 1
__INFO = 2
__WARN = 3
__ERROR = 4

__log_level = {
    "fine": __FINE,
    "debug": __DEBUG,
    "info": __INFO,
    "warn": __WARN,
    "error": __ERROR
}.get(os.environ.get("AUTOSTART_LOG_LEVEL", "WARN").lower(), __WARN)


__log_level_names = {
    __FINE: "fine",
    __DEBUG: "debug",
    __INFO: "info",
    __WARN: "warn",
    __ERROR: "error"
}


__application_name = "cycle_plugin"


def set_application_name(value):
    global __application_name
    __application_name = value


def __log(level, msg, interp=None):
    interp = interp or ()
    if __log_level <= level:
        pbs_msg = "%s:%s - %s" % (__application_name, __log_level_names[__log_level], msg)
        pylog_msg = msg
        try:
            pbs_msg = pbs_msg % interp
            pylog_msg = msg % interp
        except TypeError as e:
            pbs.logmsg(__WARN, str(e))
            
        if level >= __ERROR:
            pbs_level = pbs.LOG_ERROR
            pylog_level = logging.ERROR
        elif level == __WARN:
            pbs_level = pbs.LOG_WARNING
            pylog_level = logging.WARN
        elif level == __INFO:
            pbs_level = pbs_LOG_INFO
            pylog_level = logging.INFO
        else:
            pbs_level = pbs.LOG_DEBUG
            pylog_level = logging.DEBUG
        pbs.logmsg(pbs_level, pbs_msg)
        logging.log(pylog_level, pylog_msg)


def is_fine():
    return __log_level == __FINE


def fine(msg, *interp):
    interp = interp or ()
    __log(__FINE, msg, interp)


def debug(msg, *interp):
    interp = interp or ()
    __log(__DEBUG, msg, interp)


def info(msg, *interp):
    interp = interp or ()
    __log(__INFO, msg, interp)
    

def warn(msg, *interp):
    interp = interp or ()
    __log(__WARN, msg, interp)


def error(msg, *interp):
    interp = interp or ()
    __log(__WARN, msg, interp)
