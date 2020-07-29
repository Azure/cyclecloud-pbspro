# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
#

pbsprover = node[:pbspro][:version]
plat_ver = node['platform_version'].to_i
pbsdist = "el#{plat_ver}"

if pbsprover.to_i < 20 
  package_name = "pbspro-server-#{pbsprover}.x86_64.rpm"
else
  package_name = "openpbs-server-#{pbsprover}.#{pbsdist}.x86_64.rpm"
end

jetpack_download package_name do
  project 'pbspro'
end

yum_package package_name do
  source "#{node['jetpack']['downloads']}/#{package_name}"
  action :install
end

directory "#{node[:cyclecloud][:bootstrap]}/pbs" do
  owner "root"
  group "root"
  mode "0755"
  action :create
end

# Create parent directory structure
directory '/var/spool/pbs'

# Create sched_priv directory before attempting
# to write config to that location.
directory '/var/spool/pbs/sched_priv' do
  mode 0o750
end

cookbook_file "/var/spool/pbs/doqmgr.sh" do
  source "doqmgr.sh"
  mode "0755"
  owner "root"
  group "root"
  action :create
end

cookbook_file "/var/spool/pbs/modify_limits.sh" do
  source "modify_limits.sh"
  mode "0755"
  owner "root"
  group "root"
  action :create
end

cookbook_file "/var/spool/pbs/sched_priv/sched_config" do
  source "sched.config"
  owner "root"
  group "root"
  mode "0644"
end

service "pbs" do
  action [:enable, :start]
end

execute "serverconfig" do
  command "/var/spool/pbs/doqmgr.sh && /var/spool/pbs/modify_limits.sh && touch /etc/qmgr.config"
  creates "/etc/qmgr.config"
  notifies :restart, 'service[pbs]', :delayed
end

include_recipe "pbspro::autostart"
include_recipe "pbspro::submit_hook"
