# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
#

pbsprover = node[:pbspro][:version]
plat_ver = node['platform_version'].to_i
pbsdist = "el#{plat_ver}"

if pbsprover.to_i < 20 
  package_name = "pbspro-server-#{pbsprover}.x86_64.rpm"
else
  package_name = "openpbs-server-#{pbsprover}.x86_64.rpm"
end

jetpack_download package_name do
  project 'pbspro'
end

if plat_ver < 8
  yum_package package_name do
    source "#{node['jetpack']['downloads']}/#{package_name}"
    action :install
  end
else
  package package_name do
    source "#{node['jetpack']['downloads']}/#{package_name}"
    action :install
  end
end

directory "#{node[:pbspro][:autoscale_project_home]}" do
  owner "root"
  group "root"
  mode "0755"
  action :create
end

cookbook_file "#{node[:pbspro][:autoscale_project_home]}/logging.conf" do
  source "logging.conf"
  mode "0644"
  owner "root"
  group "root"
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

file "/etc/profile.d/azpbs_autocomplete.sh" do
  content 'eval "$(/opt/cycle/pbspro/venv/bin/register-python-argcomplete azpbs)" || echo "Warning: Autocomplete is disabled" 1>&2'
  mode '0755'
  owner 'root'
  group 'root'
end

bash 'setup cyclecloud-pbspro' do
  code <<-EOH
  source /etc/profile.d/pbs.sh
  set -e

  cd #{node[:cyclecloud][:bootstrap]}/

  rm -f #{node[:pbspro][:autoscale_installer]} 2> /dev/null

  jetpack download #{node[:pbspro][:autoscale_installer]} --project pbspro ./
  
  if [ -e cyclecloud-pbspro ]; then
    rm -rf cyclecloud-pbspro/
  fi

  tar xzf #{node[:pbspro][:autoscale_installer]}

  cd cyclecloud-pbspro/
  
  INSTALLDIR=#{node[:pbspro][:autoscale_project_home]}
  mkdir -p $INSTALLDIR/venv
  ./install.sh --install-python3 --venv $INSTALLDIR/venv
  
  azpbs initconfig --cluster-name #{node[:cyclecloud][:cluster][:name]} \
                  --username     #{node[:cyclecloud][:config][:username]} \
                  --password     #{node[:cyclecloud][:config][:password]} \
                  --url          #{node[:cyclecloud][:config][:web_server]} \
                  --lock-file    $INSTALLDIR/scalelib.lock \
                  --log-config   $INSTALLDIR/logging.conf \
                  --disable-default-resources \
                  --default-resource '{"select": {}, "name": "ncpus", "value": "node.pcpu_count"}' \
                  --default-resource '{"select": {}, "name": "ngpus", "value": "node.gpu_count"}' \
                  --default-resource '{"select": {}, "name": "disk", "value": "size::20g"}' \
                  --default-resource '{"select": {}, "name": "host", "value": "node.hostname"}' \
                  --default-resource '{"select": {}, "name": "slot_type", "value": "node.nodearray"}' \
                  --default-resource '{"select": {}, "name": "group_id", "value": "node.placement_group"}' \
                  --default-resource '{"select": {}, "name": "mem", "value": "node.memory"}' \
                  --default-resource '{"select": {}, "name": "vm_size", "value": "node.vm_size"}' \
                  --idle-timeout #{node[:pbspro][:idle_timeout]} \
                  --boot-timeout #{node[:pbspro][:boot_timeout]} \
                   > $INSTALLDIR/autoscale.json || exit 1


  ls #{node[:pbspro][:autoscale_project_home]}/autoscale.json || exit 1

  EOH

  action :run
end

include_recipe "pbspro::autoscale"
