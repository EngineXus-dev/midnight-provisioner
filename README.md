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

## Fedora installation and run — one application installer

**First install Fedora KDE alongside Windows manually, after making and testing full backups.** Nightglass's installer is an **application installer**, not an OS/partition/EFI installer.

On the manually installed Fedora desktop, as your regular user:

```bash
# Optional system dependencies, reviewed and explicitly confirmed separately:
bash scripts/fedora-dependencies.sh

# One installer on any machine, regardless of RAM size:
bash scripts/setup-nightglass.sh

# Open Nightglass:
"$HOME/.local/share/nightglass/venv/bin/nightglass" gui
```

The installer stores its **own** Python environment in `${XDG_DATA_HOME:-~/.local/share}/nightglass/venv`. It never deletes an existing environment or changes a different project's `.venv`, machine profile, Windows installation, partitions, or virtual disks. Rerunning it refreshes only Nightglass's dependencies after user confirmation.

Select **Machine settings** inside Nightglass. `Automatic` detects RAM and logical CPUs each time you start a VM, clamping allocated memory and concurrent-VM limits to the actual host. `Compact`, `Balanced`, and `Performance` are preferences that **cannot override hardware limits**. Optional wheel-safe text fields let you fine-tune maximum guest RAM, active VMs, and an advisory vCPU recommendation.

Equivalent terminal commands (run from within the installed Nightglass environment):

```bash
nightglass profile show
nightglass profile apply auto
nightglass profile apply compact
nightglass profile apply balanced
nightglass profile apply performance
```

Machine-local settings go to `${XDG_CONFIG_HOME:-~/.config}/nightglass/machine.json` (mode 0600); workspace definitions remain in the separate `workspaces.json`. **Moving to a new PC requires installing the app again and provisioning or restoring compatible VMs separately**—copying a workspace definition alone does not transfer VM disks, firmware, keys, or networks.

### Updating the application

**Updates are optional and never install silently.** On an official, clean `main` source checkout, Nightglass can check for updates and request explicit approval for a fast-forward-only source update. Branches, modified files, untracked files, and unexpected Git remotes block this path. GitHub source updates are not signed-binary verification.

```bash
nightglass update check
nightglass update apply
```

The GUI also offers **Machine settings → Check for updates / Install available update**. Enabling check-at-start only checks for updates and never installs them. Restart the GUI after an update. If Python dependencies change, rerun `bash scripts/setup-nightglass.sh` manually.

For libvirt access errors, use Fedora's documented polkit/virtualization configuration. Do **not** run Nightglass as root to bypass access checks.

### First usable workspace

1. Open `virt-manager` and create a Kali VM with a private virtual disk, ~**3 GiB RAM**, 2 vCPUs (your 8 GB system should run **only one major VM at a time**).
2. Configure its virtual network **disconnected at first**. For isolated authorized lab traffic, review the security model, then explicitly run `./scripts/create-lab-network.sh` and attach the VM NIC to **nightglass-lab**. This is not suitable for live malware analysis.
3. Configure the guest display for **loopback VNC**, not SPICE, and remove host-guest clipboard/agent channels and passthrough devices. The launch audit will report any policy violations.
4. In Nightglass choose the **Authorized Pentesting** profile → **Bind VM** → specify the libvirt domain name. A failed audit blocks starting that VM **through Nightglass**.
5. For malware analysis, create a **separate disposable offline VM**: no NIC, no host shares or USB devices, no SPICE channels. Consider a different physical system when handling real malware.
6. For development, click **Start / Enter** under Trusted Development. It explicitly warns that Distrobox shares the host home and is for trusted code only.

`nightglass inspect pentest` and `nightglass inspect analysis` show read-only VM-policy findings in the terminal. `nightglass doctor` does not modify system state.

## Offline guest preparation

Nightglass now has a **Prepare VM** wizard for Kali/pentesting and malware-analysis workspaces. It validates a **local ISO against the SHA-256 digest you obtained from its publisher**, generates an offline virt-install blueprint sized to this machine, and verifies both install and post-install libvirt XML using `--dry-run --print-xml`.

**It does not yet create or start a VM.** Actual VM installation remains under your control through virt-manager; then bind the new guest in Nightglass and run its launch audit. See [VM preparation guide](docs/VM_PREPARATION.md).

