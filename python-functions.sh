
find_python() {
    local minimum_version=${1:-3.11}
    local install_if_missing=${2:-0}
    local directory python_path resolved_directory
    local -a path_entries

    if [[ ! $minimum_version =~ ^3\.[0-9]+$ ]]; then
        echo "Expected a Python 3 minimum version such as 3.11" >&2
        return 1
    fi

    IFS=: read -r -a path_entries <<< "${PATH}:"
    for directory in "${path_entries[@]}"; do
        directory=${directory:-.}
        resolved_directory=$(cd -- "$directory" 2>/dev/null && pwd -P) || continue
        [[ $resolved_directory == /opt/cycle/jetpack/system/embedded/bin ]] && continue
        for python_path in "$directory/python3" "$directory"/python3.[0-9]*; do
            [[ ${python_path##*/} =~ ^python3(\.[0-9]+)?$ ]] || continue
            [[ -f $python_path && -x $python_path ]] || continue
            if "$python_path" -c 'import os, sys; sys.exit(os.path.realpath(sys.executable).startswith("/opt/cycle/jetpack/system/embedded/bin/") or sys.version_info[:2] < tuple(map(int, sys.argv[1].split("."))))' "$minimum_version" >/dev/null 2>&1; then
                printf '%s\n' "$python_path"
                return 0
            fi
        done
    done

    if [[ $install_if_missing == 1 ]]; then
        echo "No suitable Python version found, attempting to install..." >&2
        if command -v yum >/dev/null 2>&1; then
            yum install -y -q "python${minimum_version}" >&2 || return 1
        elif command -v apt-get >/dev/null 2>&1; then
            apt-get update >&2 || return 1
            apt-get install -y -q "python${minimum_version}" >&2 || return 1
        else
            echo "Cannot install Python automatically. Please install Python $minimum_version manually." >&2
            return 1
        fi
        find_python "$minimum_version" 0
        return $?
    fi

    echo "No suitable Python version found (minimum $minimum_version)" >&2
    return 1
}

ensure_pip_and_venv() {
    local python_path=${1:-}
    local python_version

    if [[ -z $python_path ]] || ! python_version=$("$python_path" -c 'import sys; sys.exit(1) if sys.version_info.major != 3 else print("{}.{}".format(*sys.version_info[:2]))'); then
        echo "Please supply a working Python 3 executable to ensure_pip_and_venv" >&2
        return 1
    fi

    if ! "$python_path" -m pip --version >/dev/null 2>&1; then
        "$python_path" -m ensurepip --upgrade >&2 || true
    fi
    if ! "$python_path" -m pip --version >/dev/null 2>&1; then
        echo "Installing pip support for Python $python_version..." >&2
        if command -v yum >/dev/null 2>&1; then
            yum install -y -q "python${python_version}-pip" >&2 || return 1
        elif command -v apt-get >/dev/null 2>&1; then
            apt-get update >&2 || return 1
            apt-get install -y -q python3-pip "python${python_version}-venv" >&2 || return 1
            if ! "$python_path" -m pip --version >/dev/null 2>&1; then
                "$python_path" -m ensurepip --upgrade >&2 || true
            fi
        else
            echo "Cannot install pip automatically for $python_path; no supported package manager found." >&2
            return 1
        fi
    fi

    if ! "$python_path" -m pip --version >/dev/null 2>&1; then
        echo "pip is still unavailable for $python_path after package installation." >&2
        return 1
    fi

    if ! "$python_path" -m virtualenv --version >/dev/null 2>&1; then
        if ! "$python_path" -m pip install -q virtualenv >&2; then
            echo "Could not install virtualenv for $python_path." >&2
            return 1
        fi
    fi
    if ! "$python_path" -m virtualenv --version >/dev/null 2>&1; then
        echo "virtualenv is still unavailable for $python_path after installation." >&2
        return 1
    fi
}

