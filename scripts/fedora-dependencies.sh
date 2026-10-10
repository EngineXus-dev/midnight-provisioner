#!/usr/bin/env bash
# Explicit opt-in to package installation: no partitions, bootloader, VMs or virtual networks changed.
set -euo pipefail
if [[ ! -f /etc/fedora-release ]]; then
  echo 'This installer targets Fedora Linux. Nothing changed.' >&2
  exit 2
fi
if [[ $EUID -eq 0 ]]; then
  echo 'Run as your normal Fedora user; sudo will request authorization for DNF.' >&2
  exit 2
fi
cat <<'NOTICE'
Nightglass Fedora dependencies:
  qemu-kvm, libvirt, virt-manager, virt-viewer, virt-install,
  python3, python3-pip, podman, distrobox, virtiofsd

This step installs RPM packages only. It will NOT repartition a disk,
change the EFI bootloader, install a Linux ISO, create VMs or change firewall/network rules.
Afterward create your Python venv and run the read-only 'nightglass doctor'.
NOTICE
if [[ ! -t 0 ]]; then
  echo 'Confirmation needed: run this script interactively. Nothing changed.' >&2
  exit 2
fi
response=''
read -r -p 'Type INSTALL to run sudo dnf install: ' response || true
[[ $response == INSTALL ]] || { echo 'Cancelled; nothing changed.'; exit 0; }
sudo dnf install qemu-kvm libvirt virt-manager virt-viewer virt-install python3 python3-pip podman distrobox virtiofsd
cat <<'NEXT'
Installed packages. Your libvirt service activation and permissions still need review.
Run: virsh --connect qemu:///system list --all
Do NOT start the app with sudo. Use your regular desktop user and polkit.
NEXT
