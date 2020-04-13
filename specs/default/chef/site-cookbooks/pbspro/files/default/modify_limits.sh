#!/bin/bash
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
#
set -e

sed -i "s/^if /#if /g" /opt/pbs/lib/init.d/limits.pbs_mom
sed -i "s/^fi/#fi /g" /opt/pbs/lib/init.d/limits.pbs_mom