#!/usr/bin/env bash
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
#
# Source this file, then call:
#   find_python [min_version=3.11] [install_python=0] [ensure_pip_and_virtualenv=0] [custom_python_path]
# e.g. find_python 3.11 1 1
#      find_python 3.11 1 1 /bin/python3.11
# Note that find_python 3.11 1 1 /bin/python3.9 would fail because it does not meet the minimum version requirement.
# 
# On success, sets PYTHON to the interpreter path and prints it to stdout.
# On failure, prints an error to stderr and exits non-zero.

_PYTHON_EXCLUDED_DIR=/opt/cycle/jetpack/system/embedded/bin

_python_fail() {
    echo "ERROR: $*" >&2
    exit 1
}

_python_meets_version() {
    local python=$1 major=$2 minor=$3
    "$python" -c "import sys; sys.exit(0 if sys.version_info[:2] >= ($major, $minor) else 1)" >/dev/null 2>&1
}

_python_search() {
    local major=$1 minor=$2 dir name candidate
    local dirs=() names=()
    local IFS=:
    for dir in $PATH /usr/local/bin /usr/bin /bin; do
        dir=${dir%/}
        if [[ -n "$dir" && "$dir" != "$_PYTHON_EXCLUDED_DIR" ]]; then
            dirs+=("$dir")
        fi
    done
    unset IFS

    # Prefer the newest explicitly versioned interpreter.
    for (( m = minor + 20; m >= minor; m-- )); do
        names+=("python${major}.${m}")
    done
    names+=("python${major}" python)

    for name in "${names[@]}"; do
        for dir in "${dirs[@]}"; do
            candidate="$dir/$name"
            if [[ -f "$candidate" && -x "$candidate" ]] && _python_meets_version "$candidate" "$major" "$minor"; then
                echo "$candidate"
                return 0
            fi
        done
    done
    return 1
}

# Installs OS packages for python<major>.<minor> (optionally the interpreter itself) plus pip.
_python_os_install() {
    local major=$1 minor=$2 with_python=$3
    local packages=()
    if command -v dnf >/dev/null 2>&1 || command -v yum >/dev/null 2>&1; then
        [[ $with_python == 1 ]] && packages+=("python${major}.${minor}")
        packages+=("python${major}.${minor}-pip")
        if command -v dnf >/dev/null 2>&1; then
            dnf install -y -q "${packages[@]}" >&2
        else
            yum install -y -q "${packages[@]}" >&2
        fi
    elif command -v apt-get >/dev/null 2>&1; then
        [[ $with_python == 1 ]] && packages+=("python${major}.${minor}")
        packages+=("python${major}.${minor}-venv" "python${major}-pip")
        apt-get update -qq >&2 && DEBIAN_FRONTEND=noninteractive apt-get install -y -q "${packages[@]}" >&2
    elif command -v zypper >/dev/null 2>&1; then
        [[ $with_python == 1 ]] && packages+=("python${major}${minor}")
        packages+=("python${major}${minor}-pip")
        zypper --non-interactive --quiet install "${packages[@]}" >&2
    else
        echo "No supported package manager (dnf, yum, apt-get, zypper) found" >&2
        return 1
    fi
}

_python_ensure_pip_and_virtualenv() {
    local python=$1 is_custom=$2 major minor
    read -r major minor < <("$python" -c 'import sys; print("%d %d" % sys.version_info[:2])')

    if ! "$python" -m pip --version >/dev/null 2>&1; then
        # OS packages would target the system interpreter, not a custom one.
        if [[ $is_custom == 0 ]]; then
            _python_os_install "$major" "$minor" 0 || echo "WARNING: Failed to install pip via the package manager" >&2
        fi
        if ! "$python" -m pip --version >/dev/null 2>&1; then
            "$python" -m ensurepip --upgrade >&2
        fi
        "$python" -m pip --version >/dev/null 2>&1 || _python_fail "Could not install pip for $python"
    fi

    if ! "$python" -m virtualenv --version >/dev/null 2>&1; then
        # Fall back for PEP 668 externally-managed environments.
        "$python" -m pip install -q virtualenv >&2 \
            || "$python" -m pip install -q --break-system-packages virtualenv >&2
        "$python" -m virtualenv --version >/dev/null 2>&1 || _python_fail "Could not install virtualenv for $python"
    fi
}

find_python() {
    local min_version=${1:-3.11}
    local install_python=${2:-0}
    local ensure_pip_and_virtualenv=${3:-0}
    local custom_python_path=${4:-}
    local major minor python

    [[ $min_version =~ ^([0-9]+)\.([0-9]+)$ ]] || _python_fail "Invalid min_version '$min_version', expected <major>.<minor>"
    major=${BASH_REMATCH[1]}
    minor=${BASH_REMATCH[2]}
    [[ $install_python == [01] ]] || _python_fail "install_python must be 0 or 1, got '$install_python'"
    [[ $ensure_pip_and_virtualenv == [01] ]] || _python_fail "ensure_pip_and_virtualenv must be 0 or 1, got '$ensure_pip_and_virtualenv'"

    if [[ -n $custom_python_path ]]; then
        [[ -f "$custom_python_path" && -x "$custom_python_path" ]] || _python_fail "Custom python '$custom_python_path' is not an executable file"
        _python_meets_version "$custom_python_path" "$major" "$minor" \
            || _python_fail "Custom python '$custom_python_path' does not meet the minimum version $min_version"
        python=$custom_python_path
    else
        if ! python=$(_python_search "$major" "$minor"); then
            [[ $install_python == 1 ]] || _python_fail "Could not find python >= $min_version. Please install it, or pass install_python=1"
            echo "Python >= $min_version not found, installing python${min_version}" >&2
            _python_os_install "$major" "$minor" 1 || _python_fail "Failed to install python${min_version}"
            python=$(_python_search "$major" "$minor") || _python_fail "Could not find python >= $min_version after installation"
        fi
    fi

    if [[ $ensure_pip_and_virtualenv == 1 ]]; then
        _python_ensure_pip_and_virtualenv "$python" "$([[ -n $custom_python_path ]] && echo 1 || echo 0)"
    fi

    PYTHON=$python
    echo "$PYTHON"
}
