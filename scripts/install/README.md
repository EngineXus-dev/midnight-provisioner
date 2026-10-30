# Start here: installing Midnight Provisioner

These are the only scripts you need to install and run Midnight Provisioner. Fedora itself is installed with Fedora's official installer; these scripts never partition disks, change EFI/boot settings or create VMs.

## Before installing Fedora (on Windows, optional, read-only)

```powershell
powershell -NoProfile -File scripts\windows\check-windows-hardware.ps1
powershell -NoProfile -File scripts\windows\Review-Windows-DualBoot.ps1
```

Then plan disk encryption and review the target disk (`python -m midnight_provisioner install-preview --encryption luks2`), back up your data, and install Fedora KDE with the official installer (tick **Encrypt my data**).

## On Fedora, in order

| Step | Command | What it does |
|---|---|---|
| 1 | `bash scripts/install/fedora-dependencies.sh` | Installs the virtualization packages with `sudo dnf` after you type INSTALL |
| 2 | `bash scripts/install/setup-midnight-provisioner.sh` | Installs Midnight Provisioner into its own user venv (no sudo) |
| 3 | `bash scripts/install/fedora-host-acceptance.sh` | Read-only check that KVM, SELinux and libvirt are ready |
| 4 (optional) | `bash scripts/install/create-lab-network.sh` | Creates the isolated `midnight-provisioner-lab` network for Kali VMs |

Then start the app with `~/.local/share/midnight-provisioner/venv/bin/midnight-provisioner gui` and confirm encryption with `midnight-provisioner encryption-check`.

Run every script as your normal user, not with `sudo`.

Setup adds an application-menu entry and a desktop shortcut. ISO installations add the menu entry system-wide and create the desktop shortcut at each user's first desktop login. Git, firmware, diagnostic utilities and XDG desktop tools are included in the dependency configuration. Existing ISOs must be rebuilt to include these changes.
