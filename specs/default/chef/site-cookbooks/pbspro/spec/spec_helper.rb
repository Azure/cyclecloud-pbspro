# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
#
require 'chefspec'
require 'fauxhai'

RSpec.configure do |config|
  config.log_level = :error
  config.cookbook_path = ['../../cookbooks', '../../berks-cookbooks']
end

# /usr/sbin isn't in the PATH when these tests are executed by jenkins
if !ENV['PATH'].include?('/usr/sbin')
  ENV['PATH'] = ENV['PATH'] + ':/usr/sbin'
end

# This makes it possible to test Chef libraries
Dir['libraries/*.rb'].each { |f| require File.expand_path(f) }

at_exit { ChefSpec::Coverage.report! }
