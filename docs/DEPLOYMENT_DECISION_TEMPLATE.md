# Midnight Provisioner deployment decision record (copy privately; never publish secrets)

> Privacy note: hardware and installation scenarios are illustrative. Discover actual device details independently; historical scenarios are not current authorization.

**Template only. Every item starts unverified.**
No software automatically fills this in or approves a partition/OS change.
Store any completed record locally outside the source repository.

## Windows 11 Pro clean-install decision

- [x] User preference recorded (2026-10-09): clean-install Windows 11 LATER
      (not in-place upgrade, not currently authorized)
- [ ] Microsoft PC Health Check/Windows Update eligibility reviewed,
      including TPM 2.0, Secure Boot capability, graphics and driver support
- [ ] Windows 10 offline full-image backup, tested recovery USB and
      privately secured encryption/recovery keys available *before* upgrade
- [ ] After future clean Windows 11 install: it boots repeatedly; chosen
      Windows edition activates, drivers work, intended files have been
      restored, apps are reinstalled and Windows recovery still works
- [ ] If Windows 11 was chosen: **new post-upgrade read-only**
      Windows disk/TPM/encryption/firmware inventory reviewed
- [ ] User-confirmed portable Disk 1 is explicitly protected from
      Fedora installation, USB formatting, partitioning and overwrites;
      its data/backup role is reviewed privately if needed
- [ ] Fedora installation is ON HOLD until clean Windows 11 installation,
      file restoration and recovery checks are independently complete

The chosen clean Windows 11 install is not immediate; it must not be
conflated with Fedora partitioning or any unattended OS deployment.
No recovery keys in this file.

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

## Dedicated installer USB (not Disk 1)

- [ ] A *third*, separate disposable USB is available and independently
      identified; user authorizes erasing that USB only
- [ ] Official Windows 11 x64 and Fedora KDE Live ISO sources verified
- [ ] Multiboot USB Secure Boot behavior tested, or two independent
      official USB installers used if incompatible
- [ ] User-selected clean Windows 11 install is NOT performed until
      file backups, recovery, TPM 2.0, firmware and physical target
      are checked and explicit future approval is given
- [ ] Fedora Live USB successfully tried without partitioning
- [ ] Portable Disk 1 never selected as USB writer or OS install target

See ONE_USB_MULTIBOOT_PLAN.md.

## Backup to portable drive (planned, not performed)

- [ ] Preserve desired documents, media, programs/licence records, browser
      data, Midnight Provisioner/local Git trees including ignored/untracked changes,
      local .env/config, secure credentials, and valuable user databases
- [ ] Copy reviewed data to the user-confirmed portable example backup-drive capacity drive;
      validate sizes, hashes and spot-check opening restored copies
- [ ] Disconnect the portable backup drive BEFORE booting installer media
- [ ] Separately consider a verified full Windows system image and recovery
      USB if restoring the entire current machine would be needed
- [ ] User reports a separate 16 GB USB; verify actual capacity, identity,
      contents and combined ISO sizes before any USB writer operation
- [ ] No installation or USB formatting until the user finishes other work

See WINDOWS11_CLEAN_INSTALL_STAGED.md.

## Pro licensing and customizations (not yet active)

- [x] User reports possessing Windows Pro activation key; key itself
      has NOT been collected and MUST NOT be saved in GitHub/ISO
- [ ] Validate legitimate Windows 11 Pro activation/edition on the
      clean installation, preserving Windows recovery/driver options
- [ ] Review 35-item configuration and the separate high-risk phases
- [ ] Verify backup, Windows 11 Pro, local script SHA256 and restore point
      before applying reviewed core personalization settings
- [ ] Remove OneDrive, Xbox/promotional apps only after checking cloud
      sync, file backups and independent recovery options
- [ ] Independently approve optional device-encryption default change,
      Sandbox and WSL2 feature enabling if still wanted

See WINDOWS11_PRO_32_POINT_PROFILE.md.
