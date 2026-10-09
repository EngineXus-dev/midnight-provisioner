# Windows 11 first, then Fedora KDE — clean-install preparation (DEFERRED)

> Privacy note: hardware and installation scenarios are illustrative. Discover actual device details independently; historical scenarios are not current authorization.

**Status: STAGED PLANNING ONLY. User chose a Windows 11 CLEAN INSTALL, but NOT now. NO INSTALL, PARTITION CHANGE OR USB FORMATTING AUTHORIZED.**

Windows 11 is not a technical prerequisite of Nightglass. The user's
current preference is a **future clean Windows 11 installation**,
explicitly NOT an in-place upgrade, while still finishing other work.
Prepare verified backups and eligibility first; **finish and validate
Windows 11 BEFORE any Fedora installation or storage changes.** Do not overlap two independent
operating-system changes.

## Observed Windows baseline — 2026-10-09

The user ran the native, read-only Windows hardware reviewer. The
output reported:
- Windows 10 Home, build family 10.0.19045
- UEFI boot, Windows on **Disk 0**, **GPT**, measured system-disk capacity total
- Windows OS volume C: measured system-disk capacity, measured filesystem free space free **inside the volume**
- Disk 0 partition types: System (ESP), Reserved (MSR), Basic (C:),
  Recovery; preserve all in their intended roles
- **Disk 1: measured backup-disk capacity, GPT**, **user-confirmed PORTABLE DRIVE**.
  Its existing contents/backup role have not been inventoried. It is
  **EXCLUDED** from Fedora target selection and from boot-USB formatting
- RAM detected RAM capacity usable, the detected logical CPU count; one small Nightglass VM at a time
- Firmware virtualization reported enabled; VMMonitorModeExtensions and
  SecondLevelAddressTranslationExtensions flags reported False. These
  Windows WMI indicators do NOT prove KVM will or will not work
- Secure Boot **UNKNOWN** (non-admin querying often blocked); Windows OS
  drive encryption/BitLocker status **UNKNOWN**
- Fast Startup **ENABLED** (no change has been made)

This is a single observation, not a warranty or authorisation for an
upgrade. Disk size, free C: filesystem space and BusType must never
be interpreted as permission to write to Disk 0 or Disk 1.

## Windows 11 eligibility (check the actual Windows device)

The reported target CPU (verify compatibility) is included on Microsoft's Windows 11
supported AMD CPU lists. UEFI is reported; memory and disk capacities
exceed the basic Windows 11 minima. **Overall device eligibility has
NOT been established.**

Windows 11 requirements also include TPM **2.0**, UEFI firmware
**Secure Boot capability**, qualifying graphics/display/driver support
and other criteria. Consult Microsoft's **PC Health Check** and
**Windows Update eligibility**; do not claim an unsupported upgrade
is safe because CPU and RAM alone qualify.

The revised native Windows review script observes **only** TPM
presence/readiness/version fields where permitted (not TPM owner
authentication material), and disk bus/other-disk partition summaries.
Unknown or refused TPM, BitLocker or Secure Boot readings stay
**UNKNOWN**. The script never elevates privileges and cannot certify
Windows 11 compatibility. Microsoft's Confirm-SecureBootUEFI cmdlet
requires administrator permissions; unknown status is not itself a
negative hardware verdict.

Official information:
- Windows 11 system requirements:
  https://support.microsoft.com/en-us/windows/experience/compatibility/windows-11-system-requirements
- PC Health Check:
  https://support.microsoft.com/en-us/windows/experience/compatibility/how-to-use-the-pc-health-check-app
- target CPU (verify compatibility) and supported processors:
  https://learn.microsoft.com/en-us/windows-hardware/design/minimum/supported/windows-11-supported-amd-processors
- TPM reporting:
  https://learn.microsoft.com/en-us/powershell/module/trustedplatformmodule/get-tpm
- Windows 10 support and ESU:
  https://support.microsoft.com/en-us/windows/deployment/updates-lifecycle/windows-10-notification-you-re-not-receiving-security-updates

Windows 10 Home regular support ended 2025-10-14. If an immediate
upgrade is deferred, review Microsoft's consumer Extended Security
Updates options and eligibility rather than treating a current
Windows 10 Home installation as fully serviced by default.

## Gate W11-A — backup and device compatibility first

- [x] User's current preference: Windows 11 CLEAN install (NOT immediate)
- [ ] Confirm readiness and separate authorization on the eventual date
- [ ] Official PC Health Check eligible and Windows Update readiness
      reviewed; any safeguard hold respected
