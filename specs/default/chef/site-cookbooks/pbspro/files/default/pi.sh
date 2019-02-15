#!/bin/bash
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
#
#PBS -N pitest
#PBS -j oe

/shared/scratch/pi/pi.py 10000
