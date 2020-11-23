#!/bin/bash
set -e
# ./package.sh

docker run -v $(pwd)/pbspro:/source -v $(pwd)/modules/cyclecloud-scalelib:/scalelib \
    -v $(pwd)/blobs:/root/blobs \
    -v $(pwd)/util:/root/util  \
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
    --network=host -ti centos:7  /bin/bash