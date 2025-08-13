#!/bin/bash

source "${CYCLECLOUD_PROJECT_PATH}/default/files/default.sh" || exit 1

function fail() {
    local errorMsg="$1"
    [[ -z "$errorMsg" ]] || echo -e "ERROR: $errorMsg" >&2
    exit 2
}

function get_package_name() {
    PACKAGE_TYPE=$1 # Contains "server", "client", or "execution"

    if [[ "${PBSPRO_VERSION%%.*}" -lt 20 ]]; then
        echo "pbspro-${PACKAGE_TYPE}-${PBSPRO_VERSION}.x86_64.rpm"
    else
        echo "openpbs-${PACKAGE_TYPE}-${PBSPRO_VERSION}.x86_64.rpm"
    fi
}

function get_server_hostname() {
    
}