# Cold VM backups, integrity checks and recovery

Midnight Provisioner supports **cold, offline backup copies** of the existing Kali/lab
and offline analysis VMs. It does **not** provide virtual machine snapshots,
one-click rollback, or a proven automated restoration system.

A cold backup is safer than copying a running QCOW2 image, but it is **not**
a substitute for testing restoration on a separate machine. Only start when
the guest is fully **shut off** and no managed-save memory session exists.

## Create a backup (GUI)

1. In Midnight Provisioner, find the Kali or analysis VM and choose **Cold backup**.
2. Select a directory on independent, preferably encrypted external storage.
3. Enter a **new folder name**; Midnight Provisioner refuses any existing destination.
4. Midnight Provisioner checks the guest's power state, managed-save status, current
   and inactive libvirt XML, security policy, ISO/CD-ROM detach state,
   backing chains, source files and declared disk format.
5. Inspect the previewed file paths and byte count. Confirm explicitly.
6. The application creates a new private directory and copies the guest's
   file-backed QCOW2/RAW images, UEFI NVRAM if applicable, and a copy of
   the inactive guest XML. Each file receives a SHA-256 checksum recorded
   in \`manifest.json\`.
7. Choose **Backup & verify → Verify saved backup** and select the new
   backup folder. Recalculate and compare every file hash.

A new directory contains:
- \`manifest.json\`: file names, sizes, SHA-256, source locations, guest ID.
- \`domain.xml\`: original libvirt XML with original host-specific paths.
- \`disks/disk-01.qcow2\` (or \`.raw\`): detached copy of local guest disk.
- \`firmware/nvram.bin\` when a separate NVRAM file exists.
- \`INCOMPLETE\` is present throughout copying and remains after failure.

## CLI

\`\`\`bash
midnight-provisioner backup plan pentest
midnight-provisioner backup create pentest /media/secure-drive/midnight-provisioner-pentest-001
midnight-provisioner backup verify /media/secure-drive/midnight-provisioner-pentest-001
\`\`\`

\`backup create\` requires typing **BACKUP** interactively (or passing the
explicit \`--yes\` flag in a pre-approved automation). **Nothing is ever
overwritten or deleted automatically.** Backups require non-root access to
disk-image files and sufficient free space. If libvirt VM storage is owned by
root or QEMU, Midnight Provisioner refuses and suggests a separate permission-reviewed
procedure; do **not** run the GUI as root or loosen storage permissions blindly.

## New: verified offline recovery staging

Use **Backup & verify → Recover into NEW folder**, or
`midnight-provisioner recover plan|stage|verify`, to prepare a **separate offline copy**
with a fresh guest identity and rewritten disk/NVRAM paths. Nothing is
automatically defined in libvirt and no guest is started. Follow the
[recovery staging guide](RECOVERY_STAGING.md) before a manual import.

## Recovery: deliberately manual

Restoring a guest may require reconstructing the original storage permissions
and SELinux contexts, libvirt firmware/NVRAM setup, interface and firewall
policies, machine type and virtual storage drivers. A verified file hash
cannot prove the disk boots or that backup files are malware-free.

**Never overwrite a working VM with backup files.** On a test machine, make a
fresh, isolated VM, place the copied image files in a new dedicated protected
directory, carefully review and adapt \`domain.xml\`, restore NVRAM when
appropriate, and verify boot and network policy. Only after this has been
tested should you rely on this backup.

## Safeguards and limitations

- Linux-only; no Windows or EFI modifications.
- No guest-side shared folders, no backup to cloud providers.
- No snapshot commits, merging chains, conversion, flattening or image deletion.
- Blocks running, paused and managed-saved VMs. Refuses remote/block/volume
  storage, active installation ISO attachments and QCOW2 backing chains.
- Rejects symlinks for source images and backup files.
- An external administrator or automation could start a guest or mutate a disk
  during copying. Midnight Provisioner rechecks VM power state during chunks, but cannot
  atomically lock out other privileged libvirt clients. For strong consistency,
  use an independent cold clone and hardware-tested backup workflow.
- Your backup may contain personal information, credentials or malware samples.
  Store it on an encrypted volume under appropriate permissions, never directly
  in GitHub or a cloud-sync directory.
- The manifest contains hashes, **not a cryptographic signature**. A malicious
  actor who can modify all backup files and the manifest can forge matching
  checksums.
- \`INCOMPLETE\` folders are kept for inspection; Midnight Provisioner will not delete
  them for you. Do not restore their contents.
- The current implementation is **experimental pending live Fedora/libvirt
  integration tests**. A successful unit test or SHA-256 check does not prove
  real-world recovery or isolation.
