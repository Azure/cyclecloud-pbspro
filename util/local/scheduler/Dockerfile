FROM centos:7
COPY installers/pbspro-server-18.1.4-0.x86_64.rpm /installers/

RUN yum install -y which less crontabs.noarch /installers/pbspro*server*rpm &&     echo 'export PATH=/usr/local/Cellar/ruby/2.7.1_2/bin/:/usr/local/Cellar/ruby/2.7.1_2/lib/ruby/gems/2.7.0/gems/rake-13.0.1/bin/:/usr/local/lib/ruby/gems/2.7.0/gems/reek-6.0.0/bin/:/Library/Frameworks/Python.framework/Versions/3.8/bin:/Library/Frameworks/Python.framework/Versions/2.7/bin:/Users/ryhamel/bin:/usr/local/Cellar/gnupg@2.0/2.0.31/bin:/usr/local/Cellar/python/2.7.13/bin:/usr/local/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:/Users/ryhamel/bin:/Users/ryhamel/Applications/packer_0.8.6_darwin_amd64:/Users/ryhamel/cs_installs/current:/opt/pbs/bin' > /etc/profile.d/ccpbs.sh &&     sed -r s/^PBS_SERVER=.+$/PBS_SERVER=docker-desktop/g -i /etc/pbs.conf &&     sed -r 's/^$clienthost.+$/ docker-desktop/g' -i /var/spool/pbs/mom_priv/config &&     echo docker-desktop > /var/spool/pbs/server_name

