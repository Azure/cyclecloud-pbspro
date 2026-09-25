#!/bin/bash

# This CycleCloud version has no "stages" support, so cluster-init only runs
# scripts/ (every converge). Gate the one-time install and always re-run activate.
INSTALL_MARKER="/opt/cycle/jetpack/.pbspro_execute_installed"

if [[ ! -e "$INSTALL_MARKER" ]]; then
    bash "${CYCLECLOUD_PROJECT_PATH}/execute/stages/install.sh" || exit 1
    touch "$INSTALL_MARKER" || exit 1
fi

bash "${CYCLECLOUD_PROJECT_PATH}/execute/stages/activate.sh" || exit 1
