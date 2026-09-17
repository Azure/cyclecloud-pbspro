#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
cd "$PROJECT_ROOT"

"${PYTHON:-python3}" -m venv --clear "$PROJECT_ROOT/.testenv"
TEST_PYTHON="$PROJECT_ROOT/.testenv/bin/python"
SCALELIB_VERSION=$("$TEST_PYTHON" -c 'from package import SCALELIB_VERSION; print(SCALELIB_VERSION)')
SCALELIB=${CYCLECLOUD_SCALELIB:-"https://github.com/Azure/cyclecloud-scalelib/archive/refs/tags/$SCALELIB_VERSION.tar.gz"}
API_WHEEL=${CYCLECLOUD_API:-}
if [[ -z "$API_WHEEL" ]]; then
    API_WHEEL=$("$TEST_PYTHON" - <<'PY'
import os
from package import get_cyclecloud_api

os.makedirs("blobs", exist_ok=True)
print(os.path.abspath(os.path.join("blobs", get_cyclecloud_api(None))))
PY
    )
fi

"$TEST_PYTHON" -m pip install --upgrade pip 'setuptools<72' wheel
"$TEST_PYTHON" -m pip install --no-build-isolation \
    "$API_WHEEL" "$SCALELIB" -e "$PROJECT_ROOT/pbspro" pytest hypothesis PyYAML

TEST_PATHS=(pbspro/test)
if [[ -d "$PROJECT_ROOT/test_packaging" ]]; then
    TEST_PATHS+=(test_packaging)
fi
exec "$TEST_PYTHON" -m pytest "${TEST_PATHS[@]}" "$@"