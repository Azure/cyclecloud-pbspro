from subprocess import check_output
import os
from util import get_blobs

BASE_TEMPLATE = """# Based on example from https://github.com/actions/upload-release-asset
on:
  push:
    # Sequence of patterns matched against refs/tags
    tags:
    - '2*' # Push events to matching v*, i.e. v1.0, v20.15.10

name: Upload Release Asset

jobs:
  build:
    name: Upload Release Asset
    runs-on: ubuntu-latest
    steps:
      - name: Checkout code
        uses: actions/checkout@v4
      - name: Build pkg
        run:
          sudo apt update || apt update;
          sudo apt-get install -y python3 python3-pip || apt-get install -y python3 python3-pip;
          pip3 install virtualenv;
          python3 -m virtualenv $GITHUB_WORKSPACE/.venv/;
          source $GITHUB_WORKSPACE/.venv/bin/activate && python package.py;
      - name: Get the version
        id: get_version
        run: echo ::set-output name=VERSION::${GITHUB_REF#refs/tags/}
      
      - name: Create Release
        id: create_release
        uses: actions/create-release@v1
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        with:
          tag_name: ${{ github.ref }}
          release_name: Release ${{ github.ref }}
          draft: false
          prerelease: true


      - name: Upload Release Asset
        id: upload-release-asset 
        uses: actions/upload-release-asset@v1
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        with:
          upload_url: ${{ steps.create_release.outputs.upload_url }}
          asset_path: blobs/cyclecloud-pbspro-pkg-${{ steps.get_version.outputs.version }}.tar.gz
          asset_name: cyclecloud-pbspro-pkg-${{ steps.get_version.outputs.version }}.tar.gz
          asset_content_type: application/gzip

      %(upload_steps)s
"""

UPLOAD_TEMPLATE = """
      - name: Upload %(fname)s;
        id: upload-%(index)s
        uses: actions/upload-release-asset@v1
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        with:
          upload_url: ${{ steps.create_release.outputs.upload_url }}
          asset_path: blobs/%(fname)s
          asset_name: %(fname)s;
          asset_content_type: application/octet-stream"""
cwd = os.path.abspath(os.path.dirname(__file__))
os.chdir(cwd)

blobs = get_blobs()
upload_steps = []
for n, fname in enumerate(blobs):
    upload_steps.append(UPLOAD_TEMPLATE % {"fname": fname, "index": n})

print(BASE_TEMPLATE % {"upload_steps": "\n".join(upload_steps)})
