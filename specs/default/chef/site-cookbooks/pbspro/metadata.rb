# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
#
name             "pbspro"
maintainer       "Microsoft Corporation"
license          "MIT"
description      "Installs/Configures Open PBS Pro"
long_description IO.read(File.join(File.dirname(__FILE__), 'README.md'))
version          "0.1"
depends          "tandem"
%w{ cganglia cshared cuser cyclecloud }.each {|c| depends c}

