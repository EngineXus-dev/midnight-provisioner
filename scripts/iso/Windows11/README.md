# Windows 11 installation and customization

Use this workflow for a standalone Windows 11 installation or the Windows side of an optional Fedora dual boot. Put the Windows ISO in this folder; ISO files are ignored by Git.

You have two choices:

| Choice | What you get |
|---|---|
| **Official ISO** (simplest) | Stock Windows 11. Optionally apply Midnight Provisioner's reviewed privacy tweaks later with `scripts\windows\Invoke-Midnight-Provisioner-Win11ProCustom.ps1`. |
| **AtlasOS-injected ISO** | Windows installs already set up as AtlasOS ([AtlasOS ISO injection guide](https://docs.atlasos.net/getting-started/install/install-iso-injection/)). |

## Before you start

- **Choose the edition matching your license.** Stock Windows can use the appropriate Home or Pro edition. AtlasOS and the ApplyCore customization wrapper require Pro; see the [activation guide](../../../docs/WINDOWS11_PRO_ACTIVATE_LATER.md).
- **AtlasOS calls ISO injection *experimental*.** Its tool, AME Wizard, runs on Windows only.
- **AtlasOS is a third-party modification of Windows.** It applies its own app, service, privacy, and security changes. Review its configuration options before building an image; Midnight Provisioner's preference Undo does not reverse AtlasOS changes.

## 1. Get and check the official ISO

1. Download **Windows 11 (multi-edition ISO) x64** from https://www.microsoft.com/software-download/windows11 into this folder.
2. Compare its hash with the SHA-256 Microsoft lists under *Verify your download* on that page:
   ```powershell
   Get-FileHash .\scripts\iso\Windows11\Win11_*.iso -Algorithm SHA256
   ```

For the stock Windows route, use the official ISO as the base image and continue to the installation and post-install customization steps below.

## 2. Inject AtlasOS (optional)

1. From https://atlasos.net, click **Get started**, then **Already following the guide?**, and download **Atlas Playbook** and **AME Wizard**. Extract both.
2. Open `AME Wizard Beta.exe` and click **Updates** to make sure it's current.
3. Drag the ISO from this folder into AME Wizard, then drag in `Atlas Playbook.apbx`.
4. Select the ISO on the left, then **Select a playbook to modify**, then **AtlasOS**, then **OK**, then **Next**.
5. In the playbook options, **keep these security features on.** Midnight Provisioner is a security tool, and these protect Windows and the shared PC:
   - **Windows Defender:** don't disable it.
   - **CPU security mitigations:** keep the Windows default.
   - **Core isolation (VBS / memory integrity):** don't disable it, even though Atlas suggests it for speed.
   - **Automatic Windows updates:** leave them on.
6. Drivers: keep **Include additional network drivers** selected.
7. Set a username and **a password**. Don't leave it blank.
8. Wait for the injection to finish, and save the new ISO in this folder.

## Optional: make the ISO smaller

**Size reduction isn't built into either option.** AtlasOS trims Windows *after* it's installed (removing apps); it doesn't shrink the ISO. Check the actual ISO sizes against the usable capacity of your chosen USB drive; a single-edition export is optional.

If you want a smaller ISO anyway, the safe trim is to keep only the edition you install:

```powershell
# Elevated PowerShell. Needs the Windows ADK "Deployment Tools" for oscdimg.
powershell -NoProfile -File scripts\iso\Windows11\Optimize-Windows11Iso.ps1            # Windows 11 Pro, compact install.esd
powershell -NoProfile -File scripts\iso\Windows11\Optimize-Windows11Iso.ps1 -Format Wim # keeps a mountable install.wim
```

**What the script does:**
- Exports only **Windows 11 Pro** (`-Edition` to change) with DISM, in Microsoft's compact format.
- Rebuilds the ISO with the original signed boot files, so Secure Boot is unaffected.
- Writes a new `...-single-edition.iso` and its `.sha256`, and leaves the original unchanged.

How much smaller it gets depends on the ISO, and the script prints the before and after sizes.

**What it deliberately does not do:** strip Windows components ("tiny11"-style). That breaks Windows Update, Defender, WinRE or BitLocker, which a Midnight Provisioner PC relies on. `docs/WINDOWS11_LITE_IMAGE_PROFILE.md` has the longer-term, still-conservative NTLite plan.

**With AtlasOS,** inject first, then trim the injected ISO. Or trim with `-Format Wim` first, since AME Wizard may need a mountable image. Either way, test the result in a VM.

## Create the Windows USB

**[Rufus](https://rufus.ie/en/) is the recommended USB writer for Windows 11 media.**

1. Select the intended USB stick and the official, single-edition, or reviewed customized Windows ISO in Rufus.
2. Use the Windows installation workflow and the UEFI/GPT configuration for this project. Confirm the selected USB can be erased, then write the image and wait for completion.
3. Safely eject the stick and boot its UEFI entry. Microsoft's Media Creation Tool is an alternative for stock Windows media.

For the separate Fedora/Midnight Provisioner ISO, use **Fedora Media Writer** as recommended in the [Fedora media guide](../README.md#3-make-the-usb-installer). Its DD-mode alternative is specific to Fedora media; do not apply those instructions to the Windows ISO.

## 3. Install Windows for your chosen layout

1. Back up the files you want to keep and disconnect unrelated storage, especially backup drives. Identify the installation disk by model and capacity.
2. Boot the Windows USB's UEFI entry and select a clean installation. Setup wording depends on the Windows release. For an AtlasOS image, follow the [upstream installation instructions](https://docs.atlasos.net/getting-started/install/install-iso-injection/), including any instruction to use the previous setup interface.
3. Select the edition matching your license. AtlasOS and Midnight Provisioner's ApplyCore wrapper require Pro. Choose **I don't have a product key** when offered to activate later; verify the actual edition before proceeding.
4. Choose the storage layout:
   - **Windows only:** allocate the intended Windows disk as needed; no Fedora partition or reserved Linux space is required.
   - **Shared-disk dual boot:** allocate the Windows portion and leave the Fedora space unallocated. For an existing installation, shrink its NTFS volume using Windows Disk Management.
   - **Separate-drive dual boot:** install Windows on drive A while drive B is disconnected where possible. Windows gets its own EFI, Windows, and recovery partitions. Later install Fedora on drive B while drive A is disconnected, giving Fedora its own EFI partition.
5. Confirm the target and proposed changes, then complete Windows setup. Install OEM drivers and Windows updates, verify activation and recovery, and save any Device Encryption/BitLocker recovery key.
6. For dual boot, disable Fast Startup and shut Windows down fully before installing Fedora. Follow the [shared-disk and separate-drive instructions](../../../README.md#optional-windows-11-and-fedora-dual-boot).

## 4. Customize the installed Windows system

The Windows utilities run directly in Windows PowerShell and can be used on a Windows-only machine.

```powershell
# Read the 35-item catalog and fixed core selection.
powershell -NoProfile -File scripts\windows\Invoke-Midnight-Provisioner-Win11ProCustom.ps1 -Mode Preview

# Read the smaller per-user preference plan.
powershell -NoProfile -File scripts\windows\Set-Midnight-Provisioner-Windows11-Preferences.ps1 -Mode Preview
```

The Pro wrapper's **ApplyCore** mode requires an elevated terminal, a reviewed local Win11Debloat release with its supporting files, the reviewed main script's SHA-256, backup confirmation, and literal consent. It executes a fixed settings allowlist and requests a restore point. It excludes app removal, decryption, OS installation, and enabling WSL/Sandbox. The per-user preference helper uses eight HKCU DWORDs, creates a snapshot before applying changes, and supports guarded Undo.

See the [standalone Windows README section](../../../README.md#standalone-windows-11-installation-and-customization) for installation commands, image/customization choices, and ApplyCore usage, and the [settings catalog and technical limits](../../../docs/WINDOWS11_PRO_32_POINT_PROFILE.md) for the complete profile.