## Cold VM backups and validation (experimental)

Nightglass can now prepare **cold backups** of fully shut-down restricted VMs
using newly created directories only. The export checks guest power state,
managed-save status, local disk formats and backing chains, includes UEFI NVRAM
where applicable, then copies guest disks and XML with SHA-256 manifests.

In the GUI, use **Cold backup** on a VM card, then **Backup & verify → Verify
saved backup**. CLI options:

```bash
nightglass backup plan pentest
nightglass backup create pentest /path/to/a/NEW/backup-folder
nightglass backup verify /path/to/a/backup-folder
```

This is **not** one-click rollback or a tested restore procedure: source XML
contains machine-specific paths, and a verified hash does not prove a guest
can boot. See [cold backup and manual recovery](docs/COLD_BACKUP.md).

## Recover a backup into a NEW offline staging area

Nightglass can verify a cold backup and make a separate, **disconnected**
recovery copy, generating a proposed VM XML with a fresh identity. Source
disks and existing guest definitions are untouched. Use **Backup & verify →
Recover into NEW folder** and **Verify staged recovery**, or run:

```bash
nightglass recover plan /path/to/backup /path/to/NEW-dir recovered-vm
nightglass recover stage /path/to/backup /path/to/NEW-dir recovered-vm
nightglass recover verify /path/to/NEW-dir
```

**The new VM is not defined or started.** Review firmware, SELinux labels,
permissions and XML before a manual import on an isolated test host. This
is not one-click rollback, a hypervisor security guarantee or a proven
bootable restore. See [recovery staging instructions](docs/RECOVERY_STAGING.md).

## Fedora import-readiness check (read-only)

Before registering a restored VM, Nightglass can verify its staged file hashes,
offline XML, installed libvirt schema, QEMU image headers, KVM availability,
RAM budget and a unique guest name. This is available as **Backup & verify →
Check Fedora import readiness**, or:

```bash
nightglass recover preflight /path/to/NEW-dir
bash scripts/fedora-recovery-smoke.sh /path/to/NEW-dir
```

**Neither operation imports, boots, converts, deletes, defines or modifies a
guest.** A passing check is not proof of boot success or runtime isolation.
Complete the [supervised Fedora/KVM acceptance guide](docs/FEDORA_ACCEPTANCE.md)
before introducing any automatic import or rollback behavior.

## Registered guest acceptance (actual libvirt definitions)

After manually importing a *new* recovery guest on Fedora, Nightglass can
read and compare its **current, inactive, and saved-memory** libvirt XML.
The **Backup & verify → Audit registered VM** action checks offline or lab
device rules, local RAM limits, and the declared network inventory. You can
save a **private local JSON report** to a new file; it is never uploaded.

```bash
nightglass accept new-guest --policy isolated
nightglass accept new-guest --policy isolated --report ~/nightglass-audit.json
```

A report that passes XML checks is **not** evidence of actual boot success,
packet-level network isolation, or resistance to hypervisor escape. Read the
[registered guest audit guide](docs/REGISTERED_GUEST_AUDIT.md).

## Native virtualization-tool tests (no VM creation)

The GitHub CI pipeline now checks **real** libvirt XML schema validation and
QEMU disk-header behavior on a disposable Ubuntu runner, including refusal of
QCOW2 backing-file chains. This is stronger than mocked tool responses, but
**still does not boot a VM or prove Fedora isolation**. See
[Native tools testing](docs/NATIVE_TOOLS_TESTING.md) and
[Fedora acceptance guide](docs/FEDORA_ACCEPTANCE.md).

## Live resource and external VM monitoring (advisory)

From **Diagnostics → Refresh resource monitor**, Nightglass shows host
`MemAvailable`, swap usage, and active `qemu:///system` guests, including
VMs started outside Nightglass. After explicit activation, it refreshes every
20 seconds while Diagnostics is displayed. On the command line:

```bash
nightglass resources
```

This is **read-only, not an isolation guarantee or an enforcement service**.
Missing RAM data or an inaccessible libvirt connection means UNKNOWN, never a
false NORMAL status. See [resource monitoring limitations](docs/RESOURCE_MONITOR.md).

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
