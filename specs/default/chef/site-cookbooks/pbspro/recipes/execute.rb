# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
#

pbsprover = node[:pbspro][:version]
plat_ver = node['platform_version'].to_i
pbsdist = "el#{plat_ver}"

if pbsprover.to_i < 20 
  package_name = "pbspro-execution-#{pbsprover}.x86_64.rpm"
else
  package_name = "openpbs-execution-#{pbsprover}.#{pbsdist}.x86_64.rpm"
end

jetpack_download package_name do
  project 'pbspro'
end

yum_package package_name do
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

schedint = cluster.scheduler.split(".").first
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

bash "add-node-to-scheduler" do
  code lazy {"/opt/pbs/bin/qmgr -c 'c n #{node[:hostname]}'"}
  only_if do
    cmd = Mixlib::ShellOut.new('/opt/pbs/bin/pbsnodes -a')
    list_of_pbs_nodes = cmd.run_command.stdout.strip().split("\n")
    !list_of_pbs_nodes.include?(node[:hostname])
  end
  not_if {::File.exist?(node_created_guard)}
end

defer_block 'Defer setting core count and slot_type, and start of PBS pbs_mom until end of converge' do
  execute "set-node-core-count" do
    command lazy { "/opt/pbs/bin/qmgr -c 's n #{node[:hostname]} resources_available.ncpus=#{slots}'" }
    only_if { !slots.nil? }
    not_if {::File.exist?(node_created_guard)}
  end
  execute "set-node-free" do
    command lazy { "/opt/pbs/bin/pbsnodes -r #{node[:hostname]}"}
    not_if {::File.exist?(node_created_guard)}
  end

  set_slot_type = "/opt/pbs/bin/qmgr -c 's n #{node[:hostname]} resources_available.slot_type=#{slot_type}'"
  set_nodearray = "/opt/pbs/bin/qmgr -c 's n #{node[:hostname]} resources_available.nodearray=#{nodearray}'"
  set_machinetype = "/opt/pbs/bin/qmgr -c 's n #{node[:hostname]} resources_available.machinetype=#{machinetype}'"
  set_ungrouped = "true"

  if not is_node_grouped then
  	# user data explicitly says this is an ungrouped node.
  	set_ungrouped = "/opt/pbs/bin/qmgr -c 's n #{node[:hostname]} resources_available.ungrouped=true'"
  else
  	if placement_group then
  		# user data didn't explicitly say this was an ungrouped node, but we are in a placement group
  		set_ungrouped = "/opt/pbs/bin/qmgr -c 's n #{node[:hostname]} resources_available.ungrouped=false'"
  	else
  		# user data didn't explicitly say this was an ungrouped node, but we aren't in a placement group
  		set_ungrouped = "/opt/pbs/bin/qmgr -c 's n #{node[:hostname]} resources_available.ungrouped=true'"
  	end
  end
 
  set_group_id = "true"
  if placement_group then
    set_group_id = "/opt/pbs/bin/qmgr -c 's n #{node[:hostname]} resources_available.group_id=#{placement_group}'"
  end
 
  set_instance_id = "/opt/pbs/bin/qmgr -c 's n #{node[:hostname]} resources_available.instance_id=#{instance_id}'"

  if custom_resources.empty? || custom_resources.nil? then
    set_custom_resources = "true"
  else
    custom_resources.delete("disabled")
    if custom_resources.empty? then
        set_custom_resources = "true"
    else    
        set_custom_resources = custom_resources.map{ |key, value| "/opt/pbs/bin/qmgr -c 's n #{node[:hostname]} resources_available.#{key}=#{value}'"}.join(" && ")
    end
  end

  execute "modify_limits" do
    command "/var/spool/pbs/modify_limits.sh && touch /etc/modify_limits.config"
    creates "/etc/modify_limits.config"
  end
  
  
  execute "set-node-slot_type" do
    command lazy {<<-EOS
      #{set_slot_type} && \
      #{set_nodearray} && \
      #{set_group_id} && \
      #{set_ungrouped} && \
      #{set_instance_id} && \
      #{set_machinetype} && \
      #{set_custom_resources} && \
      touch #{node_created_guard}
      EOS
    }
    creates node_created_guard
    notifies :restart, 'service[pbs]', :immediately
  end
end

service "pbs" do
  action :nothing
end

include_recipe "pbspro::autostop"
