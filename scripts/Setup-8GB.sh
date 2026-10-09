#!/usr/bin/env bash
# Nightglass 8 GiB resource preset; no sudo and no OS/partition modifications.
set -euo pipefail
PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"
PYTHON_BIN="${NIGHTGLASS_PYTHON:-python3}"
exec "$PYTHON_BIN" -m nightglass profile apply 8gb "$@"
