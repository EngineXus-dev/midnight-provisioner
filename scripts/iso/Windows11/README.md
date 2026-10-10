# Windows 11 side of the dual-boot installer

Put the Windows 11 ISO you will install in this folder. ISO files are ignored by git and never committed.

You have two choices:

| Choice | What you get |
|---|---|
| **Official ISO** (simplest) | Stock Windows 11. Optionally apply Nightglass's reviewed privacy tweaks later with `scripts\windows\Invoke-Nightglass-Win11ProCustom.ps1`. |
| **AtlasOS-injected ISO** | Windows installs already set up as AtlasOS ([AtlasOS ISO injection guide](https://docs.atlasos.net/getting-started/install/install-iso-injection/)). |

## Before you start

- **Windows 11 Pro is required for AtlasOS.** Atlas does not support Home, and this PC has Windows 10 Home today. Choose **Windows 11 Pro** in Setup and pick *I don't have a product key* if you'll activate later; see `docs/WINDOWS11_PRO_ACTIVATE_LATER.md`.
- **AtlasOS calls ISO injection *experimental*.** Its tool, AME Wizard, runs on Windows only.
- **AtlasOS is a third-party modification of Windows.** It permanently removes Smart App Control, uninstalls Edge and OneDrive, and turns off telemetry.

## 1. Get and check the official ISO

1. Download **Windows 11 (multi-edition ISO) x64** from https://www.microsoft.com/software-download/windows11 into this folder.
2. Compare its hash with the SHA-256 Microsoft lists under *Verify your download* on that page:
   ```powershell
   Get-FileHash .\scripts\iso\Windows11\Win11_*.iso -Algorithm SHA256
   ```

If you're not using AtlasOS, you're done here: use that ISO as-is.

## 2. Inject AtlasOS (optional)

1. From https://atlasos.net, click **Get started**, then **Already following the guide?**, and download **Atlas Playbook** and **AME Wizard**. Extract both.
2. Open `AME Wizard Beta.exe` and click **Updates** to make sure it's current.
3. Drag the ISO from this folder into AME Wizard, then drag in `Atlas Playbook.apbx`.
4. Select the ISO on the left, then **Select a playbook to modify**, then **AtlasOS**, then **OK**, then **Next**.
5. In the playbook options, **keep these security features on.** Nightglass is a security tool, and these protect Windows and the shared PC:
   - **Windows Defender:** don't disable it.
   - **CPU security mitigations:** keep the Windows default.
   - **Core isolation (VBS / memory integrity):** don't disable it, even though Atlas suggests it for speed.
   - **Automatic Windows updates:** leave them on.
6. Drivers: keep **Include additional network drivers** selected.
7. Set a username and **a password**. Don't leave it blank.
8. Wait for the injection to finish, and save the new ISO in this folder.

## Optional: make the ISO smaller

**Size reduction isn't built into either option.** AtlasOS trims Windows *after* it's installed (removing apps); it doesn't shrink the ISO. **You don't need to shrink it:** both ISOs already fit on a 16 GB stick.

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

**What it deliberately does not do:** strip Windows components ("tiny11"-style). That breaks Windows Update, Defender, WinRE or BitLocker, which a Nightglass PC relies on. `docs/WINDOWS11_LITE_IMAGE_PROFILE.md` has the longer-term, still-conservative NTLite plan.

**With AtlasOS,** inject first, then trim the injected ISO. Or trim with `-Format Wim` first, since AME Wizard may need a mountable image. Either way, test the result in a VM.

## 3. Install Windows, leaving room for Fedora

1. **Unplug every drive you're not installing to**, especially the portable Disk 1. Windows Setup lists every connected disk.
2. Boot the ISO: the USB stick, or the VM's optical drive for a test.
   - With Ventoy, choose the ISO, then **Boot in normal mode**. On the first Windows 11 screen, click **Next** twice, then **Previous version of setup** (bottom left), as the AtlasOS guide says.
3. Choose **Custom: Install Windows only (advanced)**.
4. At **Where do you want to install Windows?**
   - **Empty disk:** select it, click **New**, give Windows the size you want (for example `200000` MB on the 465 GB disk), then **Apply** and **Next**. The rest stays *Unallocated* for Fedora.
   - **Never** use AtlasOS's *Deleting data on all drives* option on this PC.
   - **Reinstalling over the existing Windows** (its *Keeping data* route) keeps the old partition size. Shrink C: in *Disk Management* first if Fedora needs the space.
5. In the AtlasOS first-run setup, connect to the internet when asked and wait for its new-user script to finish.
6. Before installing Fedora:
   - Save the BitLocker recovery key if device encryption is on.
   - Turn off Fast Startup.
   - Shut down.

Next: the Fedora side, in [`../Fedora`](../README.md#1-build-the-nightglass-installer-iso), and the overall order in [`../README.md`](../README.md).
