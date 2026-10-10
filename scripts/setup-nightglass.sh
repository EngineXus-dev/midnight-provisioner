#!/usr/bin/env bash
# One Nightglass application install for all supported Fedora KDE computers.
# Does not install or partition an operating system, modify UEFI, or use sudo.
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
PYTHON_BIN="${NIGHTGLASS_PYTHON:-python3}"
if [[ -z "${HOME:-}" || "$HOME" != /* ]]; then
  echo "HOME must be set to an absolute path." >&2
  exit 2
fi
DATA_HOME="${XDG_DATA_HOME:-}"
# The XDG spec says relative values are invalid and must be ignored.
[[ "$DATA_HOME" == /* ]] || DATA_HOME="$HOME/.local/share"
VENV_DIR="$DATA_HOME/nightglass/venv"
MARKER="$DATA_HOME/nightglass/installed-by-nightglass-setup"

if [[ "${1:-}" != "" && "${1:-}" != "--yes" ]]; then
  echo "Usage: ./scripts/setup-nightglass.sh [--yes]" >&2
  exit 2
fi
if [[ "$(uname -s)" != "Linux" ]]; then
  echo "Nightglass's GUI runs on Linux, not on Windows." >&2
  exit 2
fi
if [[ "$EUID" -eq 0 ]]; then
  echo "Run as your regular Linux desktop user, without sudo." >&2
  exit 2
fi
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "Python 3.11+ is required: cannot find $PYTHON_BIN" >&2
  exit 2
fi
# Explicit exit, not assert: assert is skipped when PYTHONOPTIMIZE is set.
if ! "$PYTHON_BIN" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'; then
  echo "Python 3.11+ is required: $PYTHON_BIN is older." >&2
  exit 2
fi
if [[ ! -f "$ROOT/pyproject.toml" || ! -d "$ROOT/nightglass" ]]; then
  echo "Run this script from inside a complete Nightglass source checkout." >&2
  exit 2
fi
if [[ -L "$DATA_HOME/nightglass" || -L "$VENV_DIR" || -L "$MARKER" ]]; then
  echo "Refusing symlinked Nightglass installation paths." >&2
  exit 2
fi
if [[ -e "$VENV_DIR" && ! -f "$MARKER" ]]; then
  echo "The Nightglass venv directory already exists without our installation marker." >&2
  echo "Nothing was changed; inspect the directory manually." >&2
  exit 2
fi
if [[ "${1:-}" != "--yes" ]]; then
  echo "Nightglass will install Python dependencies into its OWN user venv:"
  echo "    $VENV_DIR"
  echo "It will leave workspace profiles, VM disks, other venvs, Windows and UEFI untouched."
  echo "No root privileges are requested. System virtualization tools must be installed separately."
  if [[ ! -t 0 ]]; then
    echo "Confirmation needed: run interactively or pass --yes." >&2
    exit 2
  fi
  read -r -p "Type INSTALL to continue: " confirm
  [[ "$confirm" == "INSTALL" ]] || { echo "Cancelled."; exit 1; }
fi
umask 077
mkdir -p -- "$DATA_HOME/nightglass"
if [[ ! -e "$VENV_DIR" ]]; then
  # Claim this dedicated, newly created directory before any dependency step.
  # An interrupted first installation can therefore be safely resumed.
  mkdir -- "$VENV_DIR"
  touch -- "$MARKER"
  chmod 600 -- "$MARKER"
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi
if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  # Our marker proves we created this directory; finish an interrupted venv
  # creation in place. Nothing is deleted.
  echo "Completing an interrupted Nightglass venv creation..."
  "$PYTHON_BIN" -m venv "$VENV_DIR" || true
fi
if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  echo "Nightglass venv is not functional. Existing content was not removed." >&2
  echo "On Fedora, 'python3 -m venv' needs the python3 package (ensurepip included)." >&2
  exit 2
fi
"$VENV_DIR/bin/python" -m pip install --disable-pip-version-check -e "$ROOT"
if ! "$VENV_DIR/bin/python" -c 'import nightglass.cli' >/dev/null 2>&1; then
  echo "Installation finished but Nightglass cannot be imported from its venv." >&2
  exit 1
fi
touch -- "$MARKER"
chmod 600 -- "$MARKER"
echo
echo "Nightglass installed. Resource mode: Auto (clamped to this computer's actual RAM/CPU)."
echo "Launch: $VENV_DIR/bin/nightglass gui"
echo "Change resource profile inside Nightglass -> Machine settings."
echo "You can run this script again to refresh Nightglass dependencies; no files are deleted."
echo "This is an editable install: keep this source checkout at $ROOT (moving or deleting it breaks the app)."
echo "After 'nightglass update', run this script again so new dependencies are installed."
missing=()
for command_name in virsh virt-manager virt-viewer podman distrobox; do
  command -v "$command_name" >/dev/null 2>&1 || missing+=("$command_name")
done
if (( ${#missing[@]} )); then
  printf 'Host tool(s) not installed: %s\n' "${missing[*]}"
  echo "Review scripts/fedora-dependencies.sh to install missing host packages separately."
fi
