# Nightglass Deployment USB — one stick, two official installers

> Privacy note: hardware and installation scenarios are illustrative. Discover actual device details independently; historical scenarios are not current authorization.

**STATUS: DRAFT PLAN ONLY. NOTHING HAS BEEN WRITTEN TO ANY USB OR OS DISK.**

Example physical drive roles; discover actual devices independently:
- **Disk 0:** measured system-disk capacity internal Windows GPT disk (Windows 10 Home currently).
  The Windows System/EFI, Reserved, C: and Recovery partitions are protected.
- **Disk 1:** measured backup-disk capacity **PORTABLE DRIVE**. NOT a spare internal SSD, NOT a Fedora
  installation target and **NEVER a USB formatting/boot-media target**.
  We do not know its contents or backup role. Do not overwrite or reformat it.
- A future multiboot installer **requires a THIRD physical device**: a dedicated,
  verified-blank USB flash drive (recommend 32 GiB or greater, preferably 64 GiB).
  Capacity is a planning allowance, not proof that the USB is blank.

## One USB is convenient; one automated dual-OS installer is NOT safer

Use an established multiboot boot manager such as the upstream [Ventoy project]
(https://github.com/ventoy/Ventoy) to hold the **unchanged official ISO files**.
Installing Ventoy to an *explicitly selected empty USB* creates/rewrites that USB's
partitions and **erases its prior contents**. This MUST remain a separately
reviewed manual action, not an auto-run Nightglass PowerShell command.
Never pass a disk number discovered in our Windows review script into Ventoy.

The menu should contain approximately these independent entries:

1. **Windows 11 — official x64 ISO** (installation/recovery media).
2. **Fedora KDE Plasma 44 — official x86_64 Live ISO** (try live system first,
   then possibly start its graphical installer after future user approval).
3. Optional independent, verified Windows recovery tools and offline diagnostics.
   No unverified script injection, unattended install answer files or
   automatically applied partition layout.

Official sources checked in October 2026:
- Microsoft Windows 11 ISO:
  https://www.microsoft.com/en-ca/software-download/windows11
- Fedora KDE Plasma Desktop download:
  https://fedoraproject.org/kde/download/
- Ventoy upstream:
  https://github.com/ventoy/Ventoy
- Upstream Ventoy Secure Boot documentation:
  https://www.ventoy.net/en/doc_secure.html

Always recheck the **current stable official release** and integrity guidance
when actually downloading. Verify Windows ISO source/integrity using Microsoft's
published instructions where available. Verify Fedora's downloaded ISO against
the **signed** Fedora checksum from the same release; a raw SHA-256 on its own
checks corruption but does not authenticate the publisher.

### Secure Boot caution

Ventoy can present extra UEFI shim/MOK enrollment requirements; a working
multi-ISO menu is NOT guaranteed on every firmware. Upstream Ventoy describes
a default Secure Boot policy that may **bypass signature verification**. For
a security-focused Nightglass project, do not silently accept such a bypass
or weaken firmware security just to boot the stick. Explicitly inspect and
test the applicable Ventoy Secure Boot policy on this hardware. If it cannot
boot under the desired policy, prefer **two separate, official installer
USB sticks** (Microsoft Windows media and Fedora Media Writer) rather than
auto-changing Secure Boot settings or installing untrusted boot keys.

### Windows 11 in-place upgrade is a DIFFERENT operation

To keep Windows 10 applications and user files, first independently verify
Windows 11 eligibility and a restorable external backup, and then follow
Microsoft's supported **in-place upgrade initiated while Windows is running**:
Windows Update / Windows 11 Installation Assistant, or mount/open the official
Windows 11 ISO within Windows and run its setup.exe, choosing *Keep personal
files and apps* where available. Merely booting the Windows 11 ISO from the
USB is ordinarily the **fresh/clean installation path** and may erase the
existing Windows installation; it is NOT an unattended way to upgrade
Windows 10 safely. Do not trigger Windows installation as part of Nightglass.

Official Microsoft description:
https://support.microsoft.com/en-us/windows/deployment/install-upgrade/ways-to-install-windows-11

When Windows 11 succeeds, boot it repeatedly and recheck activation, encryption,
Windows recovery, firmware entries, hardware support and disk layout. **Only
after the Windows upgrade is finished** is Fedora partition planning appropriate.

### Fedora live boot and final installation

Initially boot Fedora KDE Live from the menu, use **Try Fedora**, test AMD
graphics, networking, input, audio, suspend/resume and reboot into Windows.
The USB is NOT the Fedora target disk and the portable Disk 1 is out of scope.

If the user later explicitly approves installing Fedora, both OS installations
must be performed **sequentially with their official installers**. On the
present single internal measured system-disk capacity Windows disk, Fedora may require manually
shrinking Windows C: using Windows Disk Management **after proven full backup
and recovery readiness**; measured filesystem free space free *inside C:* is not unallocated.
The partitioning plan must independently verify available storage, LUKS,
Windows ESP/Recovery protection, UEFI boot selectors and rollback.
No disk/EFI layout or shrink amount is approved at this stage.

### Preparation and test milestones

- [ ] Verify Windows 11 eligibility and preserve independent Windows/recovery
      backups **before** an upgrade or Fedora installer work
- [ ] Obtain a separate expendable USB stick; record its size, model and
      purpose; preserve both Disk 0 and the confirmed portable Disk 1
- [ ] Review SHA-256/signed checksum evidence for official ISO files
- [ ] Decide Ventoy vs two official sticks based on Secure Boot compatibility
- [ ] User explicitly confirms the **dedicated USB's identity and that all its
      contents may be deleted** before invoking any USB-formatter/writer
- [ ] Prepare USB manually; boot-test both menu entries WITHOUT beginning
      a clean Windows install or Fedora partitioning
- [ ] If chosen, finish Windows 11 in-place upgrade inside Windows first
- [ ] Boot Fedora KDE live; test hardware and return to Windows
- [ ] Review Windows GPT/EFI/Recovery and unallocated space against a
      separately authorized Fedora installation plan
- [ ] Perform controlled Fedora install only with explicit user approval
- [ ] Independently verify Windows + Fedora UEFI boot and Windows recovery
- [ ] Only then consider the already documented Fedora/KVM/sVirt VM
      hardware-acceptance gates, never using malicious VM test samples

**STOP conditions:** only Windows OS disk and portable drive visible;
no third dedicated USB; unknown USB target; unexpected Disk 1 write;
unverified backups/BitLocker recovery; unsigned/unknown installation image;
Ventoy Secure Boot policy incompatible; confusing Fedora partition preview;
Windows upgrade unfinished or unrecoverable. Under any of these, STOP.

This document is a planning/provenance artifact. No new "one click dual-boot"
partition tool, silent firmware modification, preseeded Windows setup,
automatic Fedora installer, ISO downloader or device writer is authorized.
