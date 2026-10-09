# Kali independent VM cold baseline audit (read-only)

Nightglass supports purpose-built, independently installed Kali VM templates
for authorized testing. Before installing or updating a tool bundle, an
operator should maintain a cold, checksum-verified backup of **that specific
VM**, not a shared image used by many profiles.

This phase adds an audit of an **existing Nightglass cold backup**, not a
new backup method and not a restore operation.

## Workflow

First, with the benign template VM manually installed and **fully shut off**,
use the existing Cold Backup workflow to create a fresh backup on separate,
encrypted storage. That operation copies files **only with explicit user
confirmation** and never changes the original guest. Verify the exported
folder first:

```bash
nightglass backup verify /path/to/existing-cold-backup
```

Then inspect the current template, expected live disk and that existing
backup directory:

```bash
nightglass templates baseline /path/to/recon-plan.json \
  --disk /absolute/path/to/recon.qcow2 \
  --backup /path/to/existing-cold-backup
```

Optional non-sensitive, private evidence **in a NEW file**:

```bash
nightglass templates baseline /path/to/recon-plan.json \
  --disk /absolute/path/to/recon.qcow2 \
  --backup /path/to/existing-cold-backup \
  --report /path/to/NEW-cold-baseline-evidence.json
```

GUI: **Prepare VM → Verify Kali cold backup**, select the curated profile
and guest, setup plan, expected qcow2 image and existing backup folder.
All checks run read-only.

## What is actually verified

- The **current registered Kali VM** passes the prior independent-disk,
  live/inactive XML, no-NIC, no-managed-save and shut-off checks.
- All cold backup assets are rehashed against the backup's local manifest.
  Incomplete, malformed, checksum-mismatched, or symlinked files are refused.
- The backup states the **same registered VM name** and restricted
  `lab` policy, has exactly one qcow2 disk, and the copied disk's declared
  original source matches the independently selected VM image path.
- The hashed archived XML matches the guest name, UUID, selected disk,
  VNC/host-device policy and absence of network adapters in the current
  and next-boot definitions.
- If the VM uses UEFI NVRAM, the backup contains the correctly identified,
  separately hashed NVRAM copy. An extra or missing NVRAM copy is refused.
- The copied image has a **distinct inode**, no extra filesystem hardlinks,
  an acceptable qcow2 header, no backing chain, no internal snapshots and
  the same declared virtual capacity as the registered disk.
- The guest is checked again to be shut off after the native metadata
  inspection. If the copy and VM share the same filesystem, the result
  warns that a single storage failure could destroy both.

`HASHES/DEFINITIONS MATCH (NOT RESTORE-PROVEN)` means precisely that:
a point-in-time check of files and declared configuration, **not proof of
a safe rollback**. The manifest can be forged together with its hashes and
is not a signature or publisher attestation. The live VM's disk contents may
have changed since the backup. The auditor does not read or hash live disk
contents, and never copies or restores any source.

## Required next safety gates

A real baseline isn't recovery-tested until a human independently stages
a **NEW, separate recovery copy**, verifies its QEMU/libvirt policy,
manually imports and boots a **benign** recovered guest under supervised
Fedora/KVM acceptance, checks the network and SELinux behavior, and verifies
the UEFI/NVRAM restore path. Never treat successful static hashes as
proof that a backup can boot or restore all data.

No guest agents, package installations, public networking, root or sudo,
automatic VM creation, host-mounted folders, data overwrites or Windows/
EFI/partition writes are added in this phase.
