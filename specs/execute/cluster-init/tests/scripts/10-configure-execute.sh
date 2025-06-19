#!/bin/bash

set -e
set -x

PACKAGE_NAME=$(config.get('package').get('package'))
PBSPRO_VERSION=$(config.get('pbspro').get('version'))
PBSPRO_DOWNLOADS=$(config.get('jetpack').get('downloads'))
HOSTNAME=$(config.get('hostname'))
SCHEDINT=$(config.get('pbspro').get('scheduler')) 

if [ "$PACKAGE_NAME" == "nil" ]; then
    if [ "$PBS_PRO_VERSION" < 20 ]; then
        PACKAGE_NAME="pbspro-execution-${PBS_PRO_VERSION}.x86_64.rpm"
    else
        PACKAGE_NAME="openpbs-execution-${PBS_PRO_VERSION}.x86_64.rpm"
    fi
else
fi

jetpack download --project pbspro $PACKAGE_NAME path_to_download

sudo yum install -y "$PBSPRO_DOWNLOADS/$PACKAGE_NAME"

if config.get('autoscale'); then
    # add to_h
    # custom_resources=config.get('autoscale').to_h
fi

cp /modify_limits.sh /var/spool/pbs/modify_limits.sh
chmod 0755 /var/spool/pbs/modify_limits.sh
chown root:root /var/spool/pbs/modify_limits.sh

if [ "$SCHEDINT" != "nil" ]; then
    # template stuff
fi


NODE_CREATED_GUARD=$(config.get('pbspro').get('node_created_guard', node_created_guard))

#TODO surround with retry logic
<<-EOF
node_attrs=$(/opt/pbs/bin/pbsnodes $HOSTNAME)
if [ $? != 0 ]; then
    echo "$HOSTNAME is not in the cluster yet. Retrying next converge" 1>&2
    exit 1
fi

echo $node_attrs | grep -qi config.get('cyclecloud')['node']['id']
if [ $? != 0 ]; then
echo "Stale entry found for $HOSTNAME. Waiting for autoscaler to update this before joining." 1>&2
exit 1
fi

/opt/pbs/bin/pbsnodes -o $HOSTNAME -C 'cyclecloud offline' && touch $NODE_CREATED_GUARD
EOF