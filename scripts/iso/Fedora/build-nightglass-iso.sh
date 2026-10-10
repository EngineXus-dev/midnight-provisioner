#!/usr/bin/env bash
# Build the Nightglass Fedora installer ISO from an OFFICIAL Fedora
# Everything netinstall ISO by adding the Nightglass kickstart with mkksiso.
# Creates only a NEW output ISO; never writes to USB sticks, disks or EFI.
set -euo pipefail

usage() {
  cat >&2 <<'EOF'
Usage: build-nightglass-iso.sh --iso Fedora-Everything-netinst-x86_64-<ver>.iso
                              (--checksum <Fedora CHECKSUM file> | --sha256 <hash>) [--output DIR]
  --iso       official Fedora Everything netinstall ISO (x86_64)
  --checksum  Fedora's signed CHECKSUM file (recommended): its GPG signature is
              verified with Fedora's key, then the ISO hash is read from it
  --gpg-key   Fedora signing key (default /etc/pki/rpm-gpg/RPM-GPG-KEY-fedora-<ver>-primary)
  --sha256    alternatively, the ISO's SHA-256 copied from that CHECKSUM file
  --output    folder for the new ISO (default: current folder)
Needs: lorax (mkksiso), xorriso, isomd5sum, python3-kickstart, git. mkksiso
runs as root (via sudo) to rebuild the EFI boot image. --checksum also needs gnupg2.
EOF
  exit 2
}

HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
iso="" sha="" checksum="" gpgkey="" out="$PWD"
while (( $# )); do
  case "$1" in
    --iso) iso="${2:-}"; shift 2 ;;
    --sha256) sha="${2:-}"; shift 2 ;;
    --checksum) checksum="${2:-}"; shift 2 ;;
    --gpg-key) gpgkey="${2:-}"; shift 2 ;;
    --output) out="${2:-}"; shift 2 ;;
    *) usage ;;
  esac
done
[[ -n "$iso" ]] || usage
[[ -n "$sha" && -z "$checksum" || -z "$sha" && -n "$checksum" ]] || { echo "Give exactly one of --checksum or --sha256." >&2; usage; }
[[ -f "$iso" && ! -L "$iso" ]] || { echo "Input ISO not found (or a symlink): $iso" >&2; exit 2; }
[[ -z "$sha" || "$sha" =~ ^[0-9a-fA-F]{64}$ ]] || { echo "--sha256 must be a 64-character SHA-256" >&2; exit 2; }
[[ -d "$out" ]] || { echo "Output folder does not exist: $out" >&2; exit 2; }
case "$(basename -- "$iso")" in
  *netinst*|*boot*) ;;
  *Live*|*live*) echo "Use the Everything NETINSTALL ISO; Live ISOs cannot apply this kickstart's package set." >&2; exit 2 ;;
esac
for tool in mkksiso xorriso implantisomd5 git python3; do
  command -v "$tool" >/dev/null 2>&1 || { echo "Missing tool: $tool (sudo dnf install lorax xorriso isomd5sum python3-kickstart git)" >&2; exit 2; }
done

work="$(mktemp -d)"
trap 'rm -rf -- "$work"' EXIT

if [[ -n "$checksum" ]]; then
  [[ -f "$checksum" ]] || { echo "CHECKSUM file not found: $checksum" >&2; exit 2; }
  ver="$(basename -- "$iso" | sed -n 's/.*-x86_64-\([0-9][0-9]*\)-.*/\1/p')"
  if [[ -z "$gpgkey" ]]; then
    [[ -n "$ver" ]] || { echo "Cannot tell the Fedora version from the ISO name; pass --gpg-key." >&2; exit 2; }
    gpgkey="/etc/pki/rpm-gpg/RPM-GPG-KEY-fedora-${ver}-primary"
  fi
  [[ -f "$gpgkey" ]] || { echo "Fedora signing key not found: $gpgkey (install fedora-gpg-keys, or pass --gpg-key)" >&2; exit 2; }
  command -v gpgv >/dev/null 2>&1 && command -v gpg >/dev/null 2>&1 || { echo "Missing tool: gpgv (sudo dnf install gnupg2)" >&2; exit 2; }
  echo "Verifying Fedora's signature on $(basename -- "$checksum")..."
  GNUPGHOME="$work/gnupg" gpg --batch --quiet --dearmor --output "$work/fedora.gpg" "$gpgkey"
  # Only the signed text counts: lines appended outside a clearsigned block are ignored.
  if ! gpgv --keyring "$work/fedora.gpg" --output "$work/CHECKSUM.verified" "$checksum" 2>"$work/gpgv.log"; then
    cat "$work/gpgv.log" >&2
    echo "CHECKSUM signature is NOT valid for Fedora's key; nothing was built." >&2
    exit 1
  fi
  sha="$(awk -v n="SHA256 ($(basename -- "$iso")) = " 'index($0, n) == 1 { print substr($0, length(n) + 1) }' "$work/CHECKSUM.verified")"
  [[ "$sha" =~ ^[0-9a-fA-F]{64}$ ]] || { echo "The signed CHECKSUM has no SHA256 line for $(basename -- "$iso")." >&2; exit 1; }
fi

echo "Verifying the official ISO checksum..."
actual="$(sha256sum -- "$iso" | cut -d' ' -f1)"
if [[ "${actual,,}" != "${sha,,}" ]]; then
  echo "SHA-256 MISMATCH: $actual. Re-download the ISO from fedoraproject.org; nothing was built." >&2
  exit 1
fi

name="Nightglass-Installer-$(basename -- "$iso")"
target="$out/$name"
[[ ! -e "$target" && ! -L "$target" ]] || { echo "Refusing to overwrite $target" >&2; exit 2; }

python3 "$HERE/render_kickstart.py" --output "$work/nightglass.ks"
if command -v ksvalidator >/dev/null 2>&1; then
  ksvalidator "$work/nightglass.ks"
fi

sudo_cmd=()
[[ "$EUID" -eq 0 ]] || sudo_cmd=(sudo)
echo "Running mkksiso (root is needed to rebuild the EFI boot image)..."
"${sudo_cmd[@]}" mkksiso --ks "$work/nightglass.ks" -- "$iso" "$target"
[[ "$EUID" -eq 0 ]] || "${sudo_cmd[@]}" chown "$(id -u):$(id -g)" "$target"

(cd -- "$out" && sha256sum -- "$name" > "$name.sha256")
echo
echo "Built: $target"
echo "SHA-256: $(cut -d' ' -f1 "$target.sha256")"
echo "Next: test it in a VM, then write it to USB. See scripts/iso/README.md."
