#!/bin/bash
source "${CYCLECLOUD_PROJECT_PATH}/default/files/utils.sh" || exit 1

ROLE=$(jetpack config pbspro.role "") || fail

case "$ROLE" in
    server)  bash "${CYCLECLOUD_PROJECT_PATH}/default/files/skel.sh" || fail ;;
    login|execute) ;;
    *)            fail "Unknown pbspro.role '$ROLE'" ;;
esac