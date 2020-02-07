# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
#
name "pbspro_master_role"
description "Open PBSPro Master Role"
run_list("role[scheduler]",
  "recipe[cuser]",
  "recipe[pbspro::skel]",
  "recipe[pbspro::scheduler]")

default_attributes "cyclecloud" => { "discoverable" => true }
