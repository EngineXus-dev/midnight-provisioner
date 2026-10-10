# Nightglass Windows 11 Lite — safe NTLite Free build profile

> Privacy note: hardware and installation scenarios are illustrative. Discover actual device details independently; historical scenarios are not current authorization.

**Status: PLANNED, NOT BUILT OR DEPLOYED.** This plan does NOT authorise modifying the current Windows installation. The user has NOT authorised
an OS installation or USB erase. The Windows and Fedora plan remains
deferred, with a separate 16 GB USB for *possible* dual-ISO media and
the confirmed example backup-drive capacity portable disk reserved for user backups only.

## Version and licence gate

As of 2026-10-09, Microsoft's official download page identifies
**Windows 11 26H2** as the current stable public release; the
community post's 25H2 recommendation is no longer automatically the
current choice. Before a future installation, review version-specific
known issues and firmware drivers, and acquire the genuine unmodified
ISO from https://www.microsoft.com/software-download/windows11.

**Edition decision updated:** the current machine was observed running
**Windows 10 Home**, but the selected edition requires a valid **Windows Pro
activation key**. The planned future image may retain **only Windows 11
Pro** after verifying that the key is genuine and valid for Windows 11 Pro.
Never embed the key in any NTLite preset, unattended image, repository,
USB boot menu or diagnostics log. The previous Home digital entitlement
does not itself license Pro. The ISO is multi-edition; evaluate
the genuine image edition indices before removal. Do not use
unsupported activation workarounds or Windows 11 compatibility bypasses.

CPU is a target CPU (verify compatibility) with detected RAM capacity usable RAM and UEFI, but TPM 2.0,
Secure Boot capability and current OS encryption have not been
verified on the host. Official PC Health Check and recovery preparation
must precede any OS install. An image build is not an install permit.

## NTLite Free — two-stage conservative profile

NTLite is a third-party Windows image editor:
https://www.ntlite.com/download/
https://ntlite.com/docs/guides/windows-lite/
https://ntlite.com/docs/guides/export/

NTLite Free permits edition management, basic app removal,
selected settings tweaks, WIM/ESD export and ISO creation for
personal/evaluation use. Full deep component removal is a paid feature;
do not recommend bypassing licensing or copying a Premium preset
that silently fails in Free.

### Stage 0: preserve untouched original

1. Download the official x64 ISO and verify it using the publisher's
   current official verification instructions. Do not tamper with
   Microsoft's original signed binaries or loader.
2. Save the untouched ISO separately from a **working copy**; create
   a new dedicated staging directory with enough free space for
   decompression and exports. Check available storage before loading.
3. Record (locally) original ISO SHA-256, Windows release, language,
   architecture, available editions and NTLite version. A SHA-256
   digest alone does not authenticate an untrusted source.
4. Do NOT store copied ISO payloads in the Nightglass Git repository
   or on the sole portable backup disk.

### Stage 1: single valid edition

1. Add the *working copy* to NTLite.
2. Inspect the multi-edition image; choose the edition that matches
   your real Windows licence: **Pro only after the reported Pro key is
   validated for Windows 11 Pro**. The old Windows 10 Home digital
   licence does not itself activate Pro.
3. Remove only the **other** editions; preserve setup, EFI/boot,
   WinRE recovery, and the installer metadata.
4. Export to a new editable **WIM** working image. Retain the
   original full ISO intact for recovery. Run a VM setup smoke test
   before any additional removal.

### Stage 2: lightweight apps, not core Windows

Reload the single-edition working image in NTLite. Prefer
app/settings-level changes that are reversible or reliably serviced.

Reasonable *optional app removals* if you do not use them:
- Xbox entertainment and Game Bar integrations (not gaming graphics,
  DirectX, game compatibility APIs or core services)
- Clipchamp, consumer promotional/preinstalled media apps
- Trial consumer Teams/Outlook applications if unused
- Widgets/news feeds, consumer suggestions and promotional content
- Maps and optional consumer apps not used by the owner
- OneDrive **only after** verifying your backups and no sync usage

**KEEP** (do not remove or disable):
- Windows servicing stack, component store, Windows Update, TrustedInstaller,
  repair/SFC/DISM and Windows Recovery Environment
- Microsoft Defender, SmartScreen, Windows Firewall, Security Center
- Secure Boot, TPM, BitLocker/device encryption infrastructure, boot
  components, Activation/Licensing and OOBE/account setup
- Network/TLS, Wi-Fi, Bluetooth, VPN stack, device driver install,
  AMD GPU driver support, audio, display and power-management components
- Microsoft Store, App Installer, Windows Package Manager/winget,
  Edge WebView2 runtime and Windows shell dependencies
- .NET Framework/.NET, Visual C++ runtime support, PowerShell,
  Windows Terminal and Win32 compatibility libraries
- Windows hypervisor features, Virtual Machine Platform, WSL2 and
  Hyper-V integration APIs where applicable — useful to Docker Desktop
  and the existing developer environment
- Accessibility, search indexing/service (can be tuned later), fonts,
  input/IME and essential language resources

**Do not force-bypass the normal Windows 11 hardware/OOBE security
requirements, automate creating privileged accounts or embed credentials.**
Leave the supported setup sequence intact and decide OOBE privacy
choices through Windows's ordinary controls.

Save the NTLite project/preset separately from the binary image so
the image edits can be reproduced and audited. Export the final
single-edition image to highly compressed **install.esd** and
build a new **bootable ISO** from the *complete Windows ISO folder*
(not just a standalone WIM or ESD). High ESD compression helps USB
capacity, not necessarily installed footprint or idle RAM.
Always retain both the original ISO and the build manifest/preset.

### Testing before an eventual real installation

- Validate ISO/boot image structure, actual selected edition, normal
  UEFI boot, unmodified Microsoft boot trust chain.
- Boot the customized ISO in a **temporary disposable VM** with Windows
  setup networking optional; Windows 11 requires >=4 GiB RAM and
  compatible guest TPM/Secure Boot if running normal supported setup.
  Do not claim that a 2 GiB guest is valid merely because online posts
  report low idle working sets.
- Complete OOBE and sign in normally; confirm Windows Update cumulative
  updates, Microsoft Defender/security UI, Store/winget, PowerShell,
  WebView2, drivers and Windows Recovery Environment.
- Test app installation, WSL/Docker support when applicable,
  system recovery, SFC/DISM and activation prompts.
- A *VM pass* is not proof of AMD hardware Wi-Fi/audio/graphics support.
  Do not erase the laptop before its official ISO recovery path works.
- If an error appears, expand the retained components. Never keep
  removing modules just to hit a specific ISO size.

**The post's "~3 GB ISO, ~2 GB RAM, ~9 GB installed" are anecdotal,
NOT Nightglass acceptance targets or guaranteed Windows 11 resource
measurements.** Current stable compatibility and reliable security
updates matter more than minimizing a screenshot of idle memory.

## After the user finishes a FUTURE clean installation

Pick **ONE** third-party debloat utility at most, inspect its current
source/changes and create a restoration path before invoking it.
Do not chain Windows image removal plus multiple app/service removers
with overlapping defaults.

### Win11Debloat (preferred if third-party GUI desired)

https://github.com/Raphire/Win11Debloat

Use the interactive, *custom* settings rather than silent
"remove everything" flags. Conservative candidates:
DisableSuggestions, DisableWidgets, DisableCopilot,
DisableRecall (if available), ShowKnownFileExt, and
DisableFastStartup **only as a separately reviewed later
dual-boot preparation change**. If optional Xbox/OneDrive features are
unused, review them specifically; avoid ForceRemoveEdge,
DisableBitlockerAutoEncryption, other encryption/key changes,
RemoveDevApps, and any broad unexamined app removal preset.
Version-dependent settings can change. Review all selected items.

The project documents registry backups and undo options. Registry
undo does not restore everything that was uninstalled:
https://github.com/Raphire/Win11Debloat/wiki/Reverting-Changes

### Chris Titus Tech WinUtil (alternative, not additive)

https://github.com/ChrisTitusTech/winutil

This utility runs with administrator privileges and changes system
configuration. If used, choose a reviewed minimal/interactive
selection rather than executing a remote internet-sourced
script blindly, and do NOT apply an overlapping aggressive profile
after Win11Debloat. Avoid permanently disabling Windows Update,
Defender/firewall, encryption and virtualization.

### RemoveWindowsAI (NOT part of default baseline)

https://github.com/zoicware/RemoveWindowsAI

The upstream tool advertises force removal of hidden/locked component
store packages, tasks and files; prevention of AI-package reinstalls;
and even a **Defender AI** feature toggle. Such actions risk Windows
servicing/security behavior and are outside Nightglass's
default security baseline. Avoid until its exact current code,
undo/repair path and effect on the targeted 26H2 build have been
evaluated separately. Prefer regular Windows settings/app policies
for unwanted Copilot/Recall options.

### Nightglass's own conservative "one shot" alternative

The project provides an **optional**, locally inspectable script:
`scripts/windows/Set-Nightglass-Windows11-Preferences.ps1`

It defaults to **preview only**, uses HKCU preferences, does not
download/execute any external tool, never touches core Windows
security/servicing/virtualization, creates a private restoration
snapshot on explicit `-Apply`, and has `-UndoFile` to restore
that snapshot. It is **NOT** a debloater and has no ISO editing/
partition/USB writing functions. Actual native PowerShell parsing,
application and undo remain UNVERIFIED until user-run tests. Do not
run during current Windows 10 work.

The optional script is intended ONLY for a later **already-installed,
licensed and verified Windows 11 system**, after source review and a
restore backup. It must pass a native PowerShell AST parser check and
a disposable Windows 11 VM Apply/Undo test before being trusted.

Example after those gates pass, in a local checkout:

    powershell.exe -NoProfile -File scripts/windows/Set-Nightglass-Windows11-Preferences.ps1 -Mode Preview

To apply **only** the eight user preference DWORDs, the owner may
later explicitly approve:

    powershell.exe -NoProfile -File scripts/windows/Set-Nightglass-Windows11-Preferences.ps1 -Mode Apply -Consent "APPLY NIGHTGLASS USER PREFERENCES"

A new snapshot path is displayed before changes. Keep that private
file, which is necessary for Undo:

    powershell.exe -NoProfile -File scripts/windows/Set-Nightglass-Windows11-Preferences.ps1 -Mode Undo -SnapshotPath "C:\path\to\prior-snapshot.json" -Consent "UNDO NIGHTGLASS USER PREFERENCES"

Undo checks that the preferences still equal the values the helper
applied and **skips** any settings subsequently changed by the user.
Neither applying nor undoing these registry preferences reinstalls
apps/components. Snapshot remains on disk for manual audit. These
commands are documentation for **future verification**, not an
instruction to execute on the present Windows 10 host.


## Deployment holds

The user explicitly said no install soon. Do not build or write USB
media now. When ready, check that the genuine Windows 11 and Fedora
KDE official ISOs both fit the user's *separate* 16 GB stick, that
Ventoy Secure Boot behavior meets the chosen trust policy, and that
portable Disk 1 (example backup-drive capacity backup media) has been **disconnected** before
any installer disk selection. USB preparation, Windows clean install,
and Fedora graphical installation require separate, explicit user
approval and independent backups/recovery readiness.

See ONE_USB_MULTIBOOT_PLAN.md and WINDOWS11_CLEAN_INSTALL_STAGED.md.

## Activation during setup or later (owner choice)

The user has a Pro key but may select **Activate later**, the default,
and choose **I don't have a product key** in official Microsoft Setup
if that page appears. **Verify Windows 11 Pro** edition explicitly:
the current device's previous Windows installation was Home and OEM
firmware may auto-select Home. A separately verified Pro-only NTLite
image can make edition selection more deterministic, but this does not
grant activation or authorize wiping a disk.

Alternatively enter the key privately into Microsoft Setup. Later
activation uses Settings > System > Activation > Change product key;
the key MUST NOT be saved in an ISO, NTLite unattended answer file,
the repository or any emitted logs.
See [Pro activate-later guide](WINDOWS11_PRO_ACTIVATE_LATER.md).

## Selected Pro customization profile

The user provided 32 detailed post-install preferences plus OneDrive,
promotional apps/Widgets and AI suite removal preferences.
A new [35-item execution-plan catalog](../config/windows11-pro-custom.json)
with reviewed/core versus separate-consent phases is documented in
[Windows 11 Pro 32-point profile](WINDOWS11_PRO_32_POINT_PROFILE.md).

The script `scripts/windows/Invoke-Nightglass-Win11ProCustom.ps1` defaults to a
read-only preview. Optional future `ApplyCore` is strictly gated on
an actually installed Windows 11 Pro system, backup confirmation,
explicit consent, an administrator terminal and an independently
reviewed and SHA256-pinned **local** Win11Debloat.ps1. It deliberately
refuses the supplied remote-downloader Get.ps1. It never performs app
uninstalls, disables Windows Update/security, decrypts BitLocker or
enables Sandbox/WSL as part of core. Native execution is UNVERIFIED.
