#!/bin/bash

source "${CYCLECLOUD_PROJECT_PATH}/default/files/utils.sh" || exit 1

SERVER_IP_ADDRESS=$(jetpack config cyclecloud.mounts.nfs_sched.address "") || fail


if [[ -n "$SERVER_IP_ADDRESS" ]]; then
    sed -e "s|__SERVERNAME__|${SERVER_IP_ADDRESS}|g" \
        "${CYCLECLOUD_PROJECT_PATH}/default/templates/default/pbs.conf.template" > /etc/pbs.conf || fail
    chmod 0644 /etc/pbs.conf || fail
fi

/opt/pbs/bin/qmgr -c "set server flatuid=true" || fail