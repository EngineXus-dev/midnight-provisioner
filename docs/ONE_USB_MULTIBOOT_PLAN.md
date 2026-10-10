# Nightglass Deployment USB — one stick, two official installers

> Privacy note: hardware and installation scenarios are illustrative. Discover actual device details independently; historical scenarios are not current authorization.

**STATUS: DRAFT PLAN ONLY. NOTHING HAS BEEN WRITTEN TO ANY USB OR OS DISK.**

**Update:** the Fedora entry on this stick can now be the Nightglass installer ISO (official Fedora netinstall plus a Nightglass kickstart; disk and encryption still chosen by you). See [`scripts/iso/README.md`](../scripts/iso/README.md) for building it, testing in a VM, and the install order. Unplug Disk 1 before running either installer.

Example physical drive roles; discover actual devices independently:
- **Disk 0:** measured system-disk capacity internal Windows GPT disk (Windows 10 Home currently).
  The Windows System/EFI, Reserved, C: and Recovery partitions are protected.
- **Disk 1:** measured backup-disk capacity **PORTABLE DRIVE**. NOT a spare internal SSD, NOT a Fedora
  installation target and **NEVER a USB formatting/boot-media target**.
  We do not know its contents or backup role. Do not overwrite or reformat it.
- A future multiboot installer **requires a THIRD physical device**: a dedicated,
  user-owned **16 GB USB flash drive** (not the portable Disk 1). A 16 GB
  stick should be sufficient for the two ISOs if their **actual combined
  sizes plus Ventoy overhead** fit the freshly prepared USB partition.
  Fedora KDE 44 x86_64 is about 3.1 GB; Windows 11 ISO size varies by
  release/language (often roughly 7–8+ GB). Check the *real* file sizes
  and usable USB space before any media preparation. Do not assume the
  drive is blank or erase it now.

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

### User-selected Windows 11 CLEAN install — intentionally deferred

The user expressly chose a **clean Windows 11 install**, NOT an in-place
upgrade preserving installed apps. That decision means the existing Windows
install, installed applications, environment and any unbacked files can be
lost if the Windows target is erased. Windows 11's real hardware eligibility
(TPM 2.0, Secure Boot capability, storage/driver support), licensing/edition,
activation recovery, and a checked backup of important local project files
must be verified before any install.

**Do not run installation now.** This is a future deployment option while
the user finishes other work. The user's example backup-drive capacity portable Disk 1 is intended
as backup storage ONLY; copy any needed files there, verify their integrity,
and **disconnect it before booting a clean installer** so it cannot be selected
as an installation target or accidentally formatted. A copy of selected files
is not automatically a restorable full-system image.

The present Windows OS is on an internal measured system-disk capacity GPT drive labelled Disk 0
*in the October 9 Windows readout*. Setup may renumber disks/partitions:
never select any drive by disk number alone. A future supported Windows 11
clean install can create/recreate its EFI, MSR, OS and recovery partitions on
a **human-verified internal Windows target**, with the consequences of every
deletion/format operation explicitly approved then. This documentation
does NOT authorize deleting the current Windows ESP/Recovery/C: partitions.
No unattended WinPE scripts, auto-delete rules, answer files or ISO patching.

After clean Windows 11 is working, independently validate activation
(the prior Windows 10 Home licence is not a guaranteed Pro licence), drivers,
user file restoration, Windows recovery, encryption and firmware.
Only then plan Fedora KDE live trials and later dual boot. Preserve
sufficient internal disk capacity for the eventual Fedora installation, but
do NOT guess a Linux allocation or partition now.

Official Microsoft clean-install documentation:
https://support.microsoft.com/en-us/windows/deployment/install-upgrade/reinstall-windows-with-the-installation-media

Read [Windows 11 clean-install staged plan](WINDOWS11_CLEAN_INSTALL_STAGED.md)
for a non-executing backup and later recovery checklist.

### Key entry is optional at installation time

The Nightglass installer-media planning options include **Activate
later (default)** and **During setup** for Windows 11 Pro. If
Microsoft Setup shows **I don't have a product key**, choose it
when deferring activation; confirm the chosen edition is **Windows
11 Pro**, especially on a laptop with a possible OEM Home firmware
key. Later activate using genuine Windows **Settings > System >
Activation > Change product key**. No product key is bundled in the
ISO, USB, Nightglass scripts or build settings.

An offline, non-mutating ISO-capacity planner is staged at
`scripts/windows/Plan-Nightglass-InstallMedia.py`; it can estimate whether
the real file sizes plus 1 GiB headroom fit a *declared measured
usable USB byte capacity*. It cannot verify media bootability,
publisher authenticity or device selection and never formats USB.
See [activation and media preflight](WINDOWS11_PRO_ACTIVATE_LATER.md).

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

- [ ] Verify Windows 11 eligibility, matching edition/licence and an
      independently restorable recovery/backup plan **before** clean install
- [x] User reports a separate 16 GB USB stick is available (capacity
      unverified); preserve the example backup-drive capacity portable Disk 1 as backup storage
- [ ] Verify real USB identity, usable size, any existing contents,
      official ISO sizes and safety margin before any USB formatting
- [ ] Review SHA-256/signed checksum evidence for official ISO files
- [ ] Decide Ventoy vs two official sticks based on Secure Boot compatibility
- [ ] User explicitly confirms the **dedicated USB's identity and that all its
      contents may be deleted** before invoking any USB-formatter/writer
- [ ] Prepare USB manually; boot-test both menu entries WITHOUT beginning
      a clean Windows install or Fedora partitioning
- [ ] When explicitly authorized much later, perform the user-selected
      Windows 11 CLEAN install only after backup validation and portable
      backup-drive disconnection; then validate Windows before Fedora
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
Windows clean-install backup unverified, or installer not explicitly
authorized for that later date. Under any of these, STOP.

This document is a planning/provenance artifact. No new "one click dual-boot"
partition tool, silent firmware modification, preseeded Windows setup,
automatic Fedora installer, ISO downloader or device writer is authorized.

**Current execution state:** USB not prepared, ISO files not downloaded
or validated, Windows 11 not installed, Fedora not installed, portable
drive not accessed and no Windows partition changed. The user is NOT
ready to execute this plan yet and has asked to continue other work.

## Optional custom Windows 11 Lite ISO is NOT necessary for USB fit

The 16 GB installer stick can likely hold official unmodified Windows
11 and Fedora KDE ISOs if the measured files plus Ventoy overhead fit.
NTLite compression is an optional independent project, **not** a
prerequisite for multi-ISO boot media. The preferred first boot path
is to retain one genuine, unmodified Microsoft installation image
for reliable recovery.

If building an optional Lite image, use the current official stable
Windows version (Microsoft lists **26H2 as of 2026-10-09**) and keep
the edition with an actually valid licence (current Windows was Home;
do not default to Pro), servicing, Defender, BitLocker, TPM, WinRE,
WebView2, Store, and virtualization components. The machine remains
in INSTALLATION HOLD and NO ISO has been built here.

See [NTLite Free safe profile](WINDOWS11_LITE_IMAGE_PROFILE.md).
