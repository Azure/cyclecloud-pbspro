#!/usr/bin/env bash
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
#

if [ $(whoami) != root ]; then
  echo "Please run as root"
  exit 1
fi

export PATH=$PATH:/root/bin

if [ -e /etc/profile.d/pbs.sh ]; then
    source /etc/profile.d/pbs.sh
else
    echo WARNING: /etc/profile.d/pbs.sh does not exist. PBS environment variables may not be initialized. 1>&2
fi
set -e

INSTALLDIR=/opt/cycle/pbspro
USERNAME=
PASSWORD=
URL=
CLUSTER_NAME=
IGNORE_QUEUES_ARG=

function usage() {
    echo Usage: $0 --username username --password password --url https://fqdn:port --cluster-name cluster_name [--install-dir /opt/cycle/pbspro]
    exit 2
}


while (( "$#" )); do
    case "$1" in
        --username)
            USERNAME=$2
            shift 2
            ;;
        --password)
            PASSWORD=$2
            shift 2
            ;;
        --url)
            URL=$2
            shift 2
            ;;
        --cluster-name)
            CLUSTER_NAME=$2
            shift 2
            ;;
        --install-dir)
            INSTALLDIR=$2
            shift 2
            ;;
        --ignore-queues)
            IGNORE_QUEUES_ARG="--ignore-queues $2"
            shift 2
            ;;
        -*|--*=)
            echo "Unknown option $1" >&2
            usage
            ;;
        *)
            echo "Unknown option  $1" >&2
            usage
            ;;
    esac
done

if [ "$1" == "-h" ]; then usage; fi
if [ "$1" == "-help" ]; then usage; fi

if [ "$USERNAME" == "" ]; then usage; fi
if [ "$PASSWORD" == "" ]; then usage; fi
if [ "$URL" == "" ]; then usage; fi
if [ "$CLUSTER_NAME" == "" ]; then usage; fi
if [ "$INSTALLDIR" == "" ]; then usage; fi

if [ -e $INSTALLDIR/autoscale.json ]; then
    if [ ! -e $INSTALLDIR/backups ]; then
        mkdir $INSTALLDIR/backups
    fi
    backup_file=$INSTALLDIR/backups/autoscale.json.$(date +%s)
    echo backing up $INSTALLDIR/autoscale.json to $backup_file
    cp $INSTALLDIR/autoscale.json $backup_file
fi

temp_autoscale=$TEMP/autoscale.json.$(date +%s)

(azpbs initconfig --cluster-name ${CLUSTER_NAME} \
                --username     ${USERNAME} \
                --password     ${PASSWORD} \
                --url          ${URL} \
                --lock-file    $INSTALLDIR/scalelib.lock \
                --log-config   $INSTALLDIR/logging.conf \
                --disable-default-resources \
                --default-resource '{"select": {}, "name": "ncpus", "value": "node.pcpu_count"}' \
                --default-resource '{"select": {}, "name": "ngpus", "value": "node.gpu_count"}' \
                --default-resource '{"select": {}, "name": "disk", "value": "size::20g"}' \
                --default-resource '{"select": {}, "name": "host", "value": "node.hostname"}' \
                --default-resource '{"select": {}, "name": "slot_type", "value": "node.nodearray"}' \
                --default-resource '{"select": {}, "name": "group_id", "value": "node.placement_group"}' \
                --default-resource '{"select": {}, "name": "mem", "value": "node.memory"}' \
                --default-resource '{"select": {}, "name": "vm_size", "value": "node.vm_size"}' \
                --idle-timeout 300 \
                --boot-timeout 3600 $IGNORE_QUEUES_ARG\
                > $temp_autoscale && mv $temp_autoscale $INSTALLDIR/autoscale.json ) || (rm -f $temp_autoscale.json; exit 1)

echo testing that we can connect to CycleCloud...
azpbs connect && echo success! || (echo Please check the arguments passed in and try again && exit 1)