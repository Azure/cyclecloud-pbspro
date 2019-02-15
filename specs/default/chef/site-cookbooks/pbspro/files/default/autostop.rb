#!/usr/bin/env ruby

# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
#

require 'json'

# Arguments
AUTOSTOP_ENABLED = `jetpack config cyclecloud.cluster.autoscale.stop_enabled`.downcase.strip == "true"

# Short-circuit without error if not enabled
exit 0 unless AUTOSTOP_ENABLED

IDLE_TIME_AFTER_JOBS = `jetpack config cyclecloud.cluster.autoscale.idle_time_after_jobs`.to_i
IDLE_TIME_BEFORE_JOBS = `jetpack config cyclecloud.cluster.autoscale.idle_time_before_jobs`.to_i

# Checks to see if we should shutdown
idle_long_enough = false

# indicates if execute node has ever ran a job
def been_active?
  # Shell out to grep with -m 1 for lazy match, as the log files can grow quite large
  # and we only need to know if one job has ever started.
  any_job = `egrep -m 1 ';pbs_mom;Job;.+;Started' /var/spool/pbs/mom_logs/*`.strip
  any_job.length > 0
end

# indicates if there are currently running jobs
def active?
  activejobs = Dir.glob('/var/spool/pbs/mom_priv/jobs/*').count
  activejobs > 0
end

# This is our autoscale runtime configuration
runtime_config = {"idle_start_time" => nil}


AUTOSCALE_DATA = '/opt/cycle/jetpack/run/autoscale.json'.freeze

if File.exist?(AUTOSCALE_DATA)
  file = File.read(AUTOSCALE_DATA)
  runtime_config.merge!(JSON.parse(file))
end

if active?
  runtime_config["idle_start_time"] = nil
elsif runtime_config["idle_start_time"].nil?
  runtime_config["idle_start_time"] = Time.now.to_i
else
  idle_seconds = Time.now - Time.at(runtime_config["idle_start_time"].to_i)

  # Different timeouts if the node has ever run a job
  timeout = if been_active?
              IDLE_TIME_AFTER_JOBS
            else
              IDLE_TIME_BEFORE_JOBS
            end

  idle_long_enough = idle_seconds > timeout
end

# Write the config information back for next time
file = File.new(AUTOSCALE_DATA, "w")
file.puts JSON.pretty_generate(runtime_config)
file.close

# Do the shutdown
if idle_long_enough
  myhost = `hostname`
  system("bash -lc 'pbsnodes -o #{myhost}'")
  sleep(5)
  system("jetpack shutdown --idle")
end
