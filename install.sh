#!/usr/bin/env bash
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
#
set -e
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

# remove jetpack's python3 from the path
export PATH=$(echo $PATH | sed -e 's/\/opt\/cycle\/jetpack\/system\/embedded\/bin://g' | sed -e 's/:\/opt\/cycle\/jetpack\/system\/embedded\/bin//g')
set +e
which python3 > /dev/null;
if [ $? != 0 ]; then
    if [ $INSTALL_PYTHON3 == 1 ]; then
        yum install -y python3 || exit 1
    else
        echo Please install python3 >&2;
        exit 1
    fi
fi
set -e

if [ $INSTALL_VIRTUALENV == 1 ]; then
    python3 -m pip install virtualenv
fi

set +e
python3 -m virtualenv --version 2>&1 > /dev/null

if [ $? != 0 ]; then
    if [ $INSTALL_VIRTUALENV ]; then
        python3 -m pip install virtualenv || exit 1
    else
        echo Please install virtualenv for python3 >&2
        exit 1
    fi
fi
set -e

python3 -m virtualenv $VENV
source $VENV/bin/activate
# not sure why but pip gets confused installing frozendict locally
# if you don't install it first. It has no dependencies so this is safe.
pip install packages/*

cat > $VENV/bin/azpbs <<EOF
#!$VENV/bin/python

from ${SCHEDULER}.cli import main
main()
EOF
chmod +x $VENV/bin/azpbs

azpbs -h 2>&1 > /dev/null || exit 1


if [ ! -e /root/bin ]; then
    mkdir /root/bin
fi

ln -sf $VENV/bin/azpbs /root/bin/

INSTALL_DIR=$(dirname $VENV)

echo Installing "autoscale" hook
cat > $INSTALL_DIR/autoscale_hook_config.json<<EOF
{
    "azpbs_path": "$VENV/bin/azpbs",
    "autoscale_json": "$INSTALL_DIR/autoscale.json"
}
EOF

cp autoscale_hook.py $INSTALL_DIR/
cp logging.conf $INSTALL_DIR/

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

if [ -e /etc/profile.d ]; then
    cat > /etc/profile.d/azpbs_autocomplete.sh<<EOF
which azpbs 2>/dev/null || export PATH=\$PATH:/root/bin
eval "\$(/opt/cycle/pbspro/venv/bin/register-python-argcomplete azpbs)" || echo "Warning: Autocomplete is disabled" 1>&2
EOF
fi
