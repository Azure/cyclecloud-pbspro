#!/bin/bash
set -e
yum install -y which less crontabs.noarch ~/blobs/pbspro*server*rpm
/etc/init.d/pbs start


