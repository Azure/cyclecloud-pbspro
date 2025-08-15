#!/bin/bash

PLATFORM_VERSION=$(jetpack props get os.version) || fail

if [[ "${PLATFORM_VERSION%%.*}" -ge 8 ]]; then
  jetpack download --project pbspro "$PBSPRO_HWLOCS_LIB_EL8" "/tmp" || fail
  yum install -y -q --allowerasing "/tmp/$PBSPRO_HWLOCS_LIB_EL8" || fail
fi