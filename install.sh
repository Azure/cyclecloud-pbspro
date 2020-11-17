#!/usr/bin/env bash

SCHEDULER=pbspro
INSTALL_PYTHON3=0
DISABLE_CRON=0
INSTALL_VIRTUALENV=0
VENV=/opt/cycle/${SCHEDULER}/venv


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
        --disable-cron)
            DISABLE_CRON=1
            shift
            ;;
        --venv)
            VENV=$2
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

which python3 > /dev/null;
if [ $? != 0 ]; then
    if [ $INSTALL_PYTHON3 == 1 ]; then
        yum install -y python3 || exit 1
    else
        echo Please install python3 >&2;
        exit 1
    fi
fi

export PATH=$(python3 -c '
import os
paths = os.environ["PATH"].split(os.pathsep)
cc_home = os.getenv("CYCLECLOUD_HOME", "/opt/cycle/jetpack")
print(os.pathsep.join(
    [p for p in paths if cc_home not in p]))')

if [ $INSTALL_VIRTUALENV == 1 ]; then
    python3 -m pip install virtualenv
fi

python3 -m virtualenv --version 2>&1 > /dev/null
if [ $? != 0 ]; then
    if [ $INSTALL_VIRTUALENV ]; then
        python3 -m pip install virtualenv || exit 1
    else
        echo Please install virtualenv for python3 >&2
        exit 1
    fi
fi


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

ln -sf $VENV/bin/azpbs /usr/local/bin/

# echo 'azpbs' installed. A symbolic link was made to /usr/local/bin/azpbs
# crontab -l > /tmp/current_crontab
# grep -q "Created by cyclecloud-${SCHEDULER} install.sh" /tmp/current_crontab
# if [ $? != 0 ]; then
#     echo \# Created by cyclecloud-${SCHEDULER} install.sh >> /tmp/current_crontab
#     echo '* * * * * /usr/local/bin/azpbs autoscale -c /opt/cycle/'${SCHEDULER}'/autoscale.json' >> /tmp/current_crontab
#     crontab /tmp/current_crontab
# fi
# rm -f /tmp/current_crontab

# crontab -l | grep -q "Created by cyclecloud-${SCHEDULER} install.sh" && exit 0
# echo "Could not install cron job for autoscale!" >&2
# exit 1