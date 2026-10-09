# Observing a manually running Kali recovery VM (read-only)

Nightglass's white-hat and authorized red-team Kali templates use separate
VMs, separate disks, no default network adapters, and an independently
verified pre-boot cold-backup/recovery chain.

This phase adds a **supervised, metadata-only runtime check** that runs
**only after a human has manually started a BENIGN recovery VM**. Nightglass
does **not** start, import, pause, resume, install, or interact with a guest.

## Sequence

Before startup, run the previous strict offline handoff:

```bash
nightglass templates recovery-registered /path/original-plan.json \
  --backup /path/existing-cold-backup \
  --staged /path/new-independent-recovery
```

That command must be reviewed as **METADATA ONLY**, not a boot permission
for unknown or malicious images. After an operator independently authorizes
a **benign** Kali test guest and manually starts the **NEW** recovered guest
under supervised Fedora/KVM, observe its current settings:

```bash
nightglass templates observe-running /path/original-plan.json \
  --backup /path/existing-cold-backup \
  --guest nightglass-kali-recon-rehearsal \
  --disk /absolute/path/to/selected-live-recovery.qcow2
```

Optional private non-attestation record, **NEW file only**:

```bash
nightglass templates observe-running /path/original-plan.json \
  --backup /path/existing-cold-backup \
  --guest nightglass-kali-recon-rehearsal \
  --disk /absolute/path/to/selected-live-recovery.qcow2 \
  --report /path/to/NEW-runtime-observation.json
```

The GUI provides **Prepare VM → Observe running Kali recovery**. Select
the original curated Kali setup plan, existing cold backup, enter the
**different recovery guest name** manually, and select the expected live
qcow2 disk. This never invokes VM start.

## What is checked

- The source Kali plan remains an unchanged, curated planned-only profile.
  The **inactive cold backup**, including the source guest UUID and lab
  policy, is hash-verified before and after metadata inspection.
- The selected recovered VM is **already running** according to libvirt.
  It has a different identity and UUID than the original backup. Its
  current/next-boot definitions consistently use the selected disk.
- Registered runtime sVirt XML labels are internally consistent; libvirt
  advertises SELinux security support and the host reports **enforcing**
  mode. This reuses the project's existing restricted-guest runtime
  SELinux metadata check.
- Neither current nor next-boot XML declares an unexpected NIC, host
  passthrough device, mounted installer, backing chain, extra disk,
  wrong QEMU disk format or an unwanted managed-save session.
- System-libvirt autostart remains explicitly **disabled** and no other
  registered guest declares an obvious lexical or same-directory disk
  alias. Missing/unknown metadata fails closed.
- The selected live qcow2 file is verified to be a regular, non-symlinked
  single-link file and its **device/inode identity** is rechecked. This
  does not resolve bind mounts or all foreign symlink aliases.
- Guest state and autostart are rechecked after the metadata inspection.
  Another privileged process can still change them afterward.

## Deliberate omissions

**The active qcow2 image is never hashed, frozen, copied, or queried through
`qemu-img`.** A VM might be writing to its image, so even a matching
pre-boot staged checksum must not be expected to remain valid after
startup. The inactive original backup is the only archive that is rehashed.

A result of **PASS (LIBVIRT/SELINUX METADATA ONLY)** does **NOT**
establish that the Kali operating system completed boot, that a backup
was restored successfully, or that SELinux actually confined the QEMU
process. No QEMU process `/proc` context was inspected, no actual disk inode
SELinux context was measured, no firewall/guest packet-denial experiment
was executed, and no guest tools or network services were contacted.

Manual, supervised **Fedora/KVM hardware acceptance** remains essential.
Never boot an untrusted sample based solely on these static/runtime
metadata findings. The report contains no host disk paths, QEMU SELinux
category IDs, passwords or guest network data.
