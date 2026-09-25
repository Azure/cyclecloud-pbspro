#!/bin/bash
set -euo pipefail
SCALELIB_VERSION="1.0.12"
SCALELIB_FILE="cyclecloud-scalelib-{SCALELIB_VERSION}.tar.gz"
SCALELIB_URL="https://github.com/Azure/cyclecloud-scalelib/archive/refs/tags/${SCALELIB_VERSION}.tar.gz"

CYCLECLOUD_API_VERSION="8.9.3"
CYCLECLOUD_WHEEL_NAME="cyclecloud_api-${CYCLECLOUD_API_VERSION}-py2.py3-none-any.whl"
CYCLECLOUD_API_URL="https://github.com/Azure/cyclecloud-scalelib/releases/download/${SCALELIB_VERSION}/${CYCLECLOUD_WHEEL_NAME}"

BIN_RELEASE_URL="https://github.com/Azure/cyclecloud-pbspro/releases/download/2023-03-29-bins"

PROJECT_VERSION=$(cat project.ini | grep "^version" | cut -d'=' -f2 | tr -d ' ')