# Windows 10 → Fedora KDE dual-boot rollout (manual, reversible)

**Do not run disk-partitioning automation.** A UEFI/ESP modification could make the existing Windows installation unbootable if performed incorrectly. This phase is only a plan and read-only diagnostic tooling.

### Stage A — on Windows

- Verify laptop manufacturer/model and whether memory/second internal NVMe can be upgraded. With 8 GB RAM, budget ~3 GB for one Kali VM and stop other VMs before launching it.
- Run `scripts/check-windows-hardware.ps1`. It does not change Windows. Check Win10 support/ESU situation.
- Create and test a full-disk backup to disconnected storage; preserve recovery keys and a Windows recovery USB.
- Identify firmware type (UEFI preferred), actual disk inventory, size of free space, ESP/Recovery/BitLocker layout. Disable Windows Fast Startup before later mounting Windows NTFS read-write from Linux. Do not use Linux to modify Windows files while Windows is hibernated.
- Test Fedora KDE live USB for Wi-Fi, sleep/resume, display scaling, AMD integrated graphics and peripherals.

### Stage B — install Fedora KDE

- Preferred: independent second internal SSD, with its own EFI partition where practical. Otherwise shrink Windows volume using Windows Disk Management **only after verifying backups**. If using an external SSD, test boot reliability and disconnection safety.
- Install Fedora KDE via its graphical installer, inspect **every proposed partition deletion/format action** before confirming. Preserve Windows EFI/recovery/data partitions. Do not choose automatic whole-disk erase on a dual-boot target.
- Prefer LUKS2 for Linux data and Btrfs snapshots if correctly configured; understand that snapshot rollback != backup.
- Use UEFI firmware boot chooser to select Windows/Fedora initially. **Avoid replacing Windows Boot Manager or adding rEFInd until the dual boot is independently verified.**
- Ensure both OS boot entries work, Windows backup recovery remains possible, and Secure Boot handling is understood.

### Stage C — optional virtualization and Nightglass

- Run `./scripts/fedora-dependencies.sh` to opt in to packages; it does NOT partition disks or create VMs.
- Create a normal-user Python virtual environment and install Nightglass as detailed in README.
- Run `nightglass doctor` and confirm `qemu:///system` libvirt authorization. Do not run Nightglass as root.
- Provision a separate Kali VM in virt-manager; initially no virtual NIC. Then review and optionally create `nightglass-lab` after deciding host firewall rules. Bind the VM in Nightglass.
- Only after VM guardrail testing consider an offline analysis VM. Never import real malware onto the personal host or into Distrobox.

### Stage D — harden and verify before daily use

- Verify no NIC or passthrough devices in analysis VM; ensure guest console doesn't expose clipboard channels.
- Verify lab network cannot access Internet and test/deny access to host bridge services separately. Never assume no `<forward>` alone means total isolation.
- Test from each VM as well as from Fedora host to confirm restrictions. Test startup denial using intentionally insecure **dummy** VM XML in a test environment.
- Keep regular external backups of VM disks/config, document restore procedure and test it.
