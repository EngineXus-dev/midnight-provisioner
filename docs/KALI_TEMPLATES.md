# Kali VM template catalog — lightweight, purpose-built guests

Nightglass now supports a catalog of **curated Kali Linux VM profiles**
for authorized white-hat and red-team workflows. Each template is a
**separate planned virtual machine with a unique name and independent qcow2
disk**. There is no enormous "install every tool" guest.

Browse without any ISO, network access or host changes:

```bash
nightglass templates list
nightglass templates list --category white-hat
nightglass templates list --category red-team
nightglass templates show web-audit
```

Choose one template in the GUI under **Prepare VM → Kali toolkit**, or plan
it through the existing ISO hash + libvirt XML dry-run:

```bash
nightglass provision pentest --template web-audit \
  --iso /path/to/official-kali-installer.iso \
  --sha256 PUBLISHER_VERIFIED_64_CHARACTER_SHA256
```

The `provision` command verifies a **local official Kali ISO checksum**
and runs `virt-install --dry-run --print-xml` for both installer stages.
It checks both against Nightglass's conservative restricted guest policy.
It **does not** clone/install/register/start a VM, generate a disk, install
packages, enable Internet routing, run `apt`, or change Windows/EFI.

After independently installing the guest through virt-manager **with explicit
owner approval**, the requested software list can be reviewed **inside that
guest**, including Kali package/dependency availability. The guest should
have **no attached interface by default**; no automatic network bridge,
host sharing, USB passthrough, microphone, guest agent or clipboard.
The user must separately authorize any network connectivity or in-guest
package installation and ensure that actual libvirt XML still passes the
Nightglass audit. All profiles remain bound by the host resource cap
(e.g. **one running VM at a time** on an 8 GiB machine).

## Built-in profiles

| VM template | Focus | Suggested packages (not installed by Nightglass) |
| --- | --- | --- |
| `recon` | White-hat discovery/inventory | nmap, dnsrecon, whois, traceroute, curl, jq |
| `web-audit` | White-hat web testing | burpsuite, whatweb, nikto, ffuf, sqlmap |
| `defense` | Blue/white-hat forensics | wireshark, tcpdump, yara, sleuthkit, lynis |
| `wireless` | White-hat radio survey planning | aircrack-ng, kismet, iw, wireshark |
| `ad-review` | Red-team authorized directory review | impacket-scripts, netexec, ldap-utils, smbclient, nmap |
| `exploit-lab` | Red-team practice exploit/debug lab | metasploit-framework, exploitdb, gdb, nmap |
| `web-validation` | Red-team scoped web validation | ffuf, sqlmap, burpsuite, whatweb |

A template's nominal RAM is no more than 3.5 GiB, with at most 2 vCPUs.
The actual machine-local budget clamps it further. Disk suggestions range
from 32 to 72 GiB. Even a few tools may pull in many dependencies—no fixed
disk-size or dependency estimate is guaranteed. Templates are suggestions,
not verified reproducible software lockfiles or preinstalled snapshots.

### Boundaries

- **Red-team is an approved exercise role, not a license to access others'
  systems.** Operate only against an explicitly authorized scope. Active
  scanners, fuzzers and exploitation frameworks can disrupt services.
- **Wireless** requires real radio/USB hardware. Nightglass's restricted
  guest policy explicitly refuses host USB passthrough; a wireless toolkit
  profile *cannot* silently enable a physical adapter.
- **Exploit research** is for disposable, controlled lab targets. No default
  public network access, automation, payload execution or third-party access.
- **No distrowide metapackage**: never use `kali-linux-everything`,
  `kali-linux-large`, or broad `kali-tools-*` groups.
- **No shared mutable guest disk** across template VMs. Keeping separate
  guest OS installations reduces cross-role package conflicts and avoids
  a single high-maintenance multi-tool installation, but isolation still
  depends on effective Fedora/libvirt/KVM security.
- **Package provenance matters:** verify the packages available from
  the intended, signed Kali repositories and review their dependency tree
  before any manual guest-side installation. Do not paste arbitrary
  third-party scripts or pipe downloads to shells.
- No automated cloning or tool installation has been added. This phase
  intentionally separates **template planning** from privileged host
  provisioning and guest updates.

## Implemented after catalog: setup plans and manual version snapshots

A template can now be exported as a private **PLANNED_ONLY** JSON record,
checked for catalog drift, compared with a manually prepared Kali package
inventory and optionally saved as a self-reported version lock. See
[per-guest Kali setup manifests](KALI_SETUP_MANIFESTS.md) for examples
and explicitly unverified software provenance and rollback assumptions.

## Host and installer preflight (implemented, not VM creation)

A private setup plan can now be combined with the actual local Kali installer
ISO and a designated existing host storage directory using
`nightglass templates preflight PLAN.json --iso LOCAL.iso --storage-dir EXISTING_DIR`.
The GUI offers **Check Kali VM readiness**. This checks the ISO checksum,
two offline libvirt XML stages, current system-libvirt guest cap, available
RAM and temporary qcow2 storage headroom; it does not reserve space,
install the VM or prove isolation. See
[Kali template host readiness](KALI_TEMPLATE_PREFLIGHT.md).

## Audit a separately installed Kali template (read-only)

After a human manually installs and shuts off a unique Kali guest,
`nightglass templates registered PLAN.json --disk /absolute/guest.qcow2`
compares its registered libvirt definitions with the curated plan and the
user-selected independent disk, and checks for **exact-path** disk sharing
with other registered VMs. The GUI offers **Audit installed Kali template VM**.
This is static configuration inspection only, not a guest boot or trust
certification. See [registered Kali template checks](KALI_REGISTERED_TEMPLATES.md).

## Next phase planned (not enabled)

A supervised, reproducible **per-guest setup manifest** could track selected
Kali version, official ISO hash, package versions, dependency checks and
post-install verification after Fedora hardware acceptance tests. Tool
installation or VM creation must remain explicit and guest-scoped, with
rollback/backup verification before automation.

Official Kali references: 
- [Kali metapackages and scope](https://www.kali.org/docs/general-use/metapackages/)
- [Official package index](https://www.kali.org/tools/)
- [Kali updating guide](https://www.kali.org/docs/general-use/updating-kali/)
