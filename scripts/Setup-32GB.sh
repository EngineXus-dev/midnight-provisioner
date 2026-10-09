#!/usr/bin/env bash
# Nightglass adaptive <=32 GiB resource preset; clamps to actual RAM.
# On an 8 GiB host this automatically falls back to the compact profile.
set -euo pipefail
PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"
PYTHON_BIN="${NIGHTGLASS_PYTHON:-python3}"
exec "$PYTHON_BIN" -m nightglass profile apply up-to-32gb "$@"
