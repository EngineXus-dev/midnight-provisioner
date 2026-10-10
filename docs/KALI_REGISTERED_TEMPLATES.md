# Audit a manually registered Kali template VM (read-only)

Nightglass's Kali toolkit catalog is designed around **separate virtual
machines** for each legitimate testing role—not a fragile, high-maintenance
Kali installation containing every available security tool.

This phase verifies whether an **already manually installed**, **shut-off**
Kali VM still resembles its saved curated plan and points at its own
user-selected independent virtual disk.

## Usage

First follow the [offline installer/host preflight](KALI_TEMPLATE_PREFLIGHT.md)
for a distinct Kali template and name. Under supervision, manually install
a benign Kali guest with virt-manager. Keep networking disconnected and
perform an ordinary power-off afterward. Nightglass does **not** install,
start, clone or register that VM for you.

On the Fedora host, use:

```bash
nightglass templates registered /path/to/recon-plan.json \
  --disk /path/to/nightglass-kali-recon.qcow2
```

Optional local evidence with a **NEW** private file (never overwrite):

```bash
nightglass templates registered /path/to/recon-plan.json \
  --disk /path/to/nightglass-kali-recon.qcow2 \
  --report /path/to/new-registration-report.json
```

The GUI offers **Prepare VM → Audit installed Kali template VM**. Select
the same Kali profile/guest, the saved plan JSON and its exact qcow2 image.

## What is checked

- A plan that still exactly matches the maintained, narrowly curated Kali
  template, with unchanged offline-only settings and guest identity.
- The named VM exists in system libvirt, is **shut off**, and has no
  managed-save resume image. Existing policy checks audit its *current* and
  *next-boot* XML for forbidden host channels and networking.
- Neither VM definition declares **any network interface**, even though the
  generic lab policy would allow a separately reviewed isolated lab network.
  This check is for a pristine offline template, not later live testing.
- Current and persistent definitions agree on the guest UUID, use exactly
  **one** explicit qcow2 image source at the chosen absolute path, and have
  no mounted installer media, unexpected disk or backingStore XML.
- Guest RAM and vCPU declarations remain within the current host resource
  budget; missing values fail closed.
- **All other system-libvirt VMs** are read through current/inactive and
  saved XML. If one reports the same source path **including a lexical
  `..` / `.` alias**, the independent-disk check blocks. A symlinked
  source within the **selected disk's trusted parent directory** also
  blocks; unknown/unreadable XML blocks instead of declaring safety.
- The selected disk's kernel inode metadata must report **exactly one
  hardlink** (`st_nlink == 1`), rejecting second hardlinks even if their
  names are in another folder or aren't referenced by a registered VM.
  This is checked again after native QEMU metadata inspection along with
  the original device/inode identifier.
- The expected local disk is a nonempty regular `.qcow2` file with no
  symlink path component. Only that user-selected path is passed to a
  **read-only** `qemu-img info --output=json` check. External/unknown disk
  paths from other VMs are **never opened**.
- The reported qcow2 virtual capacity is within conservative size bounds
  and its metadata contains no unexpected backing chain, snapshots or
  encrypted state.

## Critical limitations

**PASS (CONFIGURATION ONLY)** means the *declared configuration* matches
the selected template at the time of inspection. It does **not** prove:

- That any Kali tools were installed, version-locked, audited or sourced
  from authentic signed repositories.
- That the VM has successfully booted, passes firewall packet-denial tests
  or is actually confined by SELinux/sVirt.
- That a differently named path **outside the selected disk folder**
  isn't a symlink to the selected image; such paths are **not resolved or
  opened** because other guests' XML is not a trusted host-file access
  authority. Filesystem hardlinks are blocked by the selected disk's
  `st_nlink` count, including aliases outside that folder, but bind mounts,
  volume snapshots, unregistered VMs, other hypervisors and future races
  remain outside this point-in-time review.
- That another privileged client won't change the XML or disk immediately
  after the read-only check, or that storage/cold rollback is complete.

There are **no guest writes**, tool installations, password/host directory
mounts, implicit network connections, automatic VM starts, guest cloning,
disk provisioning, EFI changes or Windows modifications in this phase.
Current guest backup and recovery safety gates are unchanged.

Before deploying a new Kali template in a real environment, validate the
guest with supervised Fedora/KVM hardware acceptance, signed package
provenance and an individually tested cold backup/restore procedure.
