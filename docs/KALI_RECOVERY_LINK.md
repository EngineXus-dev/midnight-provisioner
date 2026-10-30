# Kali template cold-backup → offline recovery copy binding

This is the next read-only stage of Midnight Provisioner's **separate Kali template
VM** workflow. It checks that an existing, independently staged recovery
folder really originated from the expected Kali template cold backup.

This is **not** a VM restoration. It does not copy a disk, generate a
guest, register a libvirt domain, start a VM or verify a boot.

## Sequence

First maintain a benign, manually installed Kali VM in its own disk.
Manually shut it down and create a **cold backup** using Midnight Provisioner's
existing confirmation-gated backup command or GUI, preferably on separate,
encrypted storage.

Check the backup:

```bash
midnight-provisioner backup verify /path/to/existing-cold-backup
midnight-provisioner templates baseline /path/to/original-kali-plan.json \
  --disk /path/to/original-kali.qcow2 \
  --backup /path/to/existing-cold-backup
```

Using the existing **recovery staging** workflow, explicitly request a
newly named guest, in a completely **new** folder. Recovery staging is a
separate file-copy operation requiring explicit confirmation and is
not triggered by this command.

For an *already-created* staging directory, run:

```bash
midnight-provisioner templates recovery-link /path/to/original-kali-plan.json \
  --backup /path/to/existing-cold-backup \
  --staged /path/to/NEW-offline-staging
```

Optionally write one NEW non-sensitive private report:

```bash
midnight-provisioner templates recovery-link /path/to/original-kali-plan.json \
  --backup /path/to/existing-cold-backup \
  --staged /path/to/NEW-offline-staging \
  --report /path/to/NEW-recovery-link-evidence.json
```

GUI: **Prepare VM → Verify Kali recovery copy**. Select the same Kali
template and original guest name, original setup plan, existing backup and
already-staged recovery folder.

## Verified

- The original plan remains an unchanged, curated **PLANNED_ONLY** Kali
  template and the cold backup manifest describes that exact original
  guest under the restricted `lab` policy.
- `verify_backup` and `verify_staging` rehash every manifest-listed
  asset. Incomplete, tampered or symlinked assets fail.
- The recovery manifest states the exact source guest and policy, a
  different new guest identity and **offline/no-network** status.
- Exactly one qcow2 disk, plus optional separate UEFI NVRAM, is copied.
  The original and staged copies must match in kind, size and SHA-256.
- Backup and staged folders cannot be the same or nested. Asset files
  must be regular, single-link files with **different device/inode IDs**
  so a hardlink cannot masquerade as an independent recovery copy.
- The staged XML must match the deterministic, conservative offline
  recovery transformation of the **verified original backup XML**.
  Changed RAM/firmware, extra devices, network interfaces, UUID retention
  and unexpected storage references must not be silently accepted just
  because someone recalculated the staging manifest's hashes.
- Backup/staging file integrity and inode identity are rechecked at the
  end. This reduces, but cannot eliminate, time-of-check/time-of-use races.

The result is **MATCHED (FILES/XML ONLY — NOT RESTORE-PROVEN)**, never
“restored” or “safe to execute.”

## Read-only check after manual registration

After separately inspecting and **manually registering** a new, shut-off
benign recovery VM, run `midnight-provisioner templates recovery-registered PLAN.json
--backup EXISTING_BACKUP --staged EXISTING_STAGE`. The GUI offers
**Audit registered Kali recovery**. This revalidates the backup and copy
against the actual system-libvirt recovery guest, requiring a new VM UUID,
autostart OFF, no NIC/saved resume and no other registered guest using the
recovery disk. It still does **not** boot or restore the VM. See
[registered Kali recovery audit](KALI_REGISTERED_RECOVERY.md).

## Limits and next steps

SHA-256 matching does not prove that the original backup was created by
a trustworthy operator or that Kali packages were authentic. It also
does not establish the guest boot works, effective SELinux/sVirt,
packet-level isolation or successful rollback. Separate storage devices
and encrypted backups remain strongly advised.

This phase performs **no** `virsh define`, `virsh start`, guest agent,
external network access, automatic VM clone/creation, disk copy, package
installation or guest repair. It does not change Windows/EFI or another
VM's files.

A supervised, **benign** Fedora/KVM recovery rehearsal remains necessary:
run the existing recovery import preflight, independently approve manual
registration, then use the read-only recovery handoff check to compare
the registered guest to staged files. Any boot and network/SELinux test
must be separately authorized and documented.
