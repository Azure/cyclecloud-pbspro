# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
#


project_home="#{node[:cyclecloud][:home]}/../pbspro"

cookbook_file "#{project_home}/autoscale_hook.py" do
  source "autoscale_hook.py"
  mode "0755"
  owner "root"
  group "root"
end

file "#{project_home}/hook_config.json" do
  mode "0644"
  owner "root"
  group "root"
  content Chef::JSONCompat.to_json_pretty(node[:pbspro][:autoscale_hook])
end

bash "import autoscale hook" do
  code <<-EOH
    set -
    /opt/pbs/bin/qmgr -c "create hook autoscale" 1>&2 || true
    /opt/pbs/bin/qmgr -c "import hook autoscale application/x-python default #{project_home}/autoscale_hook.py"
    /opt/pbs/bin/qmgr -c "import hook autoscale application/x-config default #{project_home}/hook_config.json"
    /opt/pbs/bin/qmgr -c "set hook autoscale event = periodic"
    /opt/pbs/bin/qmgr -c "set hook autoscale freq = 15"
  EOH
  only_if { node[:cyclecloud][:cluster][:autoscale][:start_enabled] }

  notifies :restart, 'service[pbs]', :delayed
end
