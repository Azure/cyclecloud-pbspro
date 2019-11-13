# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
#
name "pbspro_login_role"
description "PBSPro Login Role"
run_list("recipe[cshared::client]",
  "recipe[cuser]",
  "recipe[pbspro::login]",
  "recipe[cganglia::client]")
