#!/usr/bin/env bash
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
#
set -e
source python-functions.sh
if [ $(whoami) != root ]; then
  echo "Please run as root"
  exit 1
fi
SCHEDULER=pbspro
INSTALL_PYTHON3=0
INSTALL_VIRTUALENV=0
VENV=/opt/cycle/${SCHEDULER}/venv
CRON_METHOD=pbs_hook

mkdir -p /opt/cycle/${SCHEDULER}/server_dyn_res
cp server_dyn_res_wrapper.sh /opt/cycle/${SCHEDULER}/
chmod +x /opt/cycle/${SCHEDULER}/server_dyn_res_wrapper.sh

export PATH=$PATH:/root/bin

while (( "$#" )); do
    case "$1" in
        --install-python3)
            INSTALL_PYTHON3=1
            INSTALL_VIRTUALENV=1
            shift
            ;;
        --install-venv)
            INSTALL_VIRTUALENV=1
            shift
            ;;
        --venv)
            VENV=$2
            shift 2
            ;;
        --cron-method)
            CRON_METHOD=$2
            shift 2
            ;;
        -*|--*=)
            echo "Unknown option $1" >&2
            exit 1
            ;;
        *)
            echo "Unknown option  $1" >&2
            exit 1
            ;;
    esac
done

echo INSTALL_PYTHON3=$INSTALL_PYTHON3
echo INSTALL_VIRTUALENV=$INSTALL_VIRTUALENV
echo VENV=$VENV

# Find / install the system python3 version.
# allow user to pick a different minimum Python version
MINIMUM_VERSION=$(jetpack config pbspro.python3.minimum_version 3.11)
PYTHON_PATH=$(find_python $MINIMUM_VERSION $INSTALL_PYTHON3)
if [ $? != 0 ]; then
    echo "Python $MINIMUM_VERSION not found and could not be installed" >&2
    exit 1
fi

# ensure that pip and virtualenv are installed
ensure_pip_and_venv "$PYTHON_PATH" $INSTALL_VIRTUALENV 
if [ $? != 0 ]; then
    echo "Python $MINIMUM_VERSION could not be configured with virtualenv and pip" >&2
    exit 1
fi

# Create the venv, activate it and install packages.
"$PYTHON_PATH" -m virtualenv "$VENV"
source "${VENV}/bin/activate"
pip install -q packages/*

# create azpbs cli
cat > "${VENV}/bin/azpbs" <<EOF
#!$VENV/bin/python

from ${SCHEDULER}.cli import main
main()
EOF
chmod +x "${VENV}/bin/azpbs"

azpbs -h 2>&1 > /dev/null || exit 1

if [ ! -e /root/bin ]; then
    mkdir /root/bin
fi

ln -sf "${VENV}/bin/azpbs" /root/bin/

# Install autoscale hook for pbs
INSTALL_DIR=$(dirname "$VENV")

echo Installing "autoscale" hook
cat > "$INSTALL_DIR/autoscale_hook_config.json" << EOF
{
    "azpbs_path": "$VENV/bin/azpbs",
    "autoscale_json": "$INSTALL_DIR/autoscale.json"
}
EOF

cp autoscale_hook.py "$INSTALL_DIR/"
cp logging.conf "$INSTALL_DIR/"

if [ "$CRON_METHOD" == "pbs_hook" ]; then
    /opt/pbs/bin/qmgr -c "list hook autoscale" 1>&2 2>/dev/null || /opt/pbs/bin/qmgr -c "create hook autoscale" 1>&2
    /opt/pbs/bin/qmgr -c "import hook autoscale application/x-python default $INSTALL_DIR/autoscale_hook.py"
    /opt/pbs/bin/qmgr -c "import hook autoscale application/x-config default $INSTALL_DIR/autoscale_hook_config.json"
    /opt/pbs/bin/qmgr -c "set hook autoscale event = periodic"
    /opt/pbs/bin/qmgr -c "set hook autoscale freq = 15"
else
    echo Installing cron job
    cat > /etc/cron.d/azpbs_autoscale<<EOF
* * * * * root /opt/cycle/jetpack/system/bootstrap/cron_wrapper.sh $VENV/bin/azpbs autoscale --config $INSTALL_DIR/autoscale.json 2>$INSTALL_DIR/last_cron.log
* * * * * root sleep 15 && /opt/cycle/jetpack/system/bootstrap/cron_wrapper.sh $VENV/bin/azpbs autoscale --config $INSTALL_DIR/autoscale.json 2>$INSTALL_DIR/last_cron.log
* * * * * root sleep 30 && /opt/cycle/jetpack/system/bootstrap/cron_wrapper.sh $VENV/bin/azpbs autoscale --config $INSTALL_DIR/autoscale.json 2>$INSTALL_DIR/last_cron.log
* * * * * root sleep 45 && /opt/cycle/jetpack/system/bootstrap/cron_wrapper.sh $VENV/bin/azpbs autoscale --config $INSTALL_DIR/autoscale.json 2>$INSTALL_DIR/last_cron.log
EOF
fi

# setup autocomplete for azpbs
if [ -e /etc/profile.d ]; then
    cat > /etc/profile.d/azpbs_autocomplete.sh<<EOF
which azpbs 2>/dev/null || export PATH=\$PATH:/root/bin
eval "\$(/opt/cycle/pbspro/venv/bin/register-python-argcomplete azpbs)" || echo "Warning: Autocomplete is disabled" 1>&2
EOF
    chmod 0755 /etc/profile.d/azpbs_autocomplete.sh || fail
fi