- [ ] TPM 2.0, Secure Boot capability, supported driver/GPU and firmware
      status verified without turning off security protections
- [ ] Confirm Windows device encryption or BitLocker state by trusted
      UI/admin inspection and privately retain the **actual** recovery
      key if present — never paste a key into chat or GitHub
- [ ] Tested complete **external Windows disk/EFI/Recovery image** and
      bootable recovery USB; important local files separately copied
- [ ] Confirmed edition/licensing and application/driver compatibility,
      enough free storage, stable power and access to official media

If any is missing: **HOLD — do not initiate the upgrade**.

## Gate W11-B — separately authorized CLEAN INSTALL (not implemented)

When and only when the user is ready, use official Windows 11 media
for a **clean installation**, after device eligibility, Windows Home
licence/edition, backup and recovery verification. This is intentionally
destructive to the previous Windows installation on the explicitly
approved internal Windows target: installed apps, settings and any
unbacked files can be lost. The current Windows ESP/MSR/C:/Recovery
partitions are NOT approved for modification now. A later installer
decision requires a separate review of the real physical target,
regardless of how Windows Setup numbers disks.

The user will back up desired files to the **example backup-drive capacity portable drive** and
verify their integrity. Preserve Nightglass and other projects'
uncommitted/untracked work, ignored .env/config, keys and datasets
securely; GitHub alone is not a complete workstation backup. A
file-copy backup is not necessarily a full bootable Windows recovery
image. Disconnect the portable drive before any installer/USB-writer
session so it cannot be selected accidentally.

Nightglass has **no Windows 11 installer, USB formatter or partition
script** and does not touch boot entries, BitLocker, TPM, firmware or
other user disks. The user is *not* installing yet.

Full staged details:
[deferred Windows 11 clean installation](WINDOWS11_CLEAN_INSTALL_STAGED.md).

## Gate W11-C — re-baseline after clean Windows 11 boots

After successfully reaching the Windows 11 desktop:
- [ ] Verify activation/edition, Windows Update and supported OEM
      graphics, storage, network and power drivers
- [ ] Verify Windows 11 edition/activation, restored user data, reinstall
      needed applications, and independent external backups
- [ ] Recheck recovery USB, encryption/recovery key, Windows boot
      entry, Secure Boot/TPM and Fast Startup state
- [ ] Rerun the **read-only** Nightglass Windows 10/11 reviewer to
      capture a **NEW** disk/partition/firmware baseline
- [ ] Preserve user-confirmed portable Disk 1 exactly as-is. Verify
      that the future Fedora target is NOT this drive or a partition
      on it, regardless of how Windows numbers USB disks after reboot
- [ ] Confirm Windows 11 restarts repeatedly and Windows recovery is
      still available. Let Windows updates settle before adding Fedora

**Only after W11-C passes** may the Fedora live USB trial, manual
disk/ESP layout choice and later owner-authorized graphical installer
be considered. The Fedora physical KVM/sVirt/live guest/cold-restore
security gates are still separate and outstanding.

## Important dual-boot constraints

- Windows Disk 0 currently contains the Windows ESP, Reserved, Basic
  and Recovery partitions. Do not format or delete them.
- measured filesystem free space free *inside* C: is NOT unallocated space and is NOT an
  automatic Linux partition allocation or shrink recommendation.
- Disk 1 is user-confirmed PORTABLE. Its contents are not inventoried;
  never use it as Fedora storage or overwrite it when creating USB media.
  A separate blank USB stick is required for a multiboot installer.
- Windows Fast Startup is currently enabled. Do not mount an NTFS
  volume read-write in Fedora while Windows is hibernated. Any change
  to Fast Startup should be a later separately approved Windows task.
- An 8 GB class machine should run only one small Nightglass VM at a
  time with host headroom, regardless of Windows edition.

**This draft phase performs no clean Windows installation, Fedora install,
partition/EFI mutation, VM startup, filesystem writes outside a
freshly fetched test-script copy, or GitHub PR merge.**

See DEPLOYMENT_SAFETY_GATES.md and DEPLOYMENT_DECISION_TEMPLATE.md for
the mandatory two-OS rollback/acceptance record.

For one dedicated installer USB with Windows 11 and Fedora Live ISOs,
see [Nightglass multi-ISO USB plan](ONE_USB_MULTIBOOT_PLAN.md).

The user reports a separate **16 GB USB**, which should fit two current
official installation ISOs subject to real file-size and firmware checks.
Preparing it is NOT authorized yet; see
[one-USB plan](ONE_USB_MULTIBOOT_PLAN.md). The user intends to complete
other work before any installer execution.
