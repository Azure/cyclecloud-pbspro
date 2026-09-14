#!/bin/bash
source "${CYCLECLOUD_PROJECT_PATH}/default/files/utils.sh" || exit 1

ROLE=$(jetpack config pbspro.role "") || fail

case "$ROLE" in
    server)
        PACKAGE_TYPE="server"
        ROLE_SCRIPT="server-install.sh"
        ;;
    login)
        PACKAGE_TYPE="client"
        ROLE_SCRIPT="login-install.sh"
        ;;
    execute)
        PACKAGE_TYPE="execution"
        ROLE_SCRIPT="execute-install.sh"
        ;;
    *)       fail "Unknown pbspro.role '$ROLE'" ;;
esac

bash "${CYCLECLOUD_PROJECT_PATH}/default/files/hwlocs-install.sh" || fail

PACKAGE_NAME=$(get_package_name "$PACKAGE_TYPE") || fail
jetpack download --project pbspro "$PACKAGE_NAME" "/tmp" || fail
yum install -y -q "/tmp/$PACKAGE_NAME" || fail

bash "${CYCLECLOUD_PROJECT_PATH}/default/roles/${ROLE_SCRIPT}" || fail
