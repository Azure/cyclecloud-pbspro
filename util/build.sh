#!/usr/bin/env bash
set -e
set -x

if [ "$1" == "-h" ] || [ "$1" == "--help" ] || [ "$1" == "-help" ]; then
    echo "Usage: $0 [path/to/scalelib repo]"
    echo "If no path to scalelib is passed in, one will be downloaded from GitHub based on"
    echo "the version specified in package.py:SCALELIB_VERSION"
    exit 1
fi

LOCAL_SCALELIB=$1

if [ "$LOCAL_SCALELIB" != "" ]; then
    LOCAL_SCALELIB=$(realpath $LOCAL_SCALELIB)
fi

cwd=$(dirname "$(readlink -f "$0")")
SOURCE=$(dirname $cwd)

if [ ! -e $SOURCE/blobs ]; then
    mkdir $SOURCE/blobs
fi


cd $SOURCE
rm -f dist/*
./package.sh
mv dist/* blobs/
