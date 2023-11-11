#!/bin/bash -e

OPENPBS_VERSION="20.0.1"
OPENPBS_FOLDER="openpbs-${OPENPBS_VERSION}"
OPENPBS_PKG="v${OPENPBS_VERSION}.tar.gz"
OPENPBS_DIST=openpbs-${OPENPBS_VERSION}.tar.gz
DOWNLOAD_URL="https://github.com/openpbs/openpbs/archive/refs/tags"

# see https://openpbs.atlassian.net/wiki/spaces/PBSPro/pages/13991940/Building+PBS+Pro+Using+rpmbuild
yum install -y rpmdevtools
rpmdev-setuptree

# Install other build deps
#yum install -y gcc autoconf automake hwloc-devel libX11-devel libXt-devel libedit-devel libical-devel ncurses-devel perl postgresql-devel python-devel==2.7.5-77.el7_6 tcl-devel tk-devel swig expat-devel openssl-devel 
yum install -y gcc make rpm-build libtool hwloc-devel libX11-devel libXt-devel libedit-devel libical-devel ncurses-devel perl postgresql-devel python-devel tcl-devel  tk-devel swig expat-devel openssl-devel libXext libXft
yum install -y expat libedit postgresql-server python sendmail sudo tcl tk libical
yum install -y python-pip which net-tools wget python36 python36-devel libtool-ltdl-devel postgresql-contrib
wget "${DOWNLOAD_URL}/${OPENPBS_PKG}"
tar xzf ${OPENPBS_PKG}

cd $OPENPBS_FOLDER
./autogen.sh
./configure
make dist
mv $OPENPBS_DIST /root/rpmbuild/SOURCES
cp -f openpbs.spec /root/rpmbuild/SPECS
cd /root/rpmbuild/SPECS
rpmbuild -ba openpbs.spec 


