#!/bin/bash

source "${CYCLECLOUD_PROJECT_PATH}/default/files/default.sh" || exit 1

function fail() {
    local errorMsg="$1"
    [[ -z "$errorMsg" ]] || echo -e "ERROR: $errorMsg" >&2
    exit 2
}

function bool() {
  # Delegate using the arguments given, each separately quoted
  "$@"

  local exitCode=$?
  if [[ $exitCode -eq 0 ]]; then
      return 0
  elif [[ $exitCode -eq 1 ]]; then
      return 1
  else
      fail "Unexpected exit code $exitCode"
  fi
}

function get_package_name() {
    local package_name=$(jetpack config pbspro.package "") || fail
    local package_type=$1 # Contains "server", "client", or "execution"

    if [[ -z "$package_name" ]]; then
        if [[ "${PBSPRO_VERSION%%.*}" -lt 20 ]]; then
            echo "pbspro-${package_type}-${PBSPRO_VERSION}.x86_64.rpm"
        else
            echo "openpbs-${package_type}-${PBSPRO_VERSION}.x86_64.rpm"
        fi
    else
        echo "$package_name"
    fi
}
