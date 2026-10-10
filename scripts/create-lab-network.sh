#!/usr/bin/env bash
# User-triggered, opt-in: create a libvirt network with NO forwarding.
# Does not modify OS disk partitions, existing libvirt VMs or other networks.
set -euo pipefail
if [[ $EUID -eq 0 ]]; then echo 'Run as normal user with libvirt authorization, not sudo.' >&2; exit 2; fi
command -v virsh >/dev/null || { echo 'virsh missing'; exit 2; }
if virsh --connect qemu:///system net-info nightglass-lab >/dev/null 2>&1; then
  echo 'nightglass-lab already exists. No changes made. Inspect with:'
  echo 'virsh --connect qemu:///system net-dumpxml nightglass-lab'
  echo "Nightglass requires <dns enable='no'/> in it (older versions of this script omitted it);"
  echo 'add it with: virsh --connect qemu:///system net-edit nightglass-lab'
  exit 1
fi
if [[ ! -t 0 ]]; then
  echo 'Confirmation needed: run this script interactively. Nothing changed.' >&2
  exit 2
fi
cat <<'WARN'
This creates ONLY a libvirt virtual bridge, with no upstream forwarding.
It is intended for authorized pentesting lab VMs, NOT live malware.
Lab VMs can potentially contact host services bound to the bridge interface.
Do not bridge this to any real network. Review host firewall rules.
WARN
confirm=''
read -r -p 'Type CREATE-LAB to create isolated libvirt network: ' confirm || true
[[ $confirm == CREATE-LAB ]] || { echo 'Cancelled; nothing changed.'; exit 0; }
temp=$(mktemp)
trap 'rm -f "$temp"' EXIT
cat > "$temp" <<'XML'
<network>
  <name>nightglass-lab</name>
  <bridge name='virbr-nglab' stp='on' delay='0'/>
  <!-- No DNS: otherwise host dnsmasq relays guest lookups upstream (a DNS tunnel out). -->
  <dns enable='no'/>
  <ip address='192.168.197.1' netmask='255.255.255.0'>
    <dhcp><range start='192.168.197.10' end='192.168.197.200'/></dhcp>
  </ip>
</network>
XML
virsh --connect qemu:///system net-define "$temp"
if ! virsh --connect qemu:///system net-start nightglass-lab; then
  # Remove only the inactive definition this run just created.
  virsh --connect qemu:///system net-undefine nightglass-lab >/dev/null 2>&1 || true
  echo 'Could not start nightglass-lab (address range or bridge name in use?). Definition removed.' >&2
  exit 1
fi
virsh --connect qemu:///system net-autostart nightglass-lab
echo 'Created isolated lab network. No Internet forwarding and no DNS relay; review host firewall exposure.'
