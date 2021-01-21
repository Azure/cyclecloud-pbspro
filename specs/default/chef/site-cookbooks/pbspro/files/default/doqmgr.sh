#!/bin/bash
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
#
set -e

/opt/pbs/bin/qmgr -c 'set server managers = root@*'
/opt/pbs/bin/qmgr -c 'set server query_other_jobs = true'
/opt/pbs/bin/qmgr -c 'set server scheduler_iteration = 15'
/opt/pbs/bin/qmgr -c 'set server flatuid = true'

function create_resource() {
	flag=""
	if [ "$3" != "" ]; then
		flag=", flag=$3"
	fi
	/opt/pbs/bin/qmgr -c "list resource $1" >/dev/null  2>/dev/null   || \
	/opt/pbs/bin/qmgr -c "create resource $1 type=$2 $flag"
}

create_resource slot_type string h
create_resource group_id string h
create_resource instance_id string h
create_resource vm_size string h
create_resource nodearray string h

create_resource disk size nh
create_resource ngpus long nh
# no flag
create_resource skipcyclesubhook boolean

/opt/pbs/bin/qmgr -c "set queue workq resources_default.place = scatter:excl:group=group_id"

/opt/pbs/bin/qmgr -c "create queue htcq"
/opt/pbs/bin/qmgr -c "set queue htcq queue_type = Execution"
/opt/pbs/bin/qmgr -c "set queue htcq resources_default.place = pack"
/opt/pbs/bin/qmgr -c "set queue htcq resources_default.skipcyclesubhook = true"
/opt/pbs/bin/qmgr -c "set queue htcq enabled = true"
/opt/pbs/bin/qmgr -c "set queue htcq started = true"

/opt/pbs/bin/qmgr -c "set sched only_explicit_psets=True"
/opt/pbs/bin/qmgr -c "set sched do_not_span_psets=True"