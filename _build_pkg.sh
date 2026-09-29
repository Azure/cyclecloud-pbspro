#!/bin/bash
set -euo pipefail
source versions.sh

python -c "import sys; assert sys.prefix != sys.base_prefix, 'Please activate a virtual environment before running this script.'"
python -m pip install 'setuptools>=69.3,<72'
mkdir -p blobs/

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
rm -f $TARGET_DIR/packages/charset_normalizer*
rm -f $TARGET_DIR/packages/itsdangerous*
rm -f $TARGET_DIR/packages/PyYAML*
rm -f $TARGET_DIR/packages/pyyaml*

# build and package the cyclecloud-pbspro project
cd pbspro
  python setup.py sdist
   sdists=(dist/cyclecloud[-_]pbspro-"$PROJECT_VERSION".tar.gz)
   if [[ ${#sdists[@]} -ne 1 || ! -f "${sdists[0]}" ]]; then
       echo "Expected one cyclecloud-pbspro sdist in dist/" >&2
       exit 1
   fi
   mv "${sdists[0]}" ../"$TARGET_DIR/packages/"
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

# build pkg tar.gz
cd .target
  tar czf ../blobs/cyclecloud-pbspro-pkg-"$PROJECT_VERSION".tar.gz cyclecloud-pbspro
cd ..
