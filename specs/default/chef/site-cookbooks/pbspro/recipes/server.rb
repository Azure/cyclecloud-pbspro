# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
#

include_recipe 'pbspro::default'

pbsprover = node[:pbspro][:version]
plat_ver = node['platform_version'].to_i
pbsdist = "el#{plat_ver}"
pbs_professional = node[:pbspro][:professional]
pbsdata_uid = node[:pbspro][:pbsdata_uid]
pbsdata_gid = node[:pbspro][:pbsdata_gid]

cron_method = node[:pbspro][:cron_method] || "pbs_cron"
package_name = node[:pbspro][:package]

ignore_workq = node[:pbspro][:queues][:workq][:ignore] || false
ignore_htcq = node[:pbspro][:queues][:htcq][:ignore] || false

ignored_queues = []
if ignore_workq
  ignored_queues.push("workq")
end

if ignore_htcq
  ignored_queues.push("htcq")
end

if !ignored_queues.empty?
  ignore_queues_arg = "--ignore-queues " + ignored_queues.join(",") 
else
  ignore_queues_arg = ""
end

if package_name.nil?
  if pbs_professional
    package_name = "pbspro-server-#{pbsprover}.#{pbsdist}.x86_64.rpm"
  else
    if pbsprover.to_i < 20 
      package_name = "pbspro-server-#{pbsprover}.x86_64.rpm"
    else
      package_name = "openpbs-server-#{pbsprover}.x86_64.rpm"
    end
  end
end

jetpack_download package_name do
  project 'pbspro'
end

if pbs_professional
  group 'pbsdata' do
    gid pbsdata_gid
    system true
  end

  user 'pbsdata' do
    system true
    uid pbsdata_uid
    gid 'pbsdata'
    manage_home true
    home '/home/pbsdata'
    shell '/bin/bash'
  end
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

# Create parent directory structure
directory '/var/spool/pbs'

# Create sched_priv directory before attempting
# to write config to that location.
directory '/var/spool/pbs/sched_priv' do
  mode 0o750
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

if pbs_professional
pbspro_license = node[:pbspro][:license]
  bash 'setup license cyclecloud-pbspro' do
    code <<-EOH
     /opt/pbs/bin/qmgr -c 'set server pbs_license_info=#{pbspro_license}'  
    EOH

    action :run
  end
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
  export PATH=$PATH:/root/bin
  set -x
  set -e

  cd #{node[:cyclecloud][:bootstrap]}/

  rm -f #{node[:pbspro][:autoscale_installer]} 2> /dev/null

  jetpack download #{node[:pbspro][:autoscale_installer]} --project pbspro ./
  
  if [ -e cyclecloud-pbspro ]; then
    rm -rf cyclecloud-pbspro/
  fi

  tar xzf #{node[:pbspro][:autoscale_installer]}

  cd cyclecloud-pbspro/
  
  INSTALLDIR=$(realpath #{node[:pbspro][:autoscale_project_home]})
  mkdir -p $INSTALLDIR/venv

  ./initialize_pbs.sh

  ./initialize_default_queues.sh

  ./install.sh --install-python3 --venv $INSTALLDIR/venv --cron-method #{cron_method}
  
  ./generate_autoscale_json.sh --install-dir $INSTALLDIR \
                                --username #{node[:cyclecloud][:config][:username]} \
                                --password "#{node[:cyclecloud][:config][:password]}" \
                                --url #{node[:cyclecloud][:config][:web_server]} \
                                --cluster-name #{node[:cyclecloud][:cluster][:name]} \
                                #{ignore_queues_arg}

  ls #{node[:pbspro][:autoscale_project_home]}/autoscale.json || exit 1
  azpbs connect || exit 1
  EOH

  action :run
  notifies :restart, 'service[pbs]', :delayed
end
