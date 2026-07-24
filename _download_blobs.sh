#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")"

source versions.sh
mkdir -p blobs
# download additional blobs specified in project.ini
for blob in $(python <<EOF
import configparser
config = configparser.ConfigParser()
config.read('project.ini')
for blob in config.get('blobs', 'Files').split(","):
    if not "cyclecloud" in blob:
        print(blob.strip())
EOF
); do 
    echo "Downloading $blob..."
    wget -O "blobs/$blob" "$BIN_RELEASE_URL/$blob"
done
echo "All blobs downloaded successfully."