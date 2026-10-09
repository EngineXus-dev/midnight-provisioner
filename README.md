# NIGHTGLASS

**Local-first, Qubes-inspired workspace controller for Fedora KDE.**

> Status: **v0.1 foundation / preview**. Real libvirt inspection, guarded VM start/shutdown/managed-save, trusted Distrobox creation and entry, host diagnostics, and editable VM binding. **NOT a Qubes OS equivalent, installer, penetration-testing tool, malware containment certification, backup system, or disk partitioner.**

Nightglass is **independent of all other projects**. Its restrained dark/neon presentation does not determine its security model.

## What works in this release

- **Four default profiles**: personal desktop (native host), trusted development (rootless Distrobox), authorized Kali VM (offline or verified no-forward lab network), malware-analysis VM (offline only).
- **Desktop GUI** on Fedora KDE via PySide6: workspace statuses, launch/stop/saved memory state, VM console and virt-manager links, bind an existing VM by name, live security-policy summaries, host readiness checks.
- **Real libvirt backend** (`qemu:///system`): domain inventory, status, offline XML inspection, and strictly allowlisted lifecycle commands. VM start is refused if the configured restricted profile fails its policy audit. On machines under 11 GiB RAM, a best-effort low-memory launch guard also requires no other active VM and at most 3.5 GiB guest memory.
- **Trusted development containers**: create a named Ubuntu 24.04 Distrobox with a reviewed image alias, and open it in Konsole. Distrobox is NOT a security boundary.
- **Read-only CLI diagnostics** and tests with mocked hypervisor calls; no virtual machines/root needed to run unit tests.
- **Scripts** for hardware diagnostics on existing Windows 10, opt-in Fedora package installation, and opt-in isolated libvirt lab networking.

### What this release does **not** do

- It does not install Fedora, edit Windows, format partitions, change EFI settings, or replace a bootloader.
- It does not create Kali/analysis guest images for you. Use **virt-manager** to install guests, then click **Bind VM** in Nightglass.
- It does not implement a trusted file transfer broker, snapshot creation/rollback, sealed VM templates, traffic filtering on the host/bridge, guest hardening, or clipboard enforcement at runtime. These are roadmap work.
- It cannot prevent users/admins/other processes from editing libvirt outside Nightglass. A post-audit modification race is possible. The low-memory guard also applies only to Nightglass-issued launches. For malware, a **dedicated analysis host** is safer than relying on this preview.
- It does not secure native host personal activity against the compromise of the host OS.

## Windows 10 first — zero-change prep

Nightglass's controller runs on **Fedora**, not Windows. On the current Windows machine, PowerShell can inspect hardware and storage **without making changes**:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\check-windows-hardware.ps1
```

Prior to Linux dual boot: create a verified full-disk Windows backup, recover BitLocker keys if applicable, confirm UEFI/GPT, check free disk capacity and whether a second SSD exists, and test Fedora KDE live USB hardware compatibility (Wi-Fi, audio, AMD GPU). **Do not repartition, disable BitLocker, or change BIOS settings based only on automatic checks.** Windows 10's ordinary support has ended; use a supported/extended-security-patched Windows environment.

## Fedora installation and run

On a manually installed Fedora KDE host (with UEFI boot entries preserved):

```bash
# Optional: installs RPM dependencies after typing INSTALL. It never changes disk partitions.
./scripts/fedora-dependencies.sh

# On Fedora, using a normal user account, no sudo for the controller.
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .

# Read-only readiness and inventory
nightglass doctor
nightglass list
nightglass gui
```

If `qemu:///system` access fails, configure libvirt/polkit via Fedora's official virtualization guidance rather than starting the entire GUI as root. Network/VM management needs an authorized user. Some machines use modular libvirt socket units; don't assume a legacy `libvirtd.service` is mandatory. Check with `virsh --connect qemu:///system list --all`.

### First usable workspace

1. Open `virt-manager` and create a Kali VM with a private virtual disk, ~**3 GiB RAM**, 2 vCPUs (your 8 GB system should run **only one major VM at a time**).
2. Configure its virtual network **disconnected at first**. For isolated authorized lab traffic, review the security model, then explicitly run `./scripts/create-lab-network.sh` and attach the VM NIC to **nightglass-lab**. This is not suitable for live malware analysis.
3. Configure the guest display for **loopback VNC**, not SPICE, and remove host-guest clipboard/agent channels and passthrough devices. The launch audit will report any policy violations.
4. In Nightglass choose the **Authorized Pentesting** profile → **Bind VM** → specify the libvirt domain name. A failed audit blocks starting that VM **through Nightglass**.
5. For malware analysis, create a **separate disposable offline VM**: no NIC, no host shares or USB devices, no SPICE channels. Consider a different physical system when handling real malware.
6. For development, click **Start / Enter** under Trusted Development. It explicitly warns that Distrobox shares the host home and is for trusted code only.

`nightglass inspect pentest` and `nightglass inspect analysis` show read-only VM-policy findings in the terminal. `nightglass doctor` does not modify system state.

## Useful controls

| Workspace | Backend | Persistent? | Network default | Security promise |
|---|---|---|---|---|
| Personal | Native Fedora KDE | Yes | Host | Not separated from host |
| Trusted Development | Distrobox/rootless Podman | Yes | Host access | **Not a sandbox** |
| Authorized Pentesting | KVM VM | Yes | Offline or verified lab | Isolation backed by KVM, subject to config |
| Malware Analysis | KVM VM | Can be made disposable manually | Offline | Startup guardrails, NOT certified containment |

**Save VM state** uses `virsh managedsave`: a saved memory image consumed by `virsh start`; it is **not a point-in-time snapshot, backup, or clean restoration**. Snapshot management is intentionally withheld in this first version pending tests of qcow2 and guest firmware interactions.

### Repo publishing (new private repo)

The connected GitHub integration does not currently expose *repository creation*. To publish this standalone folder from Windows without touching existing repositories:

```powershell
# GitHub CLI and Git must be installed and you must be authenticated (gh auth login)
.\scripts\Publish-PrivateRepo.ps1
```

The script creates a fresh `nightglass-workspaces` **private** repository through `gh repo create`, initializes only this project directory if needed, refuses existing `origin` remotes and dirty existing Git checkouts, and **never force-pushes or pulls existing work**. You may rename the repo using `-RepoName custom-name`.

## Threat model and roadmap

See [docs/SECURITY_MODEL.md](docs/SECURITY_MODEL.md), [docs/INSTALL_PLAN.md](docs/INSTALL_PLAN.md), and [docs/ROADMAP.md](docs/ROADMAP.md).

## Development / verification

```bash
python -m unittest discover -s tests -v
python -m compileall -q nightglass tests
```

No root access, VM images, lab connectivity, or malware samples are needed for these tests. They test policy logic and process argument construction, not the security of a hypervisor itself. SPDX license: MIT.
