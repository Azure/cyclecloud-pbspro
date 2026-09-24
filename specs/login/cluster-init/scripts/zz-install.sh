#!/bin/bash

# This CycleCloud version has no "stages" support, so cluster-init only runs
# scripts/ (every converge). Gate the one-time install stage with a marker file.
INSTALL_MARKER="/opt/cycle/jetpack/.pbspro_login_installed"

if [[ ! -e "$INSTALL_MARKER" ]]; then
    bash "${CYCLECLOUD_PROJECT_PATH}/login/stages/install.sh" || exit 1
    touch "$INSTALL_MARKER" || exit 1
fi
