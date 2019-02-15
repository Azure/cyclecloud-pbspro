name             "pbspro"
maintainer       "Cycle Computing, LLC."
maintainer_email "support@cyclecomputing.com"
license          "Apache 2.0"
description      "Installs/Configures Open PBS Pro"
long_description IO.read(File.join(File.dirname(__FILE__), 'README.md'))
version          "0.1"
depends          "tandem"
%w{ cganglia cshared cuser cyclecloud }.each {|c| depends c}

