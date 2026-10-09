# Fedora host security posture: read-only review

Nightglass provides a **read-only host security posture review** in
Diagnostics → Audit Fedora host security and as:

```bash
nightglass host-security
```

The checker does not require sudo, does not ask for additional credentials,
and does not modify system files. A nonzero CLI exit code indicates a
**WARN** or **UNKNOWN** finding; an exit code of zero does **not** certify
host security, sVirt guest labeling, or network isolation.

## What is inspected

| Item | Observation | Interpretation |
| --- | --- | --- |
| Linux platform / nonroot process | Python standard library | Must use an ordinary user; not a Fedora-version proof |
| SELinux mode | `getenforce` with kernel enforce-file cross-check | Enforcing is desirable; actual sVirt guest labels still require verification |
| /dev/kvm | Presence, character-device type and current-user access | Permissions check only; guest boot might still fail |
| firewalld status | `firewall-cmd --state` | Always informational; a running daemon is **not** evidence that guest/host traffic is blocked |
| IPv4 host forwarding | `/proc/sys/net/ipv4/ip_forward` | Informational; a 0 value does not prove all traffic is denied |
| IPv6 host forwarding | `/proc/sys/net/ipv6/conf/all/forwarding` | Informational; a 0 value does not prove guest containment |

Unrecognized/missing readings are **UNKNOWN**, never converted into a
silent pass. No effect on Guest Start: this tool is only an additional
inspection aid. The restricted-domain XML policy separately refuses
**explicit** `<seclabel type="none"/>` or
`<seclabel relabel="no"/>` in the VM or disk definition; an omitted
domain `seclabel` may be supplied by libvirt and cannot be judged from
source XML alone.

## Boundaries requiring physical Fedora testing

This checker **does not** read actual sVirt process/security labels for a
running QEMU guest, measure packet-level network denial, verify nftables
rules, diagnose polkit authentication, validate libvirt's SELinux security
driver, or execute a live VM boot. Those checks require a supervised Fedora
installation and benign test VM. In particular, do not treat 'firewalld
running' or 'IP forwarding off' as proof that a bridged guest cannot contact
the host or Internet.

Do not disable SELinux or firewall rules to work around an error, and do
not run Nightglass as root. Follow the official Fedora security and
virtualization guidance; use a disposable test computer for isolation
acceptance. This review does not collect persistent telemetry, upload host
information, alter Windows partitions/UEFI, or modify a guest.
