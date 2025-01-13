#!/bin/bash

# create a new venv if it does not exist, or is older than 7 days
if [ ! $(find . -path ./venv/created -mtime -7) ]; then
    rm -rf venv
    python3 -m venv venv
    source venv/bin/activate
    pip install setuptools
    touch venv/created
else
    source venv/bin/activate
fi

python package.py 

if [[ -z "$GITHUB_REF" ]]; then
    echo "Generating release.yml..."
    python generate_release_yaml.py > .github/workflows/release.yml
fi
