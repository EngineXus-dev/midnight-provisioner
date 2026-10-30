# Midnight Provisioner dual-boot installer (Windows 11 + Fedora KDE)

You end up with Windows 11 and Fedora KDE side by side, Fedora's Linux side encrypted, and Midnight Provisioner plus its virtualization tools preinstalled. The boot menu at startup lets you pick either system.

**What's on the USB** (one folder each here):
- **[`Windows11/`](Windows11/README.md):** Microsoft's official Windows 11 ISO, used as-is or with AtlasOS injected.
- **Fedora + Midnight Provisioner:** the **Midnight Provisioner installer ISO** built here. It is Fedora's official Everything netinstall ISO with a Midnight Provisioner kickstart added by Fedora's own `mkksiso` tool. Fedora's signed boot files are untouched, so Secure Boot keeps working.

**What the Midnight Provisioner ISO presets:**
- KDE Plasma, the KVM/libvirt tools, Podman and Distrobox
- Fedora's own PySide6 package
- Midnight Provisioner in `/opt/midnight-provisioner`, with an app-menu entry
- SELinux enforcing and the firewall on
- Installer boot arguments `nvme_core.default_ps_max_latency_us=0 pcie_aspm=off nvme_core.multipath=N`, including the embedded EFI boot image used on USB

**What it never decides for you:**
- **The disk.** You choose it on the installer's *Installation Destination* screen, and you tick *Encrypt my data* there.
- **Partition and EFI changes.** The kickstart does not configure storage. Review Fedora's proposed actions and choose unallocated space on a shared disk or a dedicated Fedora disk with its own EFI partition.

The Fedora install downloads packages, so the PC or VM needs internet.

## 1. Prepare both ISOs

**Windows 11:** follow [`Windows11/README.md`](Windows11/README.md). It covers getting and checking the official ISO and, optionally, injecting AtlasOS with the security options to keep on.

**Fedora + Midnight Provisioner**, built in `Fedora/`:

1. Download the official **Fedora Everything netinstall** ISO (x86_64) and its `CHECKSUM` file from https://fedoraproject.org/misc/#everything into `scripts\iso\Fedora\`.
2. Build:
   - **Windows** (Docker Desktop with Linux containers). It finds both files in that folder by itself:
     ```powershell
     powershell -NoProfile -File scripts\iso\Fedora\Build-Midnight-Provisioner-Iso.ps1
     ```
     The new `Midnight-Provisioner-Installer-....iso` lands in the same folder. The build runs in a privileged Fedora container, because `mkksiso` needs loop devices.
   - **Fedora**:
     ```bash
     sudo dnf install lorax xorriso isomd5sum mtools python3-kickstart git gnupg2
     bash scripts/iso/Fedora/build-midnight-provisioner-iso.sh --iso scripts/iso/Fedora/Fedora-Everything-netinst-x86_64-44-1.7.iso \
          --checksum scripts/iso/Fedora/Fedora-Everything-44-1.7-x86_64-CHECKSUM --output scripts/iso/Fedora
     ```

The build first checks **Fedora's GPG signature** on `CHECKSUM` using Fedora's signing key, and reads the ISO hash only from the signed part. It refuses an ISO whose checksum doesn't match. It packages only **committed** Midnight Provisioner code and writes a `.sha256` file next to the new ISO. The kickstart re-checks the embedded Midnight Provisioner archive during installation and stops if it was altered.

