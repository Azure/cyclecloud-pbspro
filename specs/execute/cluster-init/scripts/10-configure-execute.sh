#!/bin/bash

set -e
set -x

source /mnt/cluster-init/pbspro/default/files/default.sh

echo "Configuring PBS Pro execution node..."

PACKAGE_NAME=$(jetpack config pbspro.package || echo "nil")
# PBSPRO_VERSION="20.0.1-0" # TODO: use default var instead
HOSTNAME=$(jetpack config hostname)

# Note: this requires adding pbspro.scheduler = <whatever_scheduler_hostnameis> to the execute node's config for now
if ! SERVER_HOSTNAME=$(jetpack config pbspro.scheduler); then
    SERVER_HOSTNAME=$(jetpack config cyclecloud.instance.hostname)
fi

if [[ "$PACKAGE_NAME" == "nil" ]]; then
    if [[ "${PBSPRO_VERSION%%.*}" < 20 ]]; then
        PACKAGE_NAME="pbspro-execution-${PBSPRO_VERSION}.x86_64.rpm"
    else
        echo "openpbs version -- ${PBSPRO_VERSION%%.*}"
        PACKAGE_NAME="openpbs-execution-${PBSPRO_VERSION}.x86_64.rpm"
    fi
fi

jetpack download --project pbspro "$PACKAGE_NAME" "$(jetpack config jetpack.downloads)"

# TODO: this is slow, won't work on all linux distros, and will not be final--Emily and Doug's install-package will be used instead
sudo yum install -y "$(jetpack config jetpack.downloads)/$PACKAGE_NAME"

if [ "$SERVER_HOSTNAME" != "nil" ]; then
    echo "SERVER_HOSTNAME is $SERVER_HOSTNAME"

    echo "$SERVER_HOSTNAME" > /var/spool/pbs/server_name
    chmod 0644 /var/spool/pbs/server_name
    chown root:root /var/spool/pbs/server_name

    echo '$usecp *:/shared /shared' > /var/spool/pbs/mom_priv/config
    chmod 0644 /var/spool/pbs/mom_priv/config
    chown root:root /var/spool/pbs/mom_priv/config

    sed -e "s|__SERVERNAME__|$SERVER_HOSTNAME|g" \
        /mnt/cluster-init/pbspro/default/templates/default/pbs.conf.template > /etc/pbs.conf
    chmod 0644 /etc/pbs.conf
    chown root:root /etc/pbs.conf
fi

cp /mnt/cluster-init/pbspro/default/files/modify_limits.sh /var/spool/pbs/modify_limits.sh
chmod 0755 /var/spool/pbs/modify_limits.sh
chown root:root /var/spool/pbs/modify_limits.sh

NODE_CREATED_GUARD="$(jetpack config cyclecloud.chefstate)/pbs.nodecreated"

retry_command() {
    local max_retries=10
    local retry_delay=15
    local attempt=1
    
    while (( attempt <= max_retries )); do
        echo Attempting $attempt
        if "$@"; then
            return 0
        fi

        if ((attempt == max_retries)); then
        echo "Command failed after $max_retries attempts. Exiting."
            return 1
        fi

        echo "Command failed, retrying..."
        sleep $retry_delay
        ((attempt+=1))
    done

    return 1
}

await_node_definition() {
    /opt/pbs/bin/pbsnodes $HOSTNAME || {
        echo "$HOSTNAME is not in the cluster yet. Retrying next converge" 1>&2
        return 1
    }
}

await_joining_cluster() {
    if [ -f $NODE_CREATED_GUARD ]; then
        echo "Node has already been created, skipping joining checks"
        return 0
    fi
    
    NODE_ATTRS=$(/opt/pbs/bin/pbsnodes $HOSTNAME)
    if [ $? != 0 ]; then
        echo "$HOSTNAME is not in the cluster yet. Retrying next converge" 1>&2
        exit 1
    fi

    echo $NODE_ATTRS | grep -qi "$(jetpack config cyclecloud.node.id)"
    if [ $? != 0 ]; then
        echo "Stale entry found for $HOSTNAME. Waiting for autoscaler to update this before joining." 1>&2
        exit 1
    fi

    /opt/pbs/bin/pbsnodes -o $HOSTNAME -C 'cyclecloud offline' && touch $NODE_CREATED_GUARD
}

if retry_command await_node_definition; then
    echo "are we about to call await joining cluster?"
    await_joining_cluster
else 
    exit 1
fi
