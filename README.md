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

## Fedora host posture review (read-only)

Nightglass's Diagnostics page now offers **Audit Fedora host security**.
It reports SELinux enforcement, the `/dev/kvm` character device and access,
firewalld availability, and IPv4/IPv6 forwarding **without modifying the
host**. The CLI equivalent is `nightglass host-security`.

The restricted VM policy additionally rejects explicit guest/disk security
label opt-outs. Successful local checks are **not** proof of effective sVirt,
firewall isolation, packet-level network denial or malware containment.
See [Fedora security posture limitations](docs/HOST_POSTURE.md).

## Guarded VM launch checks across live, inactive and saved XML

For restricted VM workspaces, `nightglass inspect <workspace>` and the
normal **Start / Enter** action inspect the live/current, next-boot/inactive
and any managed-save libvirt domain definitions. A prohibited interface,
host-integration device, explicit SELinux label opt-out or mismatched
identity in **any** version blocks Nightglass-issued start. The local RAM
guard considers all of these definitions, including hotplug maxima.

This does **not** prevent a privileged application from editing libvirt
definitions after the audit, starting guests outside Nightglass or altering
host firewall policy. No new automatic VM import/start has been enabled.

## Verified staged-to-registered recovery handoff

After **manual** registration of a new guest on a disposable Fedora host,
Nightglass can check whether the registered VM really uses the previously
verified staged disk images and matching QEMU formats:

```bash
nightglass recover handoff /path/to/staged-new-guest
```

Or select **Backup & verify → Verify registered handoff**. The check is
read-only, requires the recovered VM to be powered off and rejects extra
disks, changed NVRAM, managed-save state or mismatched registered UUIDs.
It does not prove runtime confinement, guest boot or network isolation.
See [verified recovery handoff](docs/RECOVERY_HANDOFF.md).

## Running guest sVirt metadata (read-only)

With a **benign VM already running**, use **Diagnostics → Observe running VM
sVirt labels** or `nightglass runtime-label SAFE_GUEST --policy isolated`.
The check requires SELinux Enforcing, libvirt's SELinux security model and
matching dynamic sVirt process/image labels reported in current libvirt XML.
Shut-off guests and unverifiable values do not pass.

This **does not start a guest or inspect the actual QEMU process or image
inode's effective labels**. It does not demonstrate network packet isolation.
See [runtime sVirt observation](docs/RUNTIME_SVIRT_OBSERVATION.md).

## Separate Kali toolkit VMs — curated white-hat and red-team profiles

Nightglass offers seven lightweight Kali **planning templates** for recon,
web assessments, defensive forensics, wireless surveys, directory review,
controlled exploit research and web validation. Rather than installing all
security tools into one VM, each profile recommends a **separate Kali VM**
with a unique identity, disk, scoped tool list and laptop-aware RAM limits.

Browse via **Prepare VM → Kali toolkit**, or `nightglass templates list`,
`nightglass templates show recon`, and `nightglass provision pentest
--template recon --iso ... --sha256 ...`. All templates begin **offline**;
Nightglass does not automatically create the VM, connect networks or install
packages. See the [Kali VM template catalog](docs/KALI_TEMPLATES.md).

## Private Kali setup plans and package-version drift checks

Per-template Kali VM plans can now be written to **NEW, private JSON files**
with fixed software lists and offline-only defaults:

```bash
nightglass templates export recon ./new-recon-plan.json
nightglass templates verify ./new-recon-plan.json
```

After **manual** in-guest inspection and installation, compare an explicitly
provided guest inventory or record a separate reported-version snapshot:

```bash
nightglass templates compare ./new-recon-plan.json ./guest-inventory.json
nightglass templates lock ./new-recon-plan.json ./guest-inventory.json ./new-lock.json
```

The GUI adds **Save private Kali setup plan** and **Compare guest inventory**
to Prepare VM. These are read-only planning/comparison operations apart from
writing explicitly requested new JSON records. Guest inventories are
**untrusted user-reported data**, not proof of signed repositories, completed
dependencies or a tested baseline restore. See the
[setup manifest workflow](docs/KALI_SETUP_MANIFESTS.md).

## Kali guest inventory helper (manual, offline)

The standalone **source-checkout** script `scripts/kali-guest-inventory.py`
can be run **manually as an ordinary user inside an already-installed benign
Kali VM** to query locally cached dpkg/apt package versions and produce one
NEW private guest inventory JSON file. Use
`nightglass templates guest-help recon` or **Prepare VM → Guest inventory
instructions** for the non-executable steps.

**Nightglass does not transfer the plan or helper into any VM**, install
software, run guest commands, or open networking. An independent reviewed
transfer mechanism is required; do not enable shared folders or clipboard
to work around its absence. The output is untrusted self-reported data.
See [guest inventory helper workflow](docs/KALI_GUEST_INVENTORY.md).

## Offline Kali template package drift checks

