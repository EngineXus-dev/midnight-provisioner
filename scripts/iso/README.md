# Nightglass dual-boot installer (Windows 11 + Fedora KDE)

You end up with Windows 11 and Fedora KDE side by side, Fedora's Linux side encrypted, and Nightglass plus its virtualization tools preinstalled. The boot menu at startup lets you pick either system.

**What's on the USB** (one folder each here):
- **[`Windows11/`](Windows11/README.md):** Microsoft's official Windows 11 ISO, used as-is or with AtlasOS injected.
- **Fedora + Nightglass:** the **Nightglass installer ISO** built here. It is Fedora's official Everything netinstall ISO with a Nightglass kickstart added by Fedora's own `mkksiso` tool. Fedora's signed boot files are untouched, so Secure Boot keeps working.

**What the Nightglass ISO presets:**
- KDE Plasma, the KVM/libvirt tools, Podman and Distrobox
- Fedora's own PySide6 package
- Nightglass in `/opt/nightglass`, with an app-menu entry
- SELinux enforcing and the firewall on

**What it never decides for you:**
- **The disk.** You choose it on the installer's *Installation Destination* screen, and you tick *Encrypt my data* there.
- **Anything already on the disk.** Fedora's automatic layout only uses free space and shares Windows' EFI partition, so Windows keeps working.

The Fedora install downloads packages, so the PC or VM needs internet.

## 1. Prepare both ISOs

**Windows 11:** follow [`Windows11/README.md`](Windows11/README.md). It covers getting and checking the official ISO and, optionally, injecting AtlasOS with the security options to keep on.

**Fedora + Nightglass**, built in `Fedora/`:

1. Download the official **Fedora Everything netinstall** ISO (x86_64) and its `CHECKSUM` file from https://fedoraproject.org/misc/#everything into `scripts\iso\Fedora\`.
2. Build:
   - **Windows** (Docker Desktop with Linux containers). It finds both files in that folder by itself:
     ```powershell
     powershell -NoProfile -File scripts\iso\Fedora\Build-Nightglass-Iso.ps1
     ```
     The new `Nightglass-Installer-....iso` lands in the same folder. The build runs in a privileged Fedora container, because `mkksiso` needs loop devices.
   - **Fedora**:
     ```bash
     sudo dnf install lorax xorriso isomd5sum python3-kickstart git gnupg2
     bash scripts/iso/Fedora/build-nightglass-iso.sh --iso scripts/iso/Fedora/Fedora-Everything-netinst-x86_64-44-1.7.iso \
          --checksum scripts/iso/Fedora/Fedora-Everything-44-1.7-x86_64-CHECKSUM --output scripts/iso/Fedora
     ```

The build first checks **Fedora's GPG signature** on `CHECKSUM` using Fedora's signing key, and reads the ISO hash only from the signed part. It refuses an ISO whose checksum doesn't match. It packages only **committed** Nightglass code and writes a `.sha256` file next to the new ISO. The kickstart re-checks the embedded Nightglass archive during installation and stops if it was altered.

## 2. Test in a virtual machine first

VirtualBox 7.1 or newer is the easiest way to test both systems in one VM: it can enroll both Microsoft Secure Boot keys and emulate TPM 2.0.

Hyper-V's Secure Boot templates are set per VM ("Microsoft Windows" vs "Microsoft UEFI Certificate Authority"), so a Windows + Fedora test there may need the template changed between installs.

**VM settings:**

| Setting | Value |
|---|---|
| Type | Windows 11 (64-bit) |
| Firmware | EFI on, Secure Boot on (default Microsoft keys), TPM 2.0 |
| Memory and CPUs | 8 GB RAM, 4 CPUs |
| Disk | 128 GB dynamic |
| Network | NAT |

**Steps:**

1. **Windows first.** Attach the Windows 11 ISO from `Windows11/` and boot it. For an AtlasOS ISO, also follow `Windows11/README.md` step 3.
   - At *Where do you want to install Windows?*, select the empty disk, click **New**, enter about `65536` MB, then **Apply** and **Next**.
   - The remaining space stays *Unallocated*, ready for Fedora.
2. **In Windows, before Fedora:**
   - If *Device encryption* / BitLocker is on, save the recovery key (Settings › Privacy & security › Device encryption).
   - Turn off Fast Startup (Control Panel › Power Options › *Choose what the power buttons do*).
   - Shut down.
3. **Fedora + Nightglass.** Attach the Nightglass ISO instead and boot it (VirtualBox: F12 at start, or put the optical drive first in the boot order).
   - **Installation Destination:** select the disk, keep *Automatic*, tick **Encrypt my data**, then **Done**, then set the passphrase.
     - If the installer says there isn't enough free space, **cancel**. *Reclaim space* deletes partitions, so only use it on purpose.
   - **User Creation:** create your user and tick *Make this user administrator*.
   - **Begin Installation.**
4. **Reboot and remove the ISO.**
   - The boot menu should list **Fedora** and **Windows Boot Manager**. Boot each once.
5. **In Fedora**, run these checks:
   ```bash
   nightglass encryption-check   # expect: ENCRYPTED
   nightglass doctor
   ```
   Then open **Nightglass Workspaces** from the app menu.
   - Inside a VM, KVM usually isn't available unless nested virtualization is on. VM features may report that; it isn't an installer problem.
6. **If Windows shows the wrong time after you've booted Fedora,** run this once in an administrator Command Prompt in Windows:
   `reg add "HKLM\SYSTEM\CurrentControlSet\Control\TimeZoneInformation" /v RealTimeIsUniversal /t REG_DWORD /d 1 /f`

## 3. Make the USB installer

| Option | How | Notes |
|---|---|---|
| **A. One stick at a time** (simplest) | Write Windows 11 with Microsoft's Media Creation Tool. Later, write the Nightglass ISO with **Fedora Media Writer** (*Select .iso file*) | Works with Secure Boot as-is |
| **B. One stick with both** | Install **Ventoy** on the stick and copy both ISO files onto it (see `docs/ONE_USB_MULTIBOOT_PLAN.md`) | With Secure Boot on, you enroll Ventoy's key once at first boot |

Writing an ISO or installing Ventoy **erases the USB stick**. Double-check you picked the stick, not a disk.

## 4. Install on the real PC

1. Back up everything you want to keep, to a separate drive.
2. **Unplug every drive you are not installing to**, especially the portable backup drive (Disk 1 in `docs/ONE_USB_MULTIBOOT_PLAN.md`). Both installers list every connected disk.
3. Optionally run the read-only checks first: `scripts\windows\check-windows-hardware.ps1` and `scripts\windows\Review-Windows-DualBoot.ps1`.
4. Follow the same order as the VM test:
   1. Windows 11, leaving unallocated space. If Windows is already installed, shrink C: in *Disk Management* instead.
   2. Save the BitLocker recovery key and turn off Fast Startup.
   3. Boot the Nightglass installer: *Installation Destination*, then **Encrypt my data**, then install.
5. Keep Secure Boot on. `/boot` and the EFI partition are not encrypted by design; see `docs/DISK_ENCRYPTION.md`.

## Updating Nightglass later

The ISO installs a fixed copy of Nightglass, so `nightglass update` (which needs a git checkout) won't apply. To get a newer version, rebuild the ISO, or clone the repository and use `scripts/install/setup-nightglass.sh`.
