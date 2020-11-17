#!/bin/bash

if command -v docker; then
  docker run -v $(pwd)/specs/default/cluster-init/files:/source -v $(pwd)/blobs:/root/rpmbuild/RPMS/x86_64 -ti centos:7 /bin/bash -e /source/00-build-pbspro.sh
else
  echo "`docker` binary not found. Install docker to build RPMs with this script"
fi
