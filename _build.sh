#!/bin/bash
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"

source versions.sh

# Set up the Python virtual environment for building the project
rm -rf .buildvenv
python3.11 -m venv .buildvenv
source .buildvenv/bin/activate
python -m pip install setuptools

# create TARGET_DIR for tar packaging
TARGET_DIR=".target/cyclecloud-pbspro"
rm -rf "$TARGET_DIR"

# Download the required Python packages into the TARGET_DIR/packages directory
mkdir -p "$TARGET_DIR/packages"
python -m pip download "$CYCLECLOUD_API_URL" "$SCALELIB_URL" -d "$TARGET_DIR/packages/"
# scalelib is downloaded as $SCALELIB_VERSION.tar.gz, rename it to include the cyclecloud-scalelib prefix
if [ -f "$TARGET_DIR/packages/$SCALELIB_VERSION.tar.gz" ]; then
    mv "$TARGET_DIR/packages/$SCALELIB_VERSION.tar.gz" "$TARGET_DIR/packages/cyclecloud-scalelib-$SCALELIB_VERSION.tar.gz"
fi

# exclude unnecessary packages that cause failures
rm -f "$TARGET_DIR/packages/charset_normalizer*"
rm -f "$TARGET_DIR/packages/itsdangerous*"
rm -f "$TARGET_DIR/packages/PyYAML*"

# build and package the cyclecloud-pbspro project
cd pbspro
  python setup.py sdist
  mv dist/cyclecloud-pbspro-"$PROJECT_VERSION".tar.gz ../"$TARGET_DIR/packages/"
cd ..

# copy scripts with the correct permissions
install -m 755 install.sh "$TARGET_DIR/"
install -m 644 python-functions.sh "$TARGET_DIR/"
install -m 755 initialize_pbs.sh "$TARGET_DIR/"
install -m 755 initialize_default_queues.sh "$TARGET_DIR/"
install -m 755 generate_autoscale_json.sh "$TARGET_DIR/"
install -m 755 server_dyn_res_wrapper.sh "$TARGET_DIR/"
install -m 644 ./pbspro/conf/autoscale_hook.py "$TARGET_DIR/"
install -m 644 ./pbspro/conf/logging.conf "$TARGET_DIR/"

# clean blobs dir
rm -rf blobs
mkdir blobs
# build pkg tar.gz
cd .target
  tar czf ../blobs/cyclecloud-pbspro-pkg-"$PROJECT_VERSION".tar.gz cyclecloud-pbspro
cd ..

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

rm -rf .target
rm -rf .buildvenv