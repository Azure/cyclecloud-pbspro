#!/bin/bash

source $CYCLECLOUD_PROJECT_PATH/default/files/default.sh || exit 1
source $CYCLECLOUD_PROJECT_PATH/default/files/utils.sh || exit 1
source $CYCLECLOUD_PROJECT_PATH/default/files/hwlocs-install.sh || exit 1

PACKAGE_NAME=$(jetpack config pbspro.package "") || fail
PBSPRO_AUTOSCALE_PROJECT_HOME="/opt/cycle/pbspro" || fail
CRON_METHOD=$(jetpack config pbspro.cron_method "pbs_cron") || fail
IGNORE_WORKQ=$(jetpack config pbspro.queues.workq.ignore "False") || fail
IGNORE_HTCQ=$(jetpack config pbspro.queues.htcq.ignore "False") || fail
PBSPRO_AUTOSCALE_INSTALLER="cyclecloud-pbspro-pkg-${PBSPRO_AUTOSCALE_VERSION}.tar.gz" || fail

if [[ -z "$PACKAGE_NAME" ]]; then
    if [[ "${PBSPRO_VERSION%%.*}" -lt 20 ]]; then
        PACKAGE_NAME="pbspro-server-${PBSPRO_VERSION}.x86_64.rpm"
    else
        PACKAGE_NAME="openpbs-server-${PBSPRO_VERSION}.x86_64.rpm"
    fi
fi

jetpack download --project pbspro "$PACKAGE_NAME" "/tmp" || fail # TODO: check for platoform version?
yum install -y "/tmp/$PACKAGE_NAME" || fail # TODO: this is slow, won't work on all linux distros, and will not be final--Emily and Doug's install-package will be used instead

mkdir -p "$PBSPRO_AUTOSCALE_PROJECT_HOME" || fail
chmod 0755 "$PBSPRO_AUTOSCALE_PROJECT_HOME" || fail

mkdir -p /var/spool/pbs || fail
mkdir -p -m 750 /var/spool/pbs/sched_priv || fail/

cp "${CYCLECLOUD_PROJECT_PATH}/default/templates/default/sched.config" /var/spool/pbs/sched_priv/sched_config || fail
chmod 0644 /var/spool/pbs/sched_priv/sched_config || fail

systemctl enable --now pbs || fail

source /etc/profile.d/pbs.sh || exit 1
export PATH=$PATH:/root/bin

cd "$(jetpack config cyclecloud.bootstrap)" || fail

rm -f "$PBSPRO_AUTOSCALE_INSTALLER" 2> /dev/null || fail

jetpack download "$PBSPRO_AUTOSCALE_INSTALLER" --project pbspro ./ || fail

if [ -e cyclecloud-pbspro ]; then
    rm -rf cyclecloud-pbspro/ || fail
fi

tar xzf "$PBSPRO_AUTOSCALE_INSTALLER" || fail

cd cyclecloud-pbspro/

INSTALLDIR=$(realpath "$PBSPRO_AUTOSCALE_PROJECT_HOME") || fail
mkdir -p "${INSTALLDIR}/venv" || fail

IGNORED_QUEUES=()
IGNORE_QUEUES_ARG=""
if [[ "$IGNORE_WORKQ" == "True" ]]; then
    IGNORED_QUEUES+=("workq")
fi

if [[ "$IGNORE_HTCQ" == "True" ]]; then
    IGNORED_QUEUES+=("htcq")
fi

if [[ -n "$IGNORED_QUEUES" ]]; then
    joined=$(IFS=,; echo "${IGNORED_QUEUES[*]}")
    IGNORE_QUEUES_ARG="--ignore-queues ${joined}"
fi

./initialize_pbs.sh || fail

./initialize_default_queues.sh || fail

./install.sh --install-python3 --venv "${INSTALLDIR}/venv" --cron-method "$CRON_METHOD" || fail

./generate_autoscale_json.sh --install-dir "$INSTALLDIR" \
                            --username "$(jetpack config cyclecloud.config.username)" \
                            --password "$(jetpack config cyclecloud.config.password)" \
                            --url "$(jetpack props get cyclecloud.url)" \
                            --cluster-name "$(jetpack props get cyclecloud.cluster)" \
                            $IGNORE_QUEUES_ARG

ls "${PBSPRO_AUTOSCALE_PROJECT_HOME}/autoscale.json" || fail
azpbs connect || fail
systemctl restart pbs