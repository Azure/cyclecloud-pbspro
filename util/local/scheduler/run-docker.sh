#!/bin/bash

(docker image list pbspro-scheduler | grep pbspro-scheduler) || (echo please run build-docker.sh and then docker image tag SHA pbspro-scheduler; exit 1)

set -e
pushd ../../../
ROOT=$(pwd)
./package.sh
popd

docker run -v ${ROOT}/pbspro:/source \
    -v ${ROOT}/modules/cyclecloud-scalelib:/scalelib \
    -v ${ROOT}/blobs:/root/blobs \
    -v $(pwd):/root/util  \
    --publish 15001:15001/tcp \
    --publish 15001:15001/udp \
    --publish 15002:15002/tcp \
    --publish 15002:15002/udp \
    --publish 15003:15003/tcp \
    --publish 15003:15003/udp \
    --publish 15004:15004/tcp \
    --publish 15004:15004/udp \
    --publish 15005:15005/tcp \
    --publish 15005:15005/udp \
    --publish 15006:15006/tcp \
    --publish 15006:15006/udp \
    --publish 15007:15007/tcp \
    --publish 15007:15007/udp \
    --publish 17001:17001/tcp \
    --publish 17001:17001/udp \
    --network=bridge -ti pbspro-scheduler  /bin/bash