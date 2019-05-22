# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
#

pbsprover = node[:pbspro][:version]

package_name = "pbspro-client-#{pbsprover}.x86_64.rpm"

jetpack_download package_name do
  project 'pbspro'
end

yum_package package_name do
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
