#!/bin/bash
source "${CYCLECLOUD_PROJECT_PATH}/default/files/utils.sh" || exit 1
echo "im running configure hook"

ROLE=$(jetpack config pbspro.role "") || fail

case "$ROLE" in
    server)  bash "${CYCLECLOUD_PROJECT_PATH}/default/files/skel.sh" || fail ;;
    login|execute) ;;
    *)            fail "Unknown pbspro.role '$ROLE'" ;;
esac