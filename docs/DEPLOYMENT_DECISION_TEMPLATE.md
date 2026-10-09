# Nightglass deployment decision record (copy privately; never publish secrets)

**Template only. Every item starts unverified.**
No software automatically fills this in or approves a partition/OS change.
Store any completed record locally outside the source repository.

## Machine and rollback gate (BEFORE touching storage)

- [ ] Reviewed exact boot mode (UEFI vs legacy) and disk style
- [ ] Independently identified the Windows OS disk, EFI, MSR and recovery partitions
- [ ] Tested a complete external backup restore route, not only creation of a backup file
- [ ] Created and actually booted a Windows recovery USB
- [ ] Verified BitLocker/device-encryption recovery key offline, if applicable
- [ ] Recorded a way to reach Windows Boot Manager through one-time firmware chooser
- [ ] Confirmed Windows full shutdown and that NTFS is not hibernated
- [ ] Verified target storage is distinguishable from all Windows disks; no ambiguous partitions

## Fedora KDE non-installing live USB trial

- [ ] Source verified using official Fedora download and publisher checksum
- [ ] Tested graphics and display scaling with integrated AMD GPU
- [ ] Tested Wi-Fi, input devices, audio, external storage and power management
- [ ] Tested suspend/resume and reboot back into Windows
- [ ] Confirmed presence/absence of an actual second SSD, or documented review of shared-disk constraints
- [ ] Verified enough capacity for Fedora, VM disks, growth, encryption and **separate cold backups**

## Manual installer approval (NO automation)

- [ ] All preceding checks actually confirmed
- [ ] Windows partitions were positively identified by size/type/device, not guessed
- [ ] EFI/bootloader plan reviewed; Windows ESP/Recovery/data will not be formatted
- [ ] Every proposed installer create/delete/resize/format operation independently reviewed
- [ ] Installer will be cancelled on any uncertainty
- [ ] Windows boot/recovery path remains available during deployment
- [ ] Explicit human authorization for THIS exact machine/target and date (keep separately)

## Post-install acceptance

- [ ] Windows boots repeatedly; files and recovery functionality intact
- [ ] Fedora KDE boots independently through one-time boot chooser
- [ ] Both boot entries survive a standard update/restart cycle
- [ ] Intended Windows/Fedora encryption and Secure Boot posture verified
- [ ] External backups and recovery media remain accessible
- [ ] Only then run Fedora host prerequisites and benign VM acceptance checks

## Required stop decision

**Current decision: HOLD / NOT AUTHORIZED until every relevant
item above is explicitly validated.**

Do not write BitLocker passwords or recovery keys, device serials,
private partitions' GUIDs, disk encryption material, personal paths
or user data into this template, commit history, chat or GitHub PR.
See DEPLOYMENT_SAFETY_GATES.md for stop and rollback paths.
