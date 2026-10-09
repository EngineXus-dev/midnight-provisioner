# Future Windows 11 clean install — deferred preparation record

> Privacy note: hardware and installation scenarios are illustrative. Discover actual device details independently; historical scenarios are not current authorization.

**STAGED PLAN / NO EXECUTION APPROVED.** this example describes a clean Windows 11
installation, intends to back up desired data to the example backup-drive capacity portable
drive, owns a separate 16 GB USB, and is **not installing soon**.

This supersedes earlier *in-place Windows 11 upgrade* wording for this
user's current plan. the selected edition requires a valid **Windows
Pro key**, so the intended future target is Windows 11 **Pro**, after
independent validation of that key and activation rights. Do not run setup, alter firmware, install an OS,
delete partitions, image any USB or copy user files automatically.

## Machine and storage identity

From an illustrative read-only Windows review:
- Windows 10 Home, firmware UEFI, GPT.
- **Internal Windows disk**, then enumerated as **Disk 0**:
  measured system-disk capacity, including EFI/System, MSR/Reserved, measured system-disk capacity C: and
  Windows Recovery partitions. C: had measured filesystem free space unused *inside* its
  filesystem, not unallocated Linux space.
- **Portable backup drive**, then enumerated as **Disk 1**:
  measured backup-disk capacity, user-confirmed external/portable. It is NEVER an OS target
  and NEVER a bootable USB formatting target.
- **Separate 16 GB USB flash stick**, user-reported but not identified,
  capacity-tested or verified empty. Future possible two-ISO multiboot
  stick for official Windows 11 and Fedora KDE.
- detected RAM capacity usable RAM, the detected logical CPU count, target CPU (verify compatibility); low-memory
  single-VM profile still applies. TPM 2.0/Secure Boot readiness and
  OS drive encryption remain unverified; Fast Startup enabled.
- **Warning:** Disk numbers can change between Windows, Linux, boot
  media and unplugging drives. Identifying a future target by "Disk 0"
  alone is UNSAFE.

## Preparation at leisure — no action until explicitly requested

1. **Eligibility and licence.** Confirm Windows 11 support with
   Microsoft's current PC Health Check/Windows Update guidance,
   TPM 2.0, Secure Boot-capable UEFI, drivers and machine model.
   Keep your licensed edition in mind: current Windows is Home;
   don't assume Pro activates on a Home digital licence.
2. **Inventory intended personal backups.** Record everything you
   actually want to keep before intentionally destroying the old
   Windows installation: documents, photos, browser/bookmark/profile
   exports, program configurations, software licence information,
   network settings, Git repositories including **uncommitted and
   untracked changes**, and app-specific databases.
3. **Development assets.** For Nightglass and the other unrelated
   local projects, specifically review all local `.env` files,
   API/SSH keys, project configuration, custom scripts, generated
   assets, private datasets, Docker volumes and any VM images.
   A GitHub repository alone does NOT back up ignored/untracked files.
   Secrets should be backed up securely/encrypted, kept off GitHub and
   never pasted into a chat or log. Virtualenvs are usually rebuilt,
   but preserve environment/requirements/lockfiles and local package
   references needed to reproduce them.
4. **Portable backup drive.** Copy the intended files to a reviewed
   folder on the **portable example backup-drive capacity drive**, without formatting it.
   Independently verify sizes/checksums and open a sample of the
   copies. Backups that share only one physical disk can be lost;
   if valuable, arrange an additional independent backup. Preserve
   an optional full Windows disk image if reverting the entire system
   is important, together with a bootable Windows recovery medium.
5. **Recovery and credentials.** Check whether the current Windows
   drive is encrypted and securely retain BitLocker/device-encryption
   recovery keys offline if relevant; also verify access to accounts,
   licences and recovery USB. Never paste recovery keys into this repo
   or ChatGPT. A simple copy of Documents cannot restore a bootable
   Windows installation.
6. **The eventual 16 GB USB.** Confirm the actual usable stick capacity
   and existing files; check that the **official** Windows 11 ISO plus
   Fedora KDE Live ISO and multiboot overhead fit. The Fedora KDE 44
   x86_64 Live image was ~3.1 GB in October 2026; Windows 11 ISO
   size varies by release/edition/language. The two images generally
   fit on a normal 16 GB stick, but validate actual sizes. USB
   preparation will erase that separate stick and requires a separate
   confirmation. Do not touch the portable backup disk.
