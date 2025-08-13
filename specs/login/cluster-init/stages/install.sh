#!/bin/bash

source "${CYCLECLOUD_PROJECT_PATH}/default/files/default.sh" || exit 1
source "${CYCLECLOUD_PROJECT_PATH}/default/files/utils.sh" || exit 1
source "${CYCLECLOUD_PROJECT_PATH}/default/files/hwlocs-install.sh" || exit 1

PACKAGE_NAME=$(jetpack config pbspro.package "") || fail
SERVER_HOSTNAME=$(jetpack config pbspro.scheduler "") || fail

if [[ -z "$PACKAGE_NAME" ]]; then
    PACKAGE_NAME=$(get_package_name "client")
fi

jetpack download --project pbspro "$PACKAGE_NAME" "/tmp" || fail
yum install -y -q "/tmp/$PACKAGE_NAME" || fail # TODO: this is slow, won't work on all linux distros, and will not be final--Emily and Doug's install-package will be used instead

if [[ -z "$SERVER_HOSTNAME" ]]; then
    SERVER_HOSTNAME=$(get_server_hostname)
fi

if [[ -n "$SERVER_HOSTNAME" ]]; then
    sed -e "s|__SERVERNAME__|${SERVER_HOSTNAME}|g" \
        "${CYCLECLOUD_PROJECT_PATH}/default/templates/default/pbs.conf.template" > /etc/pbs.conf || fail
    chmod 0644 /etc/pbs.conf || fail
fi

/opt/pbs/bin/qmgr -c "set server flatuid=true" || fail