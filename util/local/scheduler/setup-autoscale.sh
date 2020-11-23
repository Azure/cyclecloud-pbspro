sed -r 's/^\$clienthost.+$/$clienthost docker-desktop/g' -i /var/spool/pbs/mom_priv/config 
eth0_ip=$(ifconfig eth0  | grep "inet " | python -c 'import sys; print(sys.stdin.read().split()[1])')
eth0_hostname=$(getent hosts ${eth0_ip} | python -c 'import sys; print(sys.stdin.read().split()[1]).lower()')
eth0_hostname_short=$(echo ${eth0_hostname} | cut -d. -f 1)
echo ${eth0_ip} ${eth0_hostname} ${eth0_hostname_short}  >> /etc/hosts
grep -q PBS_LEAF_NAME /etc/pbs.conf || echo 'PBS_LEAF_NAME='${eth0_hostname} >> /etc/pbs.conf
/etc/init.d/pbs start

echo 'export PATH=$PATH:/opt/pbs/bin' > /etc/profile.d/ccpbs.sh
source /etc/profile.d/ccpbs.sh
echo source /etc/profile.d/ccpbs.sh >> ~/.bash_profile

qmgr -c "set sched default only_explicit_psets = true"


tar xzf ~/blobs/cyclecloud-pbspro-pkg*.tar.gz
cd cyclecloud-pbspro
./install.sh --install-python3

export PYTHONPATH=/source/src:/scalelib/src

source ~/util/scheduler-settings.sh
azpbs initconfig --username $USERNAME \
                 --password $PASSWORD \
                 --url $WEB_URL \
                 --cluster-name $CLUSTER_NAME \
                 --default-resource '{"select": {}, "name": "disk", "value": "20g"}' \
                 --default-resource '{"select": {}, "name": "slot_type", "value": "node.nodearray"}' \
                 --default-resource '{"select": {}, "name": "mem", "value": "node.memory"}' \
                 --log-config /opt/cycle/pbspro//logging.conf > /opt/cycle/pbspro/autoscale.json


grep -q 'edited by setup-autoscale.sh' /etc/hosts && exit 0

cat > /tmp/hosts_hack.py <<EOF
import os
start = tuple([int(x) for x in os.getenv("SUBNET_START").split(".")])
end = tuple([int(x) for x in os.getenv("SUBNET_END").split(".")])

i = start
while i <= end:
    host = "ip-" + ("".join([ "{0:0{1}x}".format(x, 2) for x in i])).upper()
    print(".".join([str(x) for x in i]), host)
    i = (i[0], i[1], i[2], i[3] + 1)
EOF
python3 /tmp/hosts_hack.py >> /etc/hosts
echo '# edited by setup-autoscale.sh' >> /etc/hosts