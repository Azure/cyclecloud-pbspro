#!/bin/bash

source "${CYCLECLOUD_PROJECT_PATH}/default/files/default.sh" || exit 1
source "${CYCLECLOUD_PROJECT_PATH}/default/files/utils.sh" || exit 1
source "${CYCLECLOUD_PROJECT_PATH}/default/files/hwlocs-install.sh" || exit 1

PACKAGE_NAME=$(get_package_name "server") || fail
CLUSTER_NAME=$(jq -r .cluster "$CONFIG_PATH") || fail
CONNECTION_URL=$(jq -r .url "$CONFIG_PATH") || fail
IGNORE_WORKQ=$(jetpack config pbspro.queues.workq.ignore "False") || fail
IGNORE_HTCQ=$(jetpack config pbspro.queues.htcq.ignore "False") || fail
CRON_METHOD=$(jetpack config pbspro.cron_method "pbs_cron") || fail
PBSPRO_AUTOSCALE_PROJECT_HOME="/opt/cycle/pbspro" || fail
PBSPRO_AUTOSCALE_INSTALLER="cyclecloud-pbspro-pkg-${PBSPRO_AUTOSCALE_VERSION}.tar.gz" || fail

mkdir -p "/sched/${CLUSTER_NAME}" || fail

cat << EOF > "/sched/${CLUSTER_NAME}/azpbs.env"
#!/bin/bash
PBS_SCHEDULER_HOSTNAME=$(hostname)
PBS_SCHEDULER_IP=$(hostname -i)

EOF
chmod a+r "/sched/${CLUSTER_NAME}/azpbs.env" || fail

jetpack download --project pbspro "$PACKAGE_NAME" "/tmp" || fail # TODO: check for platform version?
yum install -y -q "/tmp/$PACKAGE_NAME" || fail # TODO: this is slow, won't work on all linux distros, and will not be final--Emily and Doug's install-package will be used instead

mkdir -p -m 0755 "$PBSPRO_AUTOSCALE_PROJECT_HOME" || fail

mkdir -p -m 750 /var/spool/pbs/sched_priv || fail

cp "${CYCLECLOUD_PROJECT_PATH}/default/templates/default/sched.config" /var/spool/pbs/sched_priv/sched_config || fail
chmod 0644 /var/spool/pbs/sched_priv/sched_config || fail

systemctl enable --now pbs || fail

source /etc/profile.d/pbs.sh || fail
export PATH=$PATH:/root/bin

cd "$BOOTSTRAP_HOME" || fail # TODO: find a new location instead of BOOTSTRAP_HOME

rm -f "$PBSPRO_AUTOSCALE_INSTALLER" 2> /dev/null || fail

jetpack download "$PBSPRO_AUTOSCALE_INSTALLER" --project pbspro ./ || fail

if [ -e cyclecloud-pbspro ]; then
    rm -rf cyclecloud-pbspro/ || fail
fi

tar xzf "$PBSPRO_AUTOSCALE_INSTALLER" || fail

cd cyclecloud-pbspro/ || fail

INSTALLDIR=$(realpath "$PBSPRO_AUTOSCALE_PROJECT_HOME") || fail
mkdir -p "${INSTALLDIR}/venv" || fail

IGNORE_QUEUES_ARG=""
if [[ "$IGNORE_WORKQ" == "True" && "$IGNORE_HTCQ" == "True" ]]; then
    IGNORE_QUEUES_ARG="--ignore-queues workq,htcq"
elif [[ "$IGNORE_WORKQ" == "True" ]]; then
    IGNORE_QUEUES_ARG="--ignore-queues workq"
elif [[ "$IGNORE_HTCQ" == "True" ]]; then
    IGNORE_QUEUES_ARG="--ignore-queues htcq"
fi

./initialize_pbs.sh || fail

./initialize_default_queues.sh || fail

./install.sh --install-python3 --venv "${INSTALLDIR}/venv" --cron-method "$CRON_METHOD" || fail

./generate_autoscale_json.sh --install-dir "$INSTALLDIR" \
                            --username "$(jetpack config cyclecloud.config.username)" \
                            --password "$(jetpack config cyclecloud.config.password)" \
                            --url "$CONNECTION_URL" \
                            --cluster-name "$CLUSTER_NAME" \
                            $IGNORE_QUEUES_ARG

ls "${PBSPRO_AUTOSCALE_PROJECT_HOME}/autoscale.json" || fail
azpbs connect || fail

systemctl restart pbs  || fail