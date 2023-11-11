#!/bin/bash

if command -v docker; then
  # building pbspro 18.1.4 rpm's
  docker run -v $(pwd)/specs/default/cluster-init/files:/source -v $(pwd)/blobs:/root/rpmbuild/RPMS/x86_64 -ti centos:7 /bin/bash -e /source/00-build-pbspro.sh
  # building openpbs 20.0.1 rpm's
  docker run -v $(pwd)/specs/default/cluster-init/files:/source -v $(pwd)/blobs:/root/rpmbuild/RPMS/x86_64 -ti centos:7 /bin/bash -e /source/00-build-openpbs.sh
else
  echo "`docker` binary not found. Install docker to build RPMs with this script"
fi
