#!/usr/bin/env bash
# Nightglass Fedora host prerequisite gate. Read-only, no VM creation/start.
set -euo pipefail

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "Fedora Linux hardware prerequisites cannot be verified on this host." >&2
  exit 2
fi
if [[ $EUID -eq 0 ]]; then
  echo "Do not run this inspection with sudo/root. Use your ordinary desktop user." >&2
  exit 2
fi
if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 is required; no packages will be installed automatically." >&2
  exit 2
fi

PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
export PYTHONPATH="$PROJECT_ROOT"
exec python3 -B -m nightglass.host_acceptance "$@"
