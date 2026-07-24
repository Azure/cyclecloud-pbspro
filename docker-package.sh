#!/usr/bin/env bash
set -euo pipefail

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    echo "Usage: $0"
    echo "Run the release workflow build job locally using act and Docker."
    echo "Build the current working tree with released dependencies into blobs/."
    exit 0
fi
if [[ $# -ne 0 ]]; then
    echo "Error: local dependency overrides and extra act arguments are not supported." >&2
    exit 2
fi

cd "$(dirname "$(readlink -f "$0")")"
for tool in act docker unzip; do
    if ! command -v "$tool" >/dev/null 2>&1; then
        echo "Error: $tool is required. See BUILDING.md for prerequisites." >&2
        exit 1
    fi
done
docker info >/dev/null

artifact_dir=$(mktemp -d)
trap 'rm -rf "$artifact_dir"' EXIT

act workflow_dispatch \
    --workflows .github/workflows/release.yml \
    --job build \
    --platform ubuntu-latest=node:20-bookworm-slim \
    --container-architecture linux/amd64 \
    --container-daemon-socket=- \
    --bind=false \
    --use-gitignore=true \
    --env ACT=true \
    --secret-file /dev/null \
    --env-file /dev/null \
    --var-file /dev/null \
    --input-file /dev/null \
    --artifact-server-path "$artifact_dir" \
    --artifact-server-port "${ACT_ARTIFACT_SERVER_PORT:-34567}" \
    --rm

mapfile -t archives < <(find "$artifact_dir" -type f -name release-artifacts.zip)
if [[ ${#archives[@]} -ne 1 ]]; then
    echo "Error: expected one release-artifacts.zip from the build job." >&2
    exit 1
fi
unzip -tq "${archives[0]}"
unzip -q "${archives[0]}" -d "$artifact_dir/output"
mkdir -p blobs
cp "$artifact_dir/output/"* blobs/
echo "Release artifacts written to $PWD/blobs (matching files replaced; other files preserved)."
