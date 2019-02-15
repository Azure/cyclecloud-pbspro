#
# Cookbook Name:: pbspro
# Recipe:: skel
#
# Copyright 2017, Cycle Computing
#
# All rights reserved - Do Not Redistribute

directory "/etc/skel/demo" do
  owner "root"
  group "root"
  mode "0755"
  action :create
  recursive true
  not_if "test -d /etc/skel/demo"
end

%w{pi.py pi.sh runpi.sh}.each do |myfile|
  cookbook_file "/etc/skel/demo/#{myfile}" do
    source myfile
    owner "root"
    group "root"
    mode "0755"
   action :create
  end
end
