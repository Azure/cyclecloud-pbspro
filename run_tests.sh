#!/usr/bin/env bash
set -euo pipefail
source versions.sh

PROJECT_ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
cd "$PROJECT_ROOT"

"${PYTHON:-python3}" -m venv --clear "$PROJECT_ROOT/.testenv"
TEST_PYTHON="$PROJECT_ROOT/.testenv/bin/python"

"$TEST_PYTHON" -m pip install --upgrade pip 'setuptools<72' wheel
"$TEST_PYTHON" -m pip install --no-build-isolation \
    "$CYCLECLOUD_API_URL" "$SCALELIB_URL" -e "$PROJECT_ROOT/pbspro" pytest hypothesis PyYAML

TEST_PATHS=(pbspro/test)
if [[ -d "$PROJECT_ROOT/test_packaging" ]]; then
    TEST_PATHS+=(test_packaging)
fi
exec "$TEST_PYTHON" -m pytest "${TEST_PATHS[@]}" "$@"