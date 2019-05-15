# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
#

cookbook_file "#{node[:cyclecloud][:bootstrap]}/pbs/submit_hook.py" do
    source "submit_hook.py"
    mode "0755"
    owner "root"
    group "root"
end
  
file "#{node[:cyclecloud][:bootstrap]}/pbs/submit_hook.json" do
    mode "0644"
    owner "root"
    group "root"
    content Chef::JSONCompat.to_json_pretty(node[:pbspro][:submit_hook])
end

# required by "tandem::install_driver"

cookbook_file "#{node[:cyclecloud][:bootstrap]}/pbs/pbs_driver.py" do
    source "pbs_driver.py"
    mode "0755"
    owner "root"
    group "root"
end


node.default[:tandem_driver_directory] = "#{node[:cyclecloud][:bootstrap]}/pbs"
include_recipe "tandem::install_driver"

bash "import submit hook" do
    code <<-EOH
    /opt/pbs/bin/qmgr -c "create hook cycle_sub_hook" 2>/dev/null || true
    /opt/pbs/bin/qmgr -c "set hook cycle_sub_hook event = queuejob" 2>/dev/null || true
    /opt/pbs/bin/qmgr -c "create hook cycle_sub_periodic_hook" 2>/dev/null || true
    /opt/pbs/bin/qmgr -c "set hook cycle_sub_periodic_hook event = periodic" 2>/dev/null || true
    /opt/pbs/bin/qmgr -c "set hook cycle_sub_periodic_hook freq = 15"  2>/dev/null || true
    
    set -e
    /opt/pbs/bin/qmgr -c "import hook cycle_sub_hook application/x-python default #{node[:cyclecloud][:bootstrap]}/pbs/submit_hook.py"
    /opt/pbs/bin/qmgr -c "import hook cycle_sub_hook application/x-config default #{node[:cyclecloud][:bootstrap]}/pbs/submit_hook.json"
    /opt/pbs/bin/qmgr -c "import hook cycle_sub_periodic_hook application/x-python default #{node[:cyclecloud][:bootstrap]}/pbs/submit_hook.py"
    /opt/pbs/bin/qmgr -c "import hook cycle_sub_periodic_hook application/x-config default #{node[:cyclecloud][:bootstrap]}/pbs/submit_hook.json"
        touch #{node[:cyclecloud][:bootstrap]}/pbs/submithook.imported
    EOH
    creates "#{node[:cyclecloud][:bootstrap]}/pbs/submithook.imported"
    only_if { node[:pbspro][:submit_hook][:enabled] }

    notifies :restart, "service[pbs]", :delayed
end
