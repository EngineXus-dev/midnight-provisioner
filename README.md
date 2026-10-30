# Midnight Provisioner

**Local workspace management and workstation setup for Fedora KDE.**

Midnight Provisioner brings KVM virtual machines, trusted development containers, and host diagnostics into a desktop app and command-line interface. Organize personal work, development, and authorized security research from one place, with resource limits suited to your machine.

[Installation](#installation) · [Documentation](docs/README.md) · [Security model](docs/SECURITY_MODEL.md) · [Contributing](CONTRIBUTING.md)

## Features

- **Desktop and CLI controls** for workspace status, VM launch and shutdown, console access, and binding existing libvirt guests.
- **Workspace policies** that inspect restricted VM configurations before Midnight Provisioner starts them.
- **Trusted development environments** using rootless Podman and Distrobox.
- **Resource profiles** with RAM and concurrent-VM limits based on host hardware, plus memory and active-VM monitoring.
- **Host diagnostics** for virtualization readiness, storage discovery, disk encryption, and Fedora security settings.
- **VM preparation and recovery tools** for ISO verification, cold backups, integrity checks, and recovery into separate staging folders.
- **Fedora installer ISO tooling** to build installation media with KDE, virtualization packages, and Midnight Provisioner included.

## Workspaces

| Workspace | Environment | Intended use |
| --- | --- | --- |
| Personal Desktop | Native Fedora KDE | Everyday applications, browsing, and media |
| Trusted Development | Distrobox / rootless Podman | Development with trusted code and host-file access |
| Authorized Pentesting | KVM / libvirt VM | Authorized testing, offline or on the configured isolated lab network |
| Malware Analysis | KVM / libvirt VM | Offline research with restricted guest devices and host integration |

Create VM guests with virt-manager, then use **Bind VM** in Midnight Provisioner to associate them with a workspace. The [VM preparation guide](docs/VM_PREPARATION.md) covers image checks and guest configuration.

## Requirements

- Fedora KDE for the desktop application.
- Python 3.11 or newer; the application installer installs PySide6 into a dedicated environment.
- KVM/QEMU and libvirt for VM workspaces, with hardware virtualization available.
- Podman and Distrobox for the trusted development workspace.
- Enough available RAM and storage for the guests you intend to run.

The Windows utilities provide installation planning and hardware checks. The Midnight Provisioner desktop app runs on Fedora.

## Installation

### On an existing Fedora desktop

Clone the repository, then run the setup scripts as your regular desktop user:

```bash
git clone https://github.com/EngineXus-dev/midnight-provisioner.git
cd midnight-provisioner

# Review and confirm installation of system virtualization packages.
bash scripts/install/fedora-dependencies.sh

# Install Midnight Provisioner into its own user Python environment.
bash scripts/install/setup-midnight-provisioner.sh
```

Start the app using the launch command printed by the installer. With the default data directory:

```bash
"$HOME/.local/share/midnight-provisioner/venv/bin/midnight-provisioner" gui
```

Keep the source checkout in place: setup uses an editable installation. Review libvirt access and host readiness using the [installation guide](scripts/install/README.md). Run Midnight Provisioner as your regular user.

### With the Midnight Provisioner Fedora installer ISO

The [installer media guide](scripts/iso/README.md) explains how to build an ISO from Fedora's official Everything netinstall image, test it, and prepare a USB installer. It also covers installation alongside Windows.

Fedora's installer handles operating-system installation and partitioning. You choose the destination disk and encryption settings there. Back up any data you want to keep before formatting a drive or partition.

## Using Midnight Provisioner

Open the GUI, choose a workspace, and use its controls to enter a development container or manage a bound VM. **Machine settings** provides Automatic, Compact, Balanced, and Performance resource profiles; allocations remain limited by the detected host hardware.

For a source installation, activate Midnight Provisioner's Python environment to use the CLI. ISO installations provide the `midnight-provisioner` command directly:

```bash
source "${XDG_DATA_HOME:-$HOME/.local/share}/midnight-provisioner/venv/bin/activate"
```

```bash
midnight-provisioner list
midnight-provisioner doctor
midnight-provisioner resources
midnight-provisioner inspect pentest
midnight-provisioner --help
```

Workspace configuration lives in `~/.config/midnight-provisioner/workspaces.json`, or under `$XDG_CONFIG_HOME` when set. Moving VM workspaces to another computer also requires transferring or recreating their guest disks and host configuration.

## Security model

Midnight Provisioner relies on Fedora, KVM/QEMU, libvirt, and SELinux for isolation. It checks restricted guest definitions before launches issued through the app; administrators and external virtualization tools can bypass those checks. Midnight Provisioner does not provide Qubes OS's security architecture or guarantee malware containment.

Distrobox shares the host environment and is intended for trusted code. Use dedicated analysis hardware for high-risk samples, and read the [security model](docs/SECURITY_MODEL.md) before configuring restricted guests. See [SECURITY.md](SECURITY.md) for reporting security issues.

## Documentation

- [Install and configure Midnight Provisioner](scripts/install/README.md)
- [Build installer media and set up dual boot](scripts/iso/README.md)
- [Disk encryption](docs/DISK_ENCRYPTION.md)
- [Prepare VM guests](docs/VM_PREPARATION.md)
- [Cold backups](docs/COLD_BACKUP.md) and [recovery staging](docs/RECOVERY_STAGING.md)
- [Complete documentation index](docs/README.md)

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup and pull-request guidance. Run the local verifier from the repository root:

```bash
python3 -B scripts/testing/verify_local.py
```

On Windows, use `python -B scripts/testing/verify_local.py`; the runner selects a portable subset. Fedora host and virtualization checks are described in the [testing guides](docs/README.md#development-and-verification).

## License

Midnight Provisioner is open source under the [MIT License](LICENSE).

## Sources and upstream projects

Official source repositories and documentation for the platforms, libraries, tools, and optional guides referenced by Midnight Provisioner. Each upstream project retains its own license.

### Platform and application

- [Fedora KDE](https://fedoraproject.org/kde/download/)
- [KDE Plasma](https://kde.org/plasma-desktop/)
- [Python documentation](https://docs.python.org/3/)
- [Qt for Python / PySide6](https://doc.qt.io/qtforpython-6/)
- [Qubes OS documentation (design inspiration)](https://doc.qubes-os.org/en/latest/)
- [Setuptools](https://setuptools.pypa.io/en/latest/)
- [Wheel packaging](https://wheel.readthedocs.io/en/stable/)
- [Git](https://git-scm.com/docs)
- [Fedora SELinux guidance](https://docs.fedoraproject.org/en-US/quick-docs/selinux-getting-started/)

### Virtualization and containers

- [Linux KVM](https://docs.kernel.org/virt/kvm/index.html)
- [QEMU](https://www.qemu.org/docs/master/)
- [qemu-img](https://www.qemu.org/docs/master/tools/qemu-img.html)
- [libvirt documentation](https://libvirt.org/docs.html)
- [virsh](https://libvirt.org/manpages/virsh.html)
- [virt-xml-validate](https://libvirt.org/manpages/virt-xml-validate.html)
- [virt-manager and virt-install](https://virt-manager.org/)
- [virt-install reference](https://github.com/virt-manager/virt-manager/blob/main/man/virt-install.rst)
- [Podman](https://docs.podman.io/en/latest/)
- [Distrobox](https://distrobox.it/)
- [Docker Desktop on Windows](https://docs.docker.com/desktop/setup/install/windows-install/)
- [Official Ubuntu container images](https://hub.docker.com/_/ubuntu)

### Guest environments

- [Kali tool catalog](https://www.kali.org/tools/)
- [Kali metapackages](https://www.kali.org/docs/general-use/metapackages/)
- [Updating Kali](https://www.kali.org/docs/general-use/updating-kali/)

### Installer, encryption, and boot media

- [Fedora Everything installer](https://fedoraproject.org/misc/#everything)
- [Fedora signing keys and verification](https://fedoraproject.org/security/)
- [Fedora UEFI guidance](https://fedoraproject.org/wiki/Unified_Extensible_Firmware_Interface)
- [Lorax / mkksiso](https://weldr.io/lorax/mkksiso.html)
- [Pykickstart](https://pykickstart.readthedocs.io/en/latest/)
- [GNU xorriso](https://www.gnu.org/software/xorriso/)
- [isomd5sum source](https://github.com/rhinstaller/isomd5sum)
- [cryptsetup / LUKS](https://gitlab.com/cryptsetup/cryptsetup)
- [GnuPG documentation](https://gnupg.org/documentation/)
- [Linux kernel boot parameters](https://docs.kernel.org/admin-guide/kernel-parameters.html)
- [Fedora installer option changes](https://docs.fedoraproject.org/en-US/fedora/f38/release-notes/sysadmin/Installation/)
- [Rufus](https://rufus.ie/en/)
- [Fedora Media Writer source](https://github.com/FedoraQt/MediaWriter)
- [Ventoy source](https://github.com/ventoy/Ventoy)
- [Ventoy Secure Boot guidance](https://www.ventoy.net/en/doc_secure.html)
- [GNU Mtools](https://www.gnu.org/software/mtools/)

<details>
<summary>Windows preparation references</summary>

- [Official Windows 11 download](https://www.microsoft.com/en-us/software-download/windows11)
- [Windows 11 requirements](https://www.microsoft.com/en-us/windows/windows-11-specifications?r=1)
- [Windows activation](https://support.microsoft.com/en-us/windows/activation/activate-windows)
- [BitLocker key management](https://learn.microsoft.com/en-us/windows/security/operating-system-security/data-protection/bitlocker/faq)
- [Windows device encryption](https://support.microsoft.com/en-us/windows/security/encryption/device-encryption-in-windows)
- [TPM inspection](https://learn.microsoft.com/en-us/powershell/module/trustedplatformmodule/get-tpm?view=windowsserver2025-ps)
- [Secure Boot inspection](https://learn.microsoft.com/en-us/powershell/module/secureboot/confirm-securebootuefi?view=windowsserver2025-ps)
- [REAgentC and Windows recovery](https://learn.microsoft.com/en-us/windows-hardware/manufacture/desktop/reagentc-command-line-options?view=windows-11)
- [powercfg](https://learn.microsoft.com/en-us/windows-hardware/design/device-experiences/powercfg-command-line-options)
- [Fast Startup behavior](https://learn.microsoft.com/en-us/troubleshoot/windows-client/setup-upgrade-and-drivers/fast-startup-causes-system-hibernation-shutdown-fail)
- [Windows diagnostic data controls](https://learn.microsoft.com/en-us/windows/privacy/configure-windows-diagnostic-data-in-your-organization)
- [Supported AMD processors](https://learn.microsoft.com/en-us/windows-hardware/design/minimum/supported/windows-11-supported-amd-processors)
- [Windows Sandbox](https://learn.microsoft.com/en-us/windows/security/application-security/application-isolation/windows-sandbox/windows-sandbox-install)
- [Windows Subsystem for Linux](https://learn.microsoft.com/en-us/windows/wsl/install)

</details>

<details>
<summary>Optional Windows customization references</summary>

- [AtlasOS](https://atlasos.net/)
- [AtlasOS ISO injection guide](https://docs.atlasos.net/getting-started/install/install-iso-injection/)
- [AME Wizard / AME Labs](https://amelabs.net/)
- [NTLite](https://ntlite.com/)
- [NTLite image export guide](https://ntlite.com/docs/guides/export/)
- [NTLite Windows Lite guide](https://ntlite.com/docs/guides/windows-lite/)
- [Win11Debloat source](https://github.com/Raphire/Win11Debloat)
- [Win11Debloat wiki](https://github.com/Raphire/Win11Debloat/wiki/)
- [Win11Debloat reversal guidance](https://github.com/Raphire/Win11Debloat/wiki/Reverting-Changes)
- [Chris Titus Tech Windows Utility source](https://github.com/ChrisTitusTech/winutil)
- [RemoveWindowsAI source](https://github.com/zoicware/RemoveWindowsAI)

</details>
