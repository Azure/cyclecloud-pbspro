#!/bin/bash
source "${CYCLECLOUD_PROJECT_PATH}/default/files/utils.sh" || exit 1
ROLE=$(jetpack config pbspro.role "") || fail

case "$ROLE" in
    execute)      systemctl start pbs || exit 1 ;;
    server|login) ;;
    *)            fail "Unknown pbspro.role '$ROLE'" ;;
esac
