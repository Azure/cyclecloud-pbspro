#!/bin/bash
set -e

# create a new venv if it does not exist, or is older than 7 days
if [ -z "$(find . -path ./venv/created -mtime -7 -print -quit)" ] ||
    ! venv/bin/python -c 'import sys; raise SystemExit(sys.version_info < (3, 11))' 2>/dev/null; then
    rm -rf venv
    python3 -m venv venv
    source venv/bin/activate
    python3 -m pip install setuptools
    touch venv/created
else
    source venv/bin/activate
fi

./docker-package.sh