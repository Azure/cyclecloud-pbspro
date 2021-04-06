# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
#

pbsprover = node[:pbspro][:version]
plat_ver = node['platform_version'].to_i
pbsdist = "el#{plat_ver}"

if pbsprover.to_i < 20 
  package_name = "pbspro-execution-#{pbsprover}.x86_64.rpm"
else
  package_name = "openpbs-execution-#{pbsprover}.x86_64.rpm"
end

jetpack_download package_name do
  project 'pbspro'
end

package package_name do
  source "#{node['jetpack']['downloads']}/#{package_name}"
  action :install
end

nodearray = node[:cyclecloud][:node][:template] || "execute"
slot_type = node[:pbspro][:slot_type] || nodearray
machinetype = node[:azure][:metadata][:compute][:vmSize]

placement_group = node[:cyclecloud][:node][:placement_group_id] || node[:cyclecloud][:node][:placement_group] || nil
is_node_grouped = node[:pbspro][:is_hpc] || !placement_group.nil?
instance_id = node[:cyclecloud][:instance][:id]

custom_resources = Hash.new {}
if node[:autoscale] then
    custom_resources = node[:autoscale].to_h
end

schedint = (node[:pbspro][:scheduler] || cluster.scheduler).split(".").first
slots = node[:pbspro][:slots] || nil

if schedint != nil
  template "/var/spool/pbs/server_name" do
    source "server_name_exec.erb"
    mode "0644"
    owner "root"
    group "root"
    variables(:servername => schedint)
  end

  template "/var/spool/pbs/mom_priv/config" do
    source "mom_config.erb"
    mode "0644"
    owner "root"
    group "root"
    variables(:servername => schedint)
  end

  template "/etc/pbs.conf" do
    source "pbs.conf.erb"
    mode "0644"
    owner "root"
    group "root"
    variables(:servername => schedint)
  end
end


cookbook_file "/var/spool/pbs/modify_limits.sh" do
  source "modify_limits.sh"
  mode "0755"
  owner "root"
  group "root"
  action :create
end

node_created_guard = "#{node['cyclecloud']['chefstate']}/pbs.nodecreated"

bash "await-joining-cluster" do
  code lazy { "/opt/pbs/bin/pbsnodes -o #{node[:hostname]}"}
  only_if do 
    lazy {
      cmd = Mixlib::ShellOut.new('/opt/pbs/bin/pbsnodes -a')
      list_of_pbs_nodes = cmd.run_command.stdout.strip().split("\n")
      !list_of_pbs_nodes.include?(node[:hostname])
    }
  end
  not_if {::File.exist?(node_created_guard)}
end

defer_block 'Defer setting core count and slot_type, and start of PBS pbs_mom until end of converge' do

  execute "modify_limits" do
    command "/var/spool/pbs/modify_limits.sh && touch /etc/modify_limits.config"
    creates "/etc/modify_limits.config"
    notifies :restart, 'service[pbs]', :immediately
  end
  
end

service "pbs" do
  action :nothing
end