The builder uses [`mkksiso --cmdline`](https://weldr.io/lorax/mkksiso.html#modifying-kernel-cmdline-arguments) to set the installer boot arguments. `--args` is not a supported mkksiso option. Before writing the SHA-256 sidecar, the builder extracts and checks every kernel entry in both ISO GRUB configurations and the embedded EFI images. Look for **ISO boot verification PASS**. The kickstart's `%post` settings affect the installed OS only; they cannot fix installer freezes.

Existing output files are never overwritten. To rebuild, use a new output folder, for example `-OutputDir scripts\iso\Fedora\nvme-fixed` on Windows, or create a new folder and pass `--output` on Linux. Then use the ISO from that folder; an older copy elsewhere still has its old boot settings.

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
3. **Fedora + Midnight Provisioner.** Attach the Midnight Provisioner ISO instead and boot it (VirtualBox: F12 at start, or put the optical drive first in the boot order).
   - **Installation Destination:** select the disk, keep *Automatic*, tick **Encrypt my data**, then **Done**, then set the passphrase.
     - If the installer says there isn't enough free space, **cancel**. *Reclaim space* deletes partitions, so only use it on purpose.
   - **User Creation:** create your user and tick *Make this user administrator*.
   - **Begin Installation.**
4. **Reboot and remove the ISO.**
   - The boot menu should list **Fedora** and **Windows Boot Manager**. Boot each once.
5. **In Fedora**, run these checks:
   ```bash
   midnight-provisioner encryption-check   # expect: ENCRYPTED
   midnight-provisioner doctor
   ```
   Then open **Midnight Provisioner Workspaces** from the app menu.
   - Inside a VM, KVM usually isn't available unless nested virtualization is on. VM features may report that; it isn't an installer problem.
6. **If Windows shows the wrong time after you've booted Fedora,** run this once in an administrator Command Prompt in Windows:
   `reg add "HKLM\SYSTEM\CurrentControlSet\Control\TimeZoneInformation" /v RealTimeIsUniversal /t REG_DWORD /d 1 /f`

## 3. Make the USB installer

| Option | How | Notes |
|---|---|---|
| **A. Rufus (Recommended for Windows)** | Select the `Midnight-Provisioner-Installer-*.iso`, click **START**, and select **Write in DD Image mode** when prompted. | Most popular Windows flasher. Preserves EFI boot signatures for Secure Boot. |
| **B. Fedora Media Writer** | Click *Select .iso file*, select the `Midnight-Provisioner-Installer-*.iso`, and pick your USB drive. | Official Fedora GUI utility. |
| **C. Ventoy (Multiboot USB)** | Install **Ventoy** on the USB drive, then copy the ISO files directly onto it (see `docs/ONE_USB_MULTIBOOT_PLAN.md`). | Enroll Ventoy's key once at first boot if Secure Boot is enabled. |
| **D. Linux / macOS Command Line (`dd`)** | `sudo dd if=Midnight-Provisioner-Installer-Fedora-*.iso of=/dev/sdX bs=4M status=progress conv=fsync` | Native raw block copy (`of` must be the drive node `/dev/sdX` or `/dev/rdiskN`, NOT a partition like `/dev/sdX1`). |

> **IMPORTANT RUFUS TIP:** When Rufus prompts *"ISOHybrid image detected"*, choose **Write in DD Image mode**. Standard ISO mode modifies hybrid bootloader files which can break EFI boot integrity.

Writing an ISO or installing Ventoy **erases the USB stick**. Double-check you picked the stick, not a disk.

## 4. Install on the real PC

1. Back up everything you want to keep, to a separate drive.
2. **Unplug every drive you are not installing to**, especially the portable backup drive (Disk 1 in `docs/ONE_USB_MULTIBOOT_PLAN.md`). Both installers list every connected disk.
3. Optionally run the read-only checks first: `scripts\windows\check-windows-hardware.ps1` and `scripts\windows\Review-Windows-DualBoot.ps1`.
4. Follow the same order as the VM test:
   1. Windows 11, leaving unallocated space. If Windows is already installed, shrink C: in *Disk Management* instead.
   2. Save the BitLocker recovery key and turn off Fast Startup.
   3. Boot the Midnight Provisioner installer: *Installation Destination*, then **Encrypt my data**, then install.
5. Keep Secure Boot on. `/boot` and the EFI partition are not encrypted by design; see `docs/DISK_ENCRYPTION.md`.

### Optional dual boot on separate drives

Use a dedicated Windows disk and a dedicated Fedora disk when you want each OS to keep its own boot files.

1. For a new Windows installation, power off and disconnect the Fedora target where possible. Install Windows on its own disk and confirm it boots.
2. Power off, disconnect the Windows disk, and connect the Fedora target. Boot the Fedora USB in UEFI mode and select that target only.
3. Use Fedora's automatic layout on the isolated disk, or create its own FAT32 EFI System Partition at `/boot/efi`, unencrypted `/boot`, and the chosen encrypted Linux storage manually. Do not place Fedora's EFI files on the Windows disk.
4. Shut down, reconnect both disks, and choose **Windows Boot Manager** or **Fedora** in the firmware boot menu. Test each OS with the other disk disconnected, powering off between changes.

If disk isolation is unavailable, explicitly assign the Fedora target's own EFI partition in custom partitioning and inspect the proposed bootloader destination. A separate Linux data disk can still depend on the Windows disk if its ESP is reused. The [main README](../../README.md#two-drives-independent-windows-and-fedora-disks) explains the layout and verification steps.

## Troubleshooting common installation issues

- **NVMe SSD hangs or shows "Input/output error" during formatting:**
  NVMe power management is one possible cause. A freeze at network setup or `ext4` formatting alone does not establish whether TRIM, the controller, or another component is responsible.
  * **Current ISO builds:** the workaround is already on all installer boot entries. Rebuild and replace the old ISO on your USB, or flash the new ISO using the steps above.
  * **Older ISO:** at the GRUB menu, press `e`, add `nvme_core.default_ps_max_latency_us=0 pcie_aspm=off nvme_core.multipath=N` to the `linux` line, then press `Ctrl+X`.
  * **Verify the running installer:** in its shell, run `cat /proc/cmdline` and confirm all three parameters are present. This proves which options actually booted, regardless of the ISO filename.
  * APST is disabled by the NVMe latency setting. [`pcie_aspm=off`](https://docs.kernel.org/admin-guide/kernel-parameters.html) tells Linux to leave firmware ASPM configuration unchanged; it does not guarantee firmware disabled ASPM. These options do not disable formatting-time TRIM/discard.
  * Do not add `nodmraid` as a Fedora 44 fix: [Fedora removed the dmraid/nodmraid installer options in Fedora 38](https://docs.fedoraproject.org/en-US/fedora/f38/release-notes/sysadmin/Installation/).
  * If it still freezes with the parameters confirmed, capture the kernel errors (`dmesg | tail -n 80`) and installer storage log (`/tmp/storage.log`) before choosing another partition/format action. Those errors are needed to distinguish discard failures from controller resets and USB problems.
- **"Error setting up repositories" on Installation Source:**
  Because the base installer uses Fedora's Everything netinstall ISO, software packages are not stored on the USB disc itself (`sr0`).
  * **Fix:** Click **Network & Host Name**, turn your network connection **ON**, then under **Installation Source** select **On the network** (*Closest mirror*).
- **USB drive disconnects or grays out after network setup:**
  USB 3.0 controller power resets during network initialization can briefly drop the USB drive.
  * **Fix:** Use a black **USB 2.0 port** on your PC/laptop, or write the ISO using **Fedora Media Writer** or Rufus in **DD Image mode**.

## Updating Midnight Provisioner later

The ISO installs a fixed copy of Midnight Provisioner, so `midnight-provisioner update` (which needs a git checkout) won't apply. To get a newer version, rebuild the ISO, or clone the repository and use `scripts/install/setup-midnight-provisioner.sh`.
