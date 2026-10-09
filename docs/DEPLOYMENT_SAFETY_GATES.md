# Windows 10 + Fedora KDE deployment: non-destructive readiness gates

> Privacy note: hardware and installation scenarios are illustrative. Discover actual device details independently; historical scenarios are not current authorization.

**Status: INSTALLATION HOLD — prepare and inspect, do NOT modify disks.**
This phase is separate from Fedora VM security testing. Nightglass
does not partition disks, manage firmware entries or install an OS.

## Read-only Windows review

The standalone script at scripts/Review-Windows-DualBoot.ps1 observes:
Windows/CPU/RAM; firmware and Secure Boot status (when readable);
the Fast Startup registry flag; OS BitLocker/device-encryption status
(never recovery keys); sanitized disk numbers, styles, sizes and
partition roles; and available *filesystem* space on the Windows OS
partition. Missing permissions or unreliable readings are **UNKNOWN**,
not inferred as safe.

It executes no write commands for partitioning, formatting, changing
encryption, editing BCD/EFI, rebooting or starting VMs. It does not
prompt for admin elevation, creates no report, and never selects an
installation target. **A clean readout never authorizes installation.**

### Fetch and inspect without changing the original checkout

In Windows PowerShell 5.1 or newer, from the original Nightglass Git
directory:

    git fetch --no-tags origin deployment/windows-dualboot-readiness-gates
    if ($LASTEXITCODE -ne 0) { throw "Fetch failed" }

    $dir = Join-Path $env:TEMP ("Nightglass-Windows-Review-" + [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $dir | Out-Null
    $review = Join-Path $dir "Review-Windows-DualBoot.ps1"

    git show origin/deployment/windows-dualboot-readiness-gates:scripts/Review-Windows-DualBoot.ps1 |
        Set-Content -LiteralPath $review -Encoding UTF8
    if ($LASTEXITCODE -ne 0) { throw "Could not fetch review script" }

    $tokens = $null
    $parseErrors = $null
    [System.Management.Automation.Language.Parser]::ParseFile($review, [ref]$tokens, [ref]$parseErrors) | Out-Null
    if ($parseErrors.Count -ne 0) {
        $parseErrors | Format-Table
        throw "PowerShell parser rejected script; do not execute"
    }

    powershell -NoProfile -ExecutionPolicy Bypass -File $review

This writes only one newly named, temporary copy of the script and
updates Git fetch metadata. It does not overwrite the repository,
env/venv, other folders, Windows partitions, or boot configuration.
Inspect output before sharing; withhold hardware identifiers, personal
paths, disk IDs, and all recovery keys.

## Optional Windows 11 first (before touching Fedora storage)

The Windows 10 Home baseline on 2026-10-09 reports UEFI, a
**measured system-disk capacity GPT Windows Disk 0** with C: and system/recovery partitions,
and a separate **measured backup-disk capacity GPT Disk 1 confirmed as a PORTABLE DRIVE**.
Disk 1 is neither a Fedora installation target nor a boot-media formatting
candidate; its existing contents remain protected.
Neither disk is authorized for repartition. C: has measured filesystem free space free
*inside its existing Windows volume*, not free unallocated disk space.
On this detected RAM capacity usable-RAM laptop, Nightglass still recommends one
small VM at a time.

If Windows 11 is **clean-installed later** (the user's selected option),
**finish and validate Windows 11 before Fedora**. The revised reviewer has read-only TPM presence,
readiness and version observations plus limited Disk 1 partition and
bus metadata; it never certifies eligibility, prints TPM ownership
details or modifies any state. Use Microsoft PC Health Check and
Windows Update, and separately verify Windows encryption/recovery.
Secure Boot and encryption were UNKNOWN in the initial non-admin
readout, and Fast Startup was ENABLED.

Before any Windows 11 clean installation, verify external bootable recovery media,
offline encryption recovery keys if applicable, image backups, and
supported device eligibility. Following the upgrade, rerun the
read-only review on Windows 11 and independently confirm disk layout,
boot/recovery, drivers and data before attempting Fedora live USB
testing. Neither Windows 11 clean installation nor Fedora installation is
automatic.

See the full [optional Windows 11-first plan](WINDOWS11_UPGRADE_FIRST.md)
and the [manual deployment decision template](DEPLOYMENT_DECISION_TEMPLATE.md).

## Human-only gates — all mandatory before installation

| Gate | Mandatory evidence or decision | Missing result |
| --- | --- | --- |
| Windows recovery | Tested external disk/system image covering boot/data/recovery and an independently bootable recovery USB | **HOLD** |
| Encryption | BitLocker/device encryption status, securely retrievable offline recovery key if encryption is present | **HOLD** |
| Firmware | Current boot mode, Secure Boot state, Windows boot option and one-time boot menu procedure | **HOLD** |
| Disk identity | Independently confirm Windows boot disk, EFI/MSR/Recovery partitions and exact Fedora target | **HOLD** |
| Capacity | Free room for Fedora, updates, encryption overhead, qcow2 expansion, backups and Windows growth | **HOLD** |
| Fedora medium | Official installer ISO download, checksum verification and non-installing live USB trial | **HOLD** |
| Hardware | Verify AMD graphics, touchpad, Wi-Fi, audio, display, external storage, suspend/resume and reboot | **HOLD** |
| Rollback | Written offline Windows restoration plan, recovery media and key availability | **HOLD** |
| Manual approval | Review every partition/format/delete/bootloader change in graphical installer | **HOLD** |

"Windows C: filesystem free space" is **not unallocated disk space**.
The reviewer does not recommend a shrink size. Prefer an independent
second SSD where supported. Shared-disk shrink must be a separate
human-authorized operation using Windows Disk Management only after
verified backups. Nightglass will not automate any of it.

### UEFI / EFI-system-partition design

Do not assume every PC uses the same boot/partition layout. UEFI systems
typically use GPT. Fedora's official UEFI reference permits an
existing ESP shared with Windows, but multiple-disk and multiple-ESP
designs require careful machine-specific review. Decide only after
checking the actual firmware, disks and Fedora installer proposal.
Never format a Windows ESP, Recovery or Windows data partition.
Avoid adding third-party boot managers until both OSes independently
boot via the firmware picker.

Microsoft documents that boot/UEFI changes can trigger BitLocker
recovery. **Ensure the recovery key is saved privately offline** before
any later boot-order or firmware change. Do not silently disable
BitLocker, clear TPM, or weaken Secure Boot to bypass a failed check.

Windows Fast Startup can retain a hibernated kernel session.
Before any Linux access to Windows NTFS, independently verify the
Windows filesystem is fully shut down and not hibernated. Never mount
a hibernated NTFS volume writable. The HiberbootEnabled registry
flag is an observation, not proof of current filesystem state.

### Hardware resource envelope

For an approximately 8 GiB Ryzen 5 laptop with integrated graphics,
use **one modest VM at a time** and keep sufficient host headroom;
do not run parallel heavy Kali/analysis VMs. The Fedora install/live
trial must confirm usable KVM access and RAM budgets separately.

## Manual deployment stages

**A — Windows inspection.** Run the read-only reviewer; capture
minimal locally retained disk/boot layout evidence, verify Windows
backup/recovery and keys, choose whether a second SSD is viable.

**B — Fedora live USB.** Boot using one-time firmware picker without
installing. Confirm Wi-Fi/display/suspend/disk visibility and that
the machine can return to Windows. Stop on any unreliable behavior.

**C — Explicit human installation (NOT implemented).** Only when
every A/B gate is verified, independently inspect every actual Fedora
graphical-installer disk operation, especially the ESP, target drive,
delete/format requests, encrypted volumes and boot entries. Do not
delegate partition creation or bootloader changes to Nightglass.

**D — Dual-boot acceptance.** Repeatedly boot both OSes, confirm
Windows/Recovery/data intact, intended disk encryption protection,
one-time boot selector function, external backup recoverability, and
no regression after normal updates.

**E — Nightglass VM acceptance.** Only then run Fedora host preflight,
followed by supervised benign KVM/libvirt/SELinux/sVirt, offline
network and cold recovery tests. Do not use malware as a fixture.

## Rollback and stop conditions

- **Fedora USB test fails:** exit to the existing Windows firmware boot
  entry; no disk or EFI change was needed.
- **Wrong proposed disk/ESP formatting:** cancel installer immediately.
  Do not use destructive commands to "fix" partition selection.
- **Windows boot choice missing:** stop, use verified Windows recovery
  media and OEM documentation; do not guess BCD/ESP repair commands.
- **BitLocker recovery prompt:** use only stored offline recovery key;
  never paste it into a GitHub issue or chat log. No key means HOLD.
- **Disk/data corruption:** stop writes and restore the verified
  independent image to reviewed destination hardware using the prior
  tested recovery procedure. Btrfs snapshots are not disk backups.
- **Fedora boots but VM security is unknown:** do not start restricted
  VMs, weaken SELinux or switch to root; continue host verification.

## References

- Fedora Project UEFI:
  https://fedoraproject.org/wiki/Unified_Extensible_Firmware_Interface
- Microsoft BitLocker key management:
  https://learn.microsoft.com/en-us/windows/security/information-protection/bitlocker/bitlocker-key-management-faq
- Microsoft Fast Startup:
  https://learn.microsoft.com/en-us/troubleshoot/windows-client/setup-upgrade-and-drivers/fast-startup-causes-system-hibernation-shutdown-fail

See also INSTALL_PLAN.md, FEDORA_HOST_PREFLIGHT.md and SECURITY_MODEL.md.

## First native Windows parser attempt — 2026-10-09

The user's actual Windows PowerShell AST parser rejected the initial
draft reviewer as **SYNTAX ERROR**: UnexpectedToken `) {` at line
184 and an unexpected `else`. Inspection of the committed file
confirmed 49 unintended duplicate trailing lines after the intended
final read-only checkpoint summary. No hardware queries or system
changes occurred during the attempted script execution because
PowerShell refused to parse it.

The trailing duplicate has been removed on this draft branch. The
new regression tests require one unique terminal checkpoint summary,
one OS-partition inspection block, and on **native Windows**, execute
the real PowerShell AST parser before considering the reviewer valid.

**Corrected script has NOT YET passed the user's native PowerShell
parser or produced a Windows hardware readout.** The next run must
fetch the updated branch and use the parser as a hard execution gate.
Do not execute the file at all if any parser error is returned.
Installation and disk-write permission remain **ON HOLD** regardless
of the reviewer output.

**One USB, separate installers:** see [multiboot media plan](ONE_USB_MULTIBOOT_PLAN.md).
Use a third, deliberately blank USB for Ventoy or independent official media.
Creating a USB bootloader may erase the chosen USB. Never select portable Disk 1.

## Current user-selected timing and media constraints

The user **does not intend to install soon**, prefers a **clean Windows 11
installation** (not an in-place upgrade), will back up selected files to
the **example backup-drive capacity portable Disk 1**, and has a separate **16 GB USB**.
That USB is a plausible two-ISO multiboot device, provided its real
capacity and the actual current Windows 11/Fedora ISO sizes fit.
No device may be formatted now. Backed-up files must be checked for
recoverability, including ignored/untracked local project files and
secrets retained securely. Disconnect the portable backup drive before
any future Windows installer session.

Read [deferred Windows 11 clean install](WINDOWS11_CLEAN_INSTALL_STAGED.md).
