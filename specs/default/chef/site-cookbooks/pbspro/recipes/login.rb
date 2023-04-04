# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
#

include_recipe 'pbspro::default'

pbsprover = node[:pbspro][:version]
plat_ver = node['platform_version'].to_i
pbsdist = "el#{plat_ver}"
pbs_professional = node[:pbspro][:professional]
package_name = node[:pbspro][:package]


if package_name.nil?
  if pbs_professional
    package_name = "pbspro-client-#{pbsprover}.#{pbsdist}.x86_64.rpm"
  else
    if pbsprover.to_i < 20 
      package_name = "pbspro-client-#{pbsprover}.x86_64.rpm"
    else
      package_name = "openpbs-client-#{pbsprover}.x86_64.rpm"
    end
  end
end

jetpack_download package_name do
  project 'pbspro'
end

package package_name do
  source "#{node['jetpack']['downloads']}/#{package_name}"
  action :install
end

schedint = cluster.scheduler

if schedint != nil
  template "/etc/pbs.conf" do
    source "pbs.conf.erb"
    mode "0644"
    owner "root"
    group "root"
    variables(:servername => schedint)
  end
end

execute 'set_flatuid' do
  command '/opt/pbs/bin/qmgr -c "set server flatuid=true"'
end