After creating a per-VM Kali setup plan and recording a **self-reported
version lock**, Nightglass can compare a newer inventory without running
commands inside a guest:

```bash
nightglass templates drift ./kali-plan.json ./old-versions.json ./new-inventory.json
```

Or use **Prepare VM → Review package version drift**. It flags
missing tools, version changes, package/release mismatches and
unverified dpkg audit status, but does not install anything or enable
host/guest file transfers. The input reports are **untrusted metadata**,
not cryptographic proof of a clean VM or signed packages. See the
[version drift review guide](docs/KALI_VERSION_DRIFT.md).

## Per-template Kali VM readiness (local read-only)

After saving a curated Kali setup plan with a locally obtained publisher
ISO checksum, use `nightglass templates preflight PLAN.json --iso
LOCAL.iso --storage-dir EXISTING_DIRECTORY` or **Prepare VM → Check Kali
VM readiness**. The check validates the actual ISO SHA-256, both
`virt-install --dry-run` XML phases, available host RAM, already-running
system-libvirt guests and free storage for an independent disk.

This is **not** VM creation, a reservation, package installation or isolation
certification. Missing/unsafe readings block approval; a passing dry-run
only permits **manual review**. See [Kali template readiness](docs/KALI_TEMPLATE_PREFLIGHT.md).

## Verify each installed Kali template uses its own VM disk

After **manual** installation and shutdown, review an independently registered
Kali profile against its saved plan and actual qcow2 disk:

```bash
nightglass templates registered ./recon-plan.json \
  --disk /absolute/path/to/independent-recon.qcow2
```

Or select **Prepare VM → Audit installed Kali template VM**. The checker
inspects both registered XML definitions, current guest state, resource
limits, unexpected networking, disk driver metadata and the **exact source
paths** in other libvirt VMs. It makes no host or guest modifications.
Registered disk checks reject hardlinked selected images, normalized
path aliases and symlinks found within the selected disk folder. Aliases
outside that folder, bind mounts and privileged state changes may still
escape static review; Kali package installation and runtime isolation
remain unverified. See [registered Kali VM audit](docs/KALI_REGISTERED_TEMPLATES.md).

## Verify a separate Kali VM's cold backup baseline

Nightglass can tie each curated Kali profile to an existing **checksum-verified
cold backup**, its original disk path, guest UUID and optional UEFI/NVRAM copy:

```bash
nightglass templates baseline ./kali-plan.json \
  --disk /absolute/path/to/kali-guest.qcow2 \
  --backup /path/to/existing-cold-backup
```

Or use **Prepare VM → Verify Kali cold backup**. The operation is read-only
and warns about backups on the same storage device as the live VM.
A passing hash/definition comparison is **not proof that the backup will
restore or boot**. See [Kali cold baseline workflow](docs/KALI_COLD_BASELINES.md).

## Confirm each Kali VM recovery copy belongs to its template

A read-only check now ties a curated Kali VM setup plan and original
checksum-verified cold backup to an independently staged NEW offline
recovery guest:

```bash
nightglass templates recovery-link ./kali-plan.json \
  --backup /path/to/original-cold-backup \
  --staged /path/to/new-offline-staging
```

Or use **Prepare VM → Verify Kali recovery copy**. It rechecks both
manifests/files, source guest and policy, separate disk/NVRAM copies
and exact safe offline XML transformation. It does not create, import,
boot or restore a VM. See [Kali recovery copy binding](docs/KALI_RECOVERY_LINK.md).

## Audit a separately registered Kali recovery guest before any boot

When a benign Kali VM has been manually recovered into a **NEW guest**
and separately registered (without booting), Nightglass can verify the
full template → cold backup → offline staged copy → registered guest chain:

```bash
nightglass templates recovery-registered ./original-kali-plan.json \
  --backup /path/to/verified-cold-backup \
  --staged /path/to/new-offline-recovery
```

Or use **Prepare VM → Audit registered Kali recovery**. This additional
read-only gate refuses a reused guest UUID, changed registered disk
references, enabled/unknown libvirt autostart and a running recovered guest.
It does **not** import, start or prove a guest can boot or restore. See
[registered Kali recovery handoff](docs/KALI_REGISTERED_RECOVERY.md).

## Supervised metadata observation of a running Kali recovery VM

After an operator has **manually started a BENIGN recovered Kali VM**,
Nightglass can observe libvirt running state, host SELinux/sVirt metadata,
declared offline networking, distinct disk/UUID identity and autostart:

```bash
nightglass templates observe-running ./original-kali-plan.json \
  --backup /path/to/existing-cold-backup \
  --guest new-recovery-guest \
  --disk /absolute/path/to/live-recovery.qcow2
```

The GUI offers **Prepare VM → Observe running Kali recovery**. It never
starts a VM, executes guest commands or hashes a writable live qcow2.
**LIBVIRT/SELINUX METADATA ONLY** is not verified Kali OS boot, restore,
process-context confinement or packet-level isolation. See
[supervised Kali runtime observation](docs/KALI_RUNNING_OBSERVATION.md).

