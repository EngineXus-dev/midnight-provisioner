#!/usr/bin/env bash
# User-triggered, opt-in: create a libvirt network with NO forwarding.
# Does not modify OS disk partitions, existing libvirt VMs or other networks.
set -euo pipefail
if [[ $EUID -eq 0 ]]; then echo 'Run as normal user with libvirt authorization, not sudo.' >&2; exit 2; fi
command -v virsh >/dev/null || { echo 'virsh missing'; exit 2; }
if virsh --connect qemu:///system net-info nightglass-lab >/dev/null 2>&1; then
  echo 'nightglass-lab already exists. No changes made. Inspect with:'
  echo 'virsh --connect qemu:///system net-dumpxml nightglass-lab'
  exit 1
fi
cat <<'WARN'
This creates ONLY a libvirt virtual bridge, with no upstream forwarding.
It is intended for authorized pentesting lab VMs, NOT live malware.
Lab VMs can potentially contact host services bound to the bridge interface.
Do not bridge this to any real network. Review host firewall rules.
WARN
read -r -p 'Type CREATE-LAB to create isolated libvirt network: ' confirm
[[ $confirm == CREATE-LAB ]] || { echo 'Cancelled; nothing changed.'; exit 0; }
temp=$(mktemp)
trap 'rm -f "$temp"' EXIT
cat > "$temp" <<'XML'
<network>
  <name>nightglass-lab</name>
  <bridge name='virbr-nglab' stp='on' delay='0'/>
  <ip address='192.168.197.1' netmask='255.255.255.0'>
    <dhcp><range start='192.168.197.10' end='192.168.197.200'/></dhcp>
  </ip>
</network>
XML
virsh --connect qemu:///system net-define "$temp"
virsh --connect qemu:///system net-start nightglass-lab
virsh --connect qemu:///system net-autostart nightglass-lab
echo 'Created isolated lab network. No Internet forwarding; review host firewall exposure.'
