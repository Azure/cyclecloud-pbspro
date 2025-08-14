#!/bin/bash

source "${CYCLECLOUD_PROJECT_PATH}/default/files/utils.sh" || exit 1
source "${CYCLECLOUD_PROJECT_PATH}/default/files/default.sh" || fail
source "${CYCLECLOUD_PROJECT_PATH}/default/files/hwlocs-install.sh" || fail

EXECUTE_HOSTNAME=$(jetpack config hostname) || fail
PACKAGE_NAME=$(get_package_name "execution") || fail
SERVER_HOSTNAME=$(get_server_hostname) || fail

# Forces execute node's hostname to be updated (scalelib is blocked until the hostname is correct)
# TODO: this installation status should be done by jetpack before cluster-inits are run
"${CYCLECLOUD_HOME}/system/embedded/bin/python" -c "import jetpack.converge as jc; jc._send_installation_status('warning')"

jetpack download --project pbspro "$PACKAGE_NAME" "/tmp" || fail
yum install -y -q "/tmp/$PACKAGE_NAME" || fail # TODO: this is slow, won't work on all linux distros, and will not be final--Emily and Doug's install-package will be used instead

if [[ -n "$SERVER_HOSTNAME" ]]; then
    echo "$SERVER_HOSTNAME" > /var/spool/pbs/server_name
    chmod 0644 /var/spool/pbs/server_name || fail

    cp "${CYCLECLOUD_PROJECT_PATH}/default/templates/default/mom_config.template" /var/spool/pbs/mom_priv/config || fail
    chmod 0644 /var/spool/pbs/mom_priv/config || fail

    sed -e "s|__SERVERNAME__|${SERVER_HOSTNAME}|g" \
        "${CYCLECLOUD_PROJECT_PATH}/default/templates/default/pbs.conf.template" > /etc/pbs.conf || fail
    chmod 0644 /etc/pbs.conf || fail
fi

await_node_definition() {
    if ! /opt/pbs/bin/pbsnodes "$EXECUTE_HOSTNAME"; then
        echo "${EXECUTE_HOSTNAME} is not in the cluster yet. Retrying next converge" 1>&2
        return 1
    fi
}

readonly MAX_RETRIES=10
readonly RETRY_DELAY=15
ATTEMPT=1
if ! await_node_definition; then
    while [[ $ATTEMPT -lt $MAX_RETRIES ]]; do
        sleep $RETRY_DELAY
        ((ATTEMPT+=1))
        
        if await_node_definition; then
            break;
        fi
    done

    if [[ $ATTEMPT == $MAX_RETRIES ]]; then
        fail "Command failed after $MAX_RETRIES attempts. Exiting."
    fi
fi

# This block will execute only if the "execute" node is defined in the PBS server
NODE_CREATED_GUARD="pbs.nodecreated"
if [[ -f "$NODE_CREATED_GUARD" ]]; then
    echo "Node has already been created, skipping joining checks"
else
    NODE_ATTRS=$(/opt/pbs/bin/pbsnodes "$EXECUTE_HOSTNAME") || fail
    (echo "$NODE_ATTRS" | grep -qi "$(jetpack config cyclecloud.node.id)") || fail "Stale entry found for $EXECUTE_HOSTNAME. Waiting for autoscaler to update this before joining."

    /opt/pbs/bin/pbsnodes -o "$EXECUTE_HOSTNAME" -C 'cyclecloud offline' || fail

    touch "$NODE_CREATED_GUARD" || fail
fi