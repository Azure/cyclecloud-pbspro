#!/bin/bash

function fail() {
    local errorMsg="$1"
    [[ -z "$errorMsg" ]] || echo -e "ERROR: $errorMsg" >&2
    exit 2
}