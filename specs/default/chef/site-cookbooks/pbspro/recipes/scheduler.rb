# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
#

pbsprover = node[:pbspro][:version]

package_name = "pbspro-server-#{pbsprover}.x86_64.rpm"

if node[:platform] == 'ubuntu'
  test_install = "dpkg -l | grep -q pbspro-server"
else
  test_install = "rpm -q pbspro-server"
end

jetpack_download package_name do
  project 'pbspro'
  # not_if "command -v pbsnodes"
  not_if test_install
end

yum_package package_name do
  source "#{node['jetpack']['downloads']}/#{package_name}"
  action :install
  # not_if "command -v pbsnodes"  
  not_if test_install
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


# Remove a pre-baked MOM config (if any)
replace_or_add 'replace PBS MOM clienthost if needed' do
  path "/var/spool/pbs/mom_priv/config"
  pattern "^.clienthost.*"
  line lazy { "$clienthost #{node[:hostname]}" }
  only_if {::File.exist?("/var/spool/pbs/mom_priv/config")}
end

replace_or_add 'replace PBS_SERVER if needed' do
  path "/etc/pbs.conf"
  pattern "^PBS_SERVER.*"
  line lazy { "PBS_SERVER=#{node[:hostname]}" }
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

service "pbs" do
  action :restart
  not_if { ::File.exist?("/etc/qmgr.config") }
end

execute "serverconfig" do
  command "/var/spool/pbs/doqmgr.sh && /var/spool/pbs/modify_limits.sh && touch /etc/qmgr.config"
  creates "/etc/qmgr.config"
  notifies :restart, 'service[pbs]', :delayed
end

include_recipe "pbspro::autostart"
include_recipe "pbspro::submit_hook"
