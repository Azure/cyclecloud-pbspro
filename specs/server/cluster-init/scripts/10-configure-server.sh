#!/bin/bash

# source $CYCLECLOUD_PROJECT_PATH/default/files/default.sh || exit 1

# PACKAGE_NAME=$(jetpack config pbspro.package "") || fail
# PBSPRO_AUTOSCALE_PROJECT_HOME=$(jetpack config cyclecloud.home)/../pbspro || fail

echo "chef code is not commented out"

# if [[ -z "$PACKAGE_NAME" ]]; then
#     if [[ "${PBSPRO_VERSION%%.*}" -lt 20 ]]; then
#         PACKAGE_NAME="pbspro-server-${PBSPRO_VERSION}.x86_64.rpm"
#     else
#         PACKAGE_NAME="openpbs-server-${PBSPRO_VERSION}.x86_64.rpm"
#     fi
# fi

# jetpack download --project pbspro "$PACKAGE_NAME" "$DOWNLOADS_DIRECTORY" || fail

# yum install -y "$DOWNLOADS_DIRECTORY/$PACKAGE_NAME" || fail # TODO: this is slow, won't work on all linux distros, and will not be final--Emily and Doug's install-package will be used instead

# mkdir $PBSPRO_AUTOSCALE_PROJECT_HOME || fail
# chmod 0755 $PBSPRO_AUTOSCALE_PROJECT_HOME || fail


# mkdir /var/spool/pbs || fail
# mkdir -m 750 /var/spool/pbs/sched_priv || fail


# # cp $CYCLECLOUD_PROJECT_PATH/default/templates/default/sched.config /var/spool/pbs/sched_priv/sched_config || fail
# # chmod 0644 /var/spool/pbs/sched_priv/sched_config || fail

# echo "service stuffff"
# # service stuff

# # cat > /etc/profile.d/azpbs_autocomplete.sh << EOF
# #     eval "$(/opt/cycle/pbspro/venv/bin/register-python-argcomplete azpbs)" || echo "Warning: Autocomplete is disabled" 1>&2
# # EOF
# # chmod 0755 /etc/profile.d/azpbs_autocomplete.sh

