#!/bin/bash

source $CYCLECLOUD_PROJECT_PATH/default/files/default.sh || exit 1

PACKAGE_NAME=$(jetpack config pbspro.package "") || fail
DOWNLOADS_DIRECTORY=$(jetpack config jetpack.downloads) || fail
SERVER_HOSTNAME=$(jetpack config pbspro.scheduler "") || fail # Note: this requires adding pbspro.scheduler = <whatever_scheduler_hostnameis> to the execute node's config for now

echo "Configuring PBS Pro login node..."

if [[ -z "$PACKAGE_NAME" ]]; then
    if [[ "${PBSPRO_VERSION%%.*}" -lt 20 ]]; then
        PACKAGE_NAME="pbspro-client-${PBSPRO_VERSION}.x86_64.rpm"
    else
        PACKAGE_NAME="openpbs-client-${PBSPRO_VERSION}.x86_64.rpm"
    fi
fi

jetpack download --project pbspro "$PACKAGE_NAME" "$DOWNLOADS_DIRECTORY" || fail

yum install -y "$DOWNLOADS_DIRECTORY/$PACKAGE_NAME" || fail # TODO: this is slow, won't work on all linux distros, and will not be final--Emily and Doug's install-package will be used instead

if [[ -n "$SERVER_HOSTNAME" ]]; then
    sed -e "s|__SERVERNAME__|$SERVER_HOSTNAME|g" \
        $CYCLECLOUD_PROJECT_PATH/default/templates/default/pbs.conf.template > /etc/pbs.conf || fail
    chmod 0644 /etc/pbs.conf || fail
fi

# make this idempotent?
/opt/pbs/bin/qmgr -c "set server flatuid=true" || fail