export USERNAME=ryhamel
export PASSWORD=')ya58uRU0#m%'
export WEB_URL='http://172.155.155.2:8080'
export CLUSTER_NAME=pbs3
export SUBNET_START=10.1.0.4
export SUBNET_END=10.1.0.255

azpbs initconfig --username $USERNAME \
                 --password $PASSWORD \
                 --url $WEB_URL \
                 --cluster-name $CLUSTER_NAME \
                 --default-resource '{"select": {}, "name": "disk", "value": "20g"}' \
                 --default-resource '{"select": {}, "name": "slot_type", "value": "node.nodearray"}' \
                 --default-resource '{"select": {}, "name": "mem", "value": "node.memory"}' \
                 --log-config /source/conf/logging.conf > /opt/cycle/pbspro/autoscale.json

