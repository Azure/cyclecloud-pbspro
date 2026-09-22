#!/bin/bash

source "${CYCLECLOUD_PROJECT_PATH}/default/files/utils.sh" || exit 1

FILES=("pi.py" "pi.sh" "runpi.sh")

mkdir -p -m 755 "/etc/skel/demo" || fail

for file in "${FILES[@]}"; do
    cp "${CYCLECLOUD_PROJECT_PATH}/default/files/${file}" "/etc/skel/demo/${file}" || fail
    chmod 755 "/etc/skel/demo/${file}" || fail
done