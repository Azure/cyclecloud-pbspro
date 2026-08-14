#!/bin/bash

source "${CYCLECLOUD_PROJECT_PATH}/default/files/utils.sh" || exit 1
source "${CYCLECLOUD_PROJECT_PATH}/default/files/default.sh" || fail

PLATFORM_VERSION=$(jetpack props get os.version) || fail

if [[ "${PLATFORM_VERSION%%.*}" -ge 8 ]]; then
  jetpack download --project pbspro "$PBSPRO_HWLOCS_LIB_EL8" "/tmp" || fail
  yum install -y -q --allowerasing "/tmp/$PBSPRO_HWLOCS_LIB_EL8" || fail
fi