7. **No date set.** After other work is finished, the user must
   explicitly authorize both the exact device selected for boot USB
   formatting and a separate future Windows clean install.

## Future clean-install execution (NOT scheduled or automated)

- Disconnect the **portable backup drive** before any bootable media
  preparation/OS installation, once data verification is finished.
  It is never a boot medium or destination for Windows/Fedora.
- On install day, check Windows 11 eligibility, Windows recovery,
  genuine ISO and boot-menu compatibility; do not bypass TPM/Secure
  Boot protection or enroll unreviewed third-party boot keys.
- Boot the official Windows 11 installer image from the dedicated
  USB only after verifying it boots properly. **Human review must
  explicitly identify the internal Windows target by physical identity,
  not Windows disk numbering.** Deleting partitions on that target
  removes the previous Windows install, apps and any unbacked data.
  No instruction here approves deletion/formatting of EFI, C: or
  Recovery today.
- Windows Setup can recreate EFI/System, MSR/Reserved and Recovery
  partitions during a newly authorized clean install on a selected
  internal disk. Do not pre-create Fedora partitions or automatic
  boot entries until Windows 11 boots/recovery are independently
  verified. Decide Windows/Fedora disk-space allocation later.
- Confirm correct Windows edition/activation, drivers, Windows Update,
  TPM/encryption, Windows recovery, reboot behaviour and file restore.
  Only after Windows is stable should Fedora KDE Live USB and a
  separately authorized dual-boot installation be considered.
- Fedora remains subject to separate boot/partition/SELinux/KVM/guest
  acceptance checks. The present Nightglass 16 GB USB plan is a
  **boot-menu convenience**, NOT one-click unattended dual boot.

## STOP / HOLD conditions

No verified backup, missing encryption recovery key, unknown TPM/UEFI
compatibility, ISO authenticity doubtful, USB does not have enough
space, wrong target disk, portable drive detected as install target,
unreviewed partition delete/format operation, missing recovery path,
other user projects still active, or user not ready: **STOP**.

No deployment has taken place. This plan may be revised before use.
Official Microsoft clean installation reference:
https://support.microsoft.com/en-us/windows/deployment/install-upgrade/reinstall-windows-with-the-installation-media

See ONE_USB_MULTIBOOT_PLAN.md, WINDOWS11_UPGRADE_FIRST.md,
DEPLOYMENT_SAFETY_GATES.md and DEPLOYMENT_DECISION_TEMPLATE.md.

## Optional lightweight Windows 11 image — conservative profile

A future custom ISO can be built from an **untouched official Windows
11 26H2 ISO** using NTLite Free's edition-management, basic app removal,
ESD compression and ISO creation features. Do NOT remove all editions
except Pro by default: the previously verified Windows licence is
Home, and Pro needs its own valid licence. Never strip servicing,
Defender/firewall, TPM/Secure Boot, WinRE, drivers, Store/WebView2 or
Windows virtualization/WSL/Docker dependencies for a numeric size goal.

NTLite and post-install debloat tools are not required just to
fit Windows and Fedora official ISOs on the user's separate 16 GB USB;
check actual ISO sizes first. Avoid executing WinUtil, Win11Debloat
and RemoveWindowsAI in a chain. User-only, preview-first preferences
are an optional *post*-installation script, not a bootable ISO builder.

This is still a **deferred clean installation**, with no USB format,
image build or Windows system changes performed here.
See [safe Windows 11 Lite build profile](WINDOWS11_LITE_IMAGE_PROFILE.md).

**Requested post-install profile:** all 32 preferences, OneDrive,
Xbox/Game Bar, Widgets/promotions and Copilot/Recall/Click to Do are
staged in [Windows 11 Pro configuration](WINDOWS11_PRO_32_POINT_PROFILE.md).
Privacy/AI toggles are distinct from app uninstall, automatic-encryption
security choice, Windows Sandbox and WSL feature enablement.
No changes have been applied to current Windows 10.
