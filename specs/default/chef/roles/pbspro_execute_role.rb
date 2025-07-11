# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
#
name "pbspro_execute_role"
description "PBSPro Execute Role"
run_list("recipe[cshared::client]",
  "recipe[pbspro::execute]")
