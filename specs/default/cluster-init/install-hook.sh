#!/bin/bash
source "${CYCLECLOUD_PROJECT_PATH}/default/files/utils.sh" || exit 1

bash "${CYCLECLOUD_PROJECT_PATH}/default/files/hwlocs-install.sh" || fail

ROLE=$(jetpack config pbspro.role "") || fail

echo "jetpack config pbspro.role $ROLE"

case "$ROLE" in
    server)  bash "${CYCLECLOUD_PROJECT_PATH}/default/roles/server-install.sh" || fail ;;
    login)   bash "${CYCLECLOUD_PROJECT_PATH}/default/roles/login-install.sh" || fail ;;
    execute) bash "${CYCLECLOUD_PROJECT_PATH}/default/roles/execute-install.sh" || fail ;;
    *)       fail "Unknown pbspro.role '$ROLE'" ;;
esac