## Read-only effective QEMU SELinux context probe

For an **already manually started benign Kali recovery guest**, the new
`nightglass templates process-label ORIGINAL_PLAN.json --guest NEW_RECOVERY_NAME`
command and **Prepare VM → Inspect effective QEMU sVirt label** button
compare the current libvirt SELinux process label to a read-only,
unprivileged `/proc/PID/attr/current` observation.

The process must uniquely match the registered libvirt guest name and UUID;
unknown or inaccessible process metadata fails closed, **without sudo**.
Kali action buttons now use a compact grid instead of one oversized row.
No VM, guest disk or host configuration is changed. This remains
non-attested process metadata, not proof of guest isolation, OS boot or
recovery. See [QEMU process label inspection](docs/KALI_QEMU_PROCESS_LABEL.md).

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

## Windows-to-Fedora dual-boot preparation (NO installation)

The next draft phase adds a **read-only Windows 10 readiness reviewer** for
UEFI/BIOS, disk layout, Fast Startup, CPU/RAM and BitLocker status.
It does **not** edit Windows, partition drives, install Fedora, alter
Secure Boot/TPM, request recovery keys or reboot. Do not run any
partitioning or OS install task from Nightglass.

See [Windows dual-boot safety gates](docs/DEPLOYMENT_SAFETY_GATES.md)
and the [private manual decision template](docs/DEPLOYMENT_DECISION_TEMPLATE.md).
The new PowerShell script is on the unmerged
`deployment/windows-dualboot-readiness-gates` draft branch. It is
retrieved to a **new temporary path**, leaving the original local
`main` checkout and its untracked files untouched. Its actual
Windows PowerShell execution has not yet been verified.

No Windows/Fedora dual-boot, physical Fedora hardware acceptance,
benign KVM VM boot or cold rollback has been performed on the user's
machine by this project.

## Threat model and roadmap

See [docs/SECURITY_MODEL.md](docs/SECURITY_MODEL.md), [docs/INSTALL_PLAN.md](docs/INSTALL_PLAN.md), and [docs/ROADMAP.md](docs/ROADMAP.md).

## Verification while GitHub Actions minutes are exhausted

The stacked Nightglass pull requests are still **draft and unmerged**.
The integration branch makes `.github/workflows/verify.yml` manual-only
and provides a local Python test runner that does not launch VMs, use
sudo, download dependencies, or spend GitHub Actions minutes:

```bash
python3 -B scripts/verify_local.py
python3 -B scripts/verify_local.py --focused
python3 -B scripts/verify_local.py --gui       # only with PySide6 installed
python3 -B scripts/verify_local.py --native    # only with native tools installed
```

**On Windows**, the default verifier now runs a clearly labeled
**portable subset** rather than the full Fedora-only test suite.
It never invokes the Windows WSL `bash.exe` launcher. Checks requiring
Linux symlinks, POSIX `0600` permissions, SELinux, system libvirt and
actual running QEMU processes remain **NOT RUN / pending Fedora**.
Do not enable Windows Developer Mode or install WSL to make the security
tests appear green.

Re-run the existing `Run-Nightglass-Checks.ps1` from the original
Nightglass checkout to fetch the updated integration branch into another
**new independent worktree**; it does not pull or overwrite existing
`.env`, `.venv` or untracked files.

### Run complete Fedora tests inside Docker Desktop (Windows)

With Docker Desktop's **Linux engine already running**, use the separate
PowerShell launcher/runner to fetch this integration branch into another
**new clean git worktree** and run the complete Fedora test suite without
GitHub Actions or access to original project secrets:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\Run-Nightglass-Fedora-Checks.ps1
```

This script lives on the integration branch (not the older `main`
checkout). A standalone launcher can retrieve it from the connected
private repository without checking out or overwriting any original
files. The test image may download official Fedora packages **during
the initial build**; the actual tests run with **no network**, a
**read-only checkout**, nonroot UID, no KVM devices and no VM lifecycle
operations. It saves a new result transcript. See
[Docker test instructions](docs/FEDORA_DOCKER_VERIFICATION.md).

**Fedora container green ≠ Fedora host/KVM certified.** Real host
SELinux/sVirt process, guest network and restore verification remains
pending.

This workflow change does **not** globally disable existing automatic
workflows in other PR branches. A repository owner can disable the
**Verify source** workflow in GitHub's Actions UI while minutes are
exhausted. No merges or changes to `main` have been performed.

See [offline verification and stacked-PR integration](docs/INTEGRATION_CHECKLIST.md).
A local test result is not recorded as a GitHub check and cannot replace
real Fedora/KVM hardware safety acceptance.

## Development / verification

```bash
python -m unittest discover -s tests -v
python -m compileall -q nightglass tests
```

No root access, VM images, lab connectivity, or malware samples are needed for these tests. They test policy logic and process argument construction, not the security of a hypervisor itself. SPDX license: MIT.
