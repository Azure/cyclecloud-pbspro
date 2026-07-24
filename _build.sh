#!/bin/bash
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"

source versions.sh

# Set up the Python virtual environment for building the project
rm -rf .buildvenv
python3.11 -m venv .buildvenv
source .buildvenv/bin/activate

# clean blobs dir and build the cyclecloud-pbspro-pkg tar
rm -rf blobs
./_build_pkg.sh
./_download_blobs.sh

rm -rf .target
rm -rf .buildvenv