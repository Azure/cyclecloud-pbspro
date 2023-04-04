# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
#

plat_ver = node['platform_version'].to_i

if plat_ver >= 8
  hwlocs_lib_el8 = node[:pbspro][:hwlocs_lib_el8]
  jetpack_download hwlocs_lib_el8 do
    project 'pbspro'
  end
  
  package hwlocs_lib_el8 do
    source "#{node['jetpack']['downloads']}/#{hwlocs_lib_el8}"
    action :install
  end
end
