#!/bin/bash
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
#

/opt/pbs/bin/qmgr -c 'set server managers = root@*'
/opt/pbs/bin/qmgr -c 'set server query_other_jobs = true'
/opt/pbs/bin/qmgr -c 'set server scheduler_iteration = 15'

function create_resource() {
	/opt/pbs/bin/qmgr -c "list resource $1" >/dev/null  2>/dev/null   || \
	/opt/pbs/bin/qmgr -c "create resource $1 type=$2, flag=h"
}

create_resource slot_type string
create_resource group_id string
create_resource ungrouped string
create_resource instance_id string
create_resource machinetype string
create_resource nodearray string
create_resource disk size
create_resource ngpus size

/opt/pbs/bin/qmgr -c "set queue workq resources_default.ungrouped = false"
/opt/pbs/bin/qmgr -c "set queue workq resources_default.place = scatter"
/opt/pbs/bin/qmgr -c "set queue workq default_chunk.ungrouped = false"
/opt/pbs/bin/qmgr -c "set queue workq default_chunk.place = scatter"

/opt/pbs/bin/qmgr -c "create queue htcq"
/opt/pbs/bin/qmgr -c "set queue htcq queue_type = Execution"
/opt/pbs/bin/qmgr -c "set queue htcq resources_default.ungrouped = true"
/opt/pbs/bin/qmgr -c "set queue htcq resources_default.place = pack"
/opt/pbs/bin/qmgr -c "set queue htcq default_chunk.ungrouped = true"
/opt/pbs/bin/qmgr -c "set queue htcq default_chunk.place = pack"
/opt/pbs/bin/qmgr -c "set queue htcq enabled = true"
/opt/pbs/bin/qmgr -c "set queue htcq started = true"

/opt/pbs/bin/qmgr -c "set sched only_explicit_psets=True"
/opt/pbs/bin/qmgr -c "set sched do_not_span_psets=True"