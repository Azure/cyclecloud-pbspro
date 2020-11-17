#!/bin/bash

set -e

rm -rf installers
mkdir installers

cp  ../../../blobs/pbspro-server-*.x86_64.rpm installers/
if [ $(ls -1 installers/ | wc -l) != 1 ]; then
  echo Too many pbspro-server rpms
  ls installers/
  exit 1
fi

# cp  ../../../blobs/cyclecloud-pbspro-pkg-*.tar.gz  installers/
# if [ $(ls -1 installers/ | wc -l) != 2 ]; then
#   echo Too many cyclecloud pbspro pkgs
#   ls installers/
#   exit 1
# fi

PBSPRO_RPM=$(ls -1 installers/pbspro-server*.rpm)
# CC_RPM=$(ls -1 installers/cyclecloud-pbspro-pkg*.gz)


cat > Dockerfile<<EOF
FROM centos:7
COPY ${PBSPRO_RPM} /installers/

RUN yum install -y which less crontabs.noarch /installers/pbspro*server*rpm && \
    echo 'export PATH=$PATH:/opt/pbs/bin' > /etc/profile.d/ccpbs.sh && \
    sed -r s/^PBS_SERVER=.+$/PBS_SERVER=docker-desktop/g -i /etc/pbs.conf && \
    sed -r 's/^\$clienthost.+$/$clienthost docker-desktop/g' -i /var/spool/pbs/mom_priv/config && \
    echo docker-desktop > /var/spool/pbs/server_name

EOF

docker image build .