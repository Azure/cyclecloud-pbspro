# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
#
name "pbspro_server_role"
description "Open PBSPro Server Role"
run_list("role[scheduler]",
  "recipe[cshared::directories]",
  "recipe[pbspro::skel]",
  "recipe[cuser]",
  "recipe[cshared::server]",
  "recipe[pbspro::server]",
  "recipe[cganglia::server]")

default_attributes "cyclecloud" => { "discoverable" => true }
