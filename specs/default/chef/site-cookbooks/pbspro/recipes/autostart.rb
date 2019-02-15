# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
#
cookbook_file "#{node[:cyclecloud][:bootstrap]}/pbs/autostart.py" do
    source "autostart.py"
    mode "0755"
    owner "root"
    group "root"
end

cookbook_file "#{node[:cyclecloud][:bootstrap]}/pbs/autostart_hook.py" do
  source "autostart_hook.py"
  mode "0755"
  owner "root"
  group "root"
end

cookbook_file "#{node[:cyclecloud][:bootstrap]}/pbs/logging_init.py" do
  source "logging_init.py"
  mode "0755"
  owner "root"
  group "root"
end

cookbook_file "#{node[:cyclecloud][:bootstrap]}/pbs/mockpbs.py" do
  source "mockpbs.py"
  mode "0755"
  owner "root"
  group "root"
end

cookbook_file "#{node[:cyclecloud][:bootstrap]}/pbs/pbscc.py" do
  source "pbscc.py"
  mode "0755"
  owner "root"
  group "root"
end

file "#{node[:cyclecloud][:bootstrap]}/pbs/autostart.json" do
  mode "0644"
  owner "root"
  group "root"
  content Chef::JSONCompat.to_json_pretty(node[:pbspro][:autoscale_hook])
end

bash "import autoscale hook" do
  code <<-EOH
    set -e
    /opt/pbs/bin/qmgr -c "create hook autoscale" 1>&2 || true
    /opt/pbs/bin/qmgr -c "import hook autoscale application/x-python default #{node[:cyclecloud][:bootstrap]}/pbs/autostart_hook.py"
    /opt/pbs/bin/qmgr -c "import hook autoscale application/x-config default #{node[:cyclecloud][:bootstrap]}/pbs/autostart.json"
    /opt/pbs/bin/qmgr -c "set hook autoscale event = periodic"
    /opt/pbs/bin/qmgr -c "set hook autoscale freq = 15"
    touch #{node[:cyclecloud][:bootstrap]}/pbs/autoscalehook.imported
  EOH
  creates "#{node[:cyclecloud][:bootstrap]}/pbs/autoscalehook.imported"
  only_if { node[:cyclecloud][:cluster][:autoscale][:start_enabled] }

  notifies :restart, 'service[pbs]', :delayed
end
