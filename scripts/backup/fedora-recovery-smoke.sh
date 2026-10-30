#!/usr/bin/env bash
# Midnight Provisioner Fedora recovery smoke checks: READ-ONLY; no guest defined or booted.
set -euo pipefail
if [[ $# -ne 1 ]]; then
  echo "Usage: bash scripts/backup/fedora-recovery-smoke.sh /path/to/staged-recovery" >&2
  exit 2
fi
if [[ "$(uname -s)" != "Linux" ]]; then
  echo "Run on a Fedora Linux test host." >&2
  exit 2
fi
if [[ $EUID -eq 0 ]]; then
  echo "Do not run as root: inspect libvirt permissions instead." >&2
  exit 2
fi
HERE="$(cd -- "$(dirname -- "$BASH_SOURCE")/../.." && pwd -P)"
export PYTHONPATH="$HERE"
if ! command -v python3 >/dev/null 2>&1; then
  echo "Missing Python 3 interpreter." >&2
  exit 2
fi
printf '\n[1/3] Midnight Provisioner host diagnostics (read-only)\n'
python3 -m midnight_provisioner doctor
printf '\n[2/3] Staged recovery integrity (read-only)\n'
python3 -m midnight_provisioner recover verify "$1"
printf '\n[3/3] Fedora host import-readiness audit (read-only)\n'
python3 -m midnight_provisioner recover preflight "$1"
cat <<'NOTICE'

PASS: the read-only recovery checks completed.
This does NOT prove that the guest boots, network is fully isolated,
or the host is protected from dangerous samples.

Manual acceptance steps remain:
- Review all generated XML, machine/UEFI firmware, NVRAM and disk paths.
- Confirm the security profile and SELinux/permission settings.
- Only on a disposable, isolated test host: register a NEW guest under
  human supervision, independently verify it has no network interface,
  and test a clean boot and stop without touching the original VM.
- Do not use real malware as a test fixture.

No guest was defined, started or changed by this script.
NOTICE
