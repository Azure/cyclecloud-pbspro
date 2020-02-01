# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
#
name "pbspro_login_role"
description "PBSPro Login Role"
run_list("recipe[pbspro::login]")
