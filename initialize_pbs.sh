#!/usr/bin/env bash
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
#

if [ $(whoami) != root ]; then
  echo "Please run as root"
  exit 1
fi

source /etc/profile.d/pbs.sh
set -e

/opt/pbs/bin/qmgr -c 'set server managers = root@*'
/opt/pbs/bin/qmgr -c 'set server query_other_jobs = true'
/opt/pbs/bin/qmgr -c 'set server scheduler_iteration = 15'
/opt/pbs/bin/qmgr -c 'set server flatuid = true'
/opt/pbs/bin/qmgr -c 'set server job_history_enable = true'

/opt/pbs/bin/qmgr -c "set sched only_explicit_psets=True"
/opt/pbs/bin/qmgr -c "set sched do_not_span_psets=True"


function create_resource() {
	flag=""
	if [ "$3" != "" ]; then
		flag=", flag=$3"
	fi
	/opt/pbs/bin/qmgr -c "list resource $1" >/dev/null  2>/dev/null   || \
	/opt/pbs/bin/qmgr -c "create resource $1 type=$2 $flag"
}

create_resource slot_type string h
create_resource instance_id string h
create_resource vm_size string h
create_resource nodearray string h
create_resource disk size nh
create_resource ngpus long nh

create_resource group_id string h
# would love to use a boolean here, but pbs' boolean support is buggy with
# scheduling jobs
create_resource ungrouped string h

sed -i "s/^if /#if /g" /opt/pbs/lib/init.d/limits.pbs_mom
sed -i "s/^fi/#fi /g" /opt/pbs/lib/init.d/limits.pbs_mom