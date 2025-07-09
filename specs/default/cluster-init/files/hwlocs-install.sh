PLATFORM_VERSION=$(jetpack config platform_version) || fail

if [[ "${PLATFORM_VERSION%%.*}" -ge 8 ]]; then
  jetpack download --project pbspro "$PBSPRO_HWLOCS_LIB_EL8" "/tmp" || fail
  yum install -y --allowerasing "/tmp/$PBSPRO_HWLOCS_LIB_EL8" || fail # TODO: this is slow, won't work on all linux distros, and will not be final--Emily and Doug's install-package will be used instead
fi