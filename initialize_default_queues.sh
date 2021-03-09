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
/opt/pbs/bin/qmgr -c "set queue workq resources_default.place = scatter:excl"
/opt/pbs/bin/qmgr -c "set queue workq resources_default.ungrouped = false"

/opt/pbs/bin/qmgr -c "set server node_group_enable = true"
/opt/pbs/bin/qmgr -c 'set server node_group_key = group_id'

/opt/pbs/bin/qmgr -c "list queue htcq" 2>/dev/null || /opt/pbs/bin/qmgr -c "create queue htcq"
/opt/pbs/bin/qmgr -c "set queue htcq queue_type = Execution"
/opt/pbs/bin/qmgr -c "set queue htcq resources_default.place = free"
/opt/pbs/bin/qmgr -c "set queue htcq resources_default.ungrouped = true"
/opt/pbs/bin/qmgr -c "set queue htcq enabled = true"
/opt/pbs/bin/qmgr -c "set queue htcq started = true"