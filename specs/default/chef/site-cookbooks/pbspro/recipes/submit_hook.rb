# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
#

cookbook_file "#{node[:pbspro][:autoscale_project_home]}/submit_hook.py" do
    source "submit_hook.py"
    mode "0755"
    owner "root"
    group "root"
end
  
file "#{node[:pbspro][:autoscale_project_home]}/submit_hook.json" do
    mode "0644"
    owner "root"
    group "root"
    content Chef::JSONCompat.to_json_pretty(node[:pbspro][:submit_hook])
end


bash "import submit hook" do
    code <<-EOH
    /opt/pbs/bin/qmgr -c "create hook cycle_sub_hook" 2>/dev/null || true
    /opt/pbs/bin/qmgr -c "set hook cycle_sub_hook event = queuejob" 2>/dev/null || true
    /opt/pbs/bin/qmgr -c "create hook cycle_sub_periodic_hook" 2>/dev/null || true
    /opt/pbs/bin/qmgr -c "set hook cycle_sub_periodic_hook event = periodic" 2>/dev/null || true
    /opt/pbs/bin/qmgr -c "set hook cycle_sub_periodic_hook freq = 15"  2>/dev/null || true
    
    set -e
    /opt/pbs/bin/qmgr -c "import hook cycle_sub_hook application/x-python default #{node[:pbspro][:autoscale_project_home]}/submit_hook.py"
    /opt/pbs/bin/qmgr -c "import hook cycle_sub_hook application/x-config default #{node[:pbspro][:autoscale_project_home]}/hook_config.json"
    /opt/pbs/bin/qmgr -c "import hook cycle_sub_periodic_hook application/x-python default #{node[:pbspro][:autoscale_project_home]}/submit_hook.py"
    /opt/pbs/bin/qmgr -c "import hook cycle_sub_periodic_hook application/x-config default #{node[:pbspro][:autoscale_project_home]}/hook_config.json"
    EOH
    only_if { node[:pbspro][:submit_hook][:enabled] }

    notifies :restart, "service[pbs]", :delayed
end
