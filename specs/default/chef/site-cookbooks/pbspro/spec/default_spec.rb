# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
#
require 'spec_helper'
require_relative "../../cyclecloud/libraries/cycle_cloud_cluster"

describe 'pbspro::execute' do
  platforms = {
    'centos' => ['6.8', '7.2.1511']
  }

  platforms.each do |platform, versions|
    versions.each do |version|
      context "On #{platform} #{version}" do
        cached(:chef_run) do
          ChefSpec::SoloRunner.new(platform: platform, version: version) do |node|
            node.default[:cyclecloud][:cluster][:autoscale][:stop_enabled] = true
            node.override[:pbspro][:version] = "test-version"
          end.converge(described_recipe)
        end

        before do
          pbs_stdout_double = double('pbs_stdout_double')
          allow(pbs_stdout_double).to receive(:stdout).and_return("")
          
          pbsnodes_double = double('pbsnodes_double')
          allow(pbsnodes_double).to receive(:run_command).and_return(pbs_stdout_double)
          
          allow(Mixlib::ShellOut).to receive(:new).with("/opt/pbs/bin/pbsnodes -a").and_return(pbsnodes_double)
          
          # here we mock the global `cluster.scheduler` method so that these
          # tests don't block forever trying to query a nonexistent CycleServer instance
          allow_any_instance_of(CycleCloudCluster).to receive(:scheduler).and_return('127.0.0.1')
        end

        it 'downloads pbspro installer' do
          expect(chef_run).to download_jetpack_download("pbspro-execution-test-version.x86_64.rpm")
        end
        
        it 'adds node to scheduler' do
          expect(chef_run).to run_bash("add-node-to-scheduler")
        end
        
        it 'creates cron autostop job' do
          expect(chef_run).to create_cron("autostop")
        end

      end
    end
  end
end


describe 'pbspro::scheduler' do
  platforms = {
    'centos' => ['6.8', '7.2.1511']
  }

  platforms.each do |platform, versions|
    versions.each do |version|
      context "On #{platform} #{version}" do
        cached(:chef_run) do
          ChefSpec::SoloRunner.new(platform: platform, version: version) do |node|
            node.default[:cyclecloud][:cluster][:autoscale][:stop_enabled] = true
            node.override[:pbspro][:version] = "test-version"
          end.converge(described_recipe)
        end

        before do
          pbs_stdout_double = double('pbs_stdout_double')
          allow(pbs_stdout_double).to receive(:stdout).and_return("")
          
          pbsnodes_double = double('pbsnodes_double')
          allow(pbsnodes_double).to receive(:run_command).and_return(pbs_stdout_double)
          
          allow(Mixlib::ShellOut).to receive(:new).with("/opt/pbs/bin/pbsnodes -a").and_return(pbsnodes_double)
          
          # here we mock the global `cluster.scheduler` method so that these
          # tests don't block forever trying to query a nonexistent CycleServer instance
          allow_any_instance_of(CycleCloudCluster).to receive(:scheduler).and_return('127.0.0.1')
        end

        it 'downloads pbspro installer' do
          expect(chef_run).to download_jetpack_download("pbspro-server-test-version.x86_64.rpm")
        end

        it 'executes serverconfig' do
          expect(chef_run).to run_execute("serverconfig")
        end

        it 'downloads pbspro installer' do
          expect(chef_run).to run_execute("serverconfig")
        end

        it 'enables and starts the pbs service' do
          expect(chef_run).to enable_service("pbs")
          expect(chef_run).to start_service("pbs")
        end

        ['pbspro::autostart', 'pbspro::submit_hook'].each do |recipe|
          it "includes #{recipe}" do
            expect(chef_run).to include_recipe(recipe)
          end
        end
        
      end
    end
  end
end

