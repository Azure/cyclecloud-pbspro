# https://www.altair.com/pdfs/pbsworks/PBSHooks2020.1.pdf
# 4.5.1
# must import site for pbs module to be included
import site  # noqa
import time
from subprocess import check_call

# https://www.altair.com/pdfs/pbsworks/PBSProgramGuide2020.1.pdf
# 8.4 pbs_module
# and
# https://www.altair.com/pdfs/pbsworks/PBSHooks2020.1.pdf#page=84&zoom=100,78,208
# 6.1
import pbs

try:

    pbs.logmsg(pbs.LOG_ERROR, "RDH Disabling scheduler")
    check_call(["/opt/pbs/bin/qmgr", "-c", "set sched default scheduling = false"])
    pbs.logmsg(pbs.LOG_ERROR, "RDH sleeping")
    time.sleep(10)
    pbs.logmsg(pbs.LOG_ERROR, "RDH enabling scheduler")
    check_call(["/opt/pbs/bin/qmgr", "-c", "set sched default scheduling = true"])
    pbs.logmsg(pbs.LOG_ERROR, "RDH done")
    pbs.logmsg(pbs.LOG_ERROR, "RDH accepting event")
    pbs.event().accept()
except Exception as e:
    pbs.logmsg(pbs.LOG_ERROR, "RDH failed {}".format(e))
