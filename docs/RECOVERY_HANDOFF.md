# Verified recovery handoff — read-only registered guest comparison

Midnight Provisioner distinguishes three independent stages:

1. **Stage** verified offline backup assets into a **NEW** folder.
2. **Preflight** the unregistered staging against native QEMU, libvirt XML
   schema, guest limits and unused domain name.
3. **After manual import on a disposable Fedora host**, **Handoff** checks
   that the registered guest still points exclusively at the staged, verified
   disk/NVRAM images and has not acquired an unsafe network or driver change.

Steps 1 and 2 do not import or boot. Step 3 is **read-only**. There is still
no automatic VM import or start by Midnight Provisioner.

## Usage

From the project root with a separate, already-staged recovery folder:

```bash
midnight-provisioner recover verify /path/to/staged-new-guest
midnight-provisioner recover preflight /path/to/staged-new-guest

# After an independently authorized MANUAL new-guest registration:
midnight-provisioner recover handoff /path/to/staged-new-guest

# Optional private, NEW report file (never overwrites):
midnight-provisioner recover handoff /path/to/staged-new-guest \
    --report /path/to/new-handoff-report.json
```

On the GUI, use **Backup & verify → Verify registered handoff**, select
the staged folder and optionally **Save local audit report**.

A successful handoff requires the registered guest to be powered off,
no managed-save session, and compatible policy across current and inactive
XML. Its identity UUID must be present and consistent. Every VM disk must
point to a verified staged image with the correct declared QEMU driver type
(`qcow2` or `raw`) and no additional disk/ISO; associated UEFI NVRAM
must also point to the staged copy.

For each known staged disk, `qemu-img info --output=json` is checked
read-only against the XML driver and filename format. An unknown/extra
registered disk is **never opened** by Midnight Provisioner. Any backing chain,
unexpected snapshot/encryption marker, hash mismatch, symlink, or changed
registered XML blocks approval. The recovered guest's new UUID is assigned
by libvirt during intentional manual registration, not by Midnight Provisioner.

## What approval does **not** mean

- File hashes only prove the staged manifest/files are consistent; they
  do not establish publisher authenticity or absence of malicious contents.
- Static libvirt XML, QEMU headers, and local file paths do **not** prove
  SELinux confinement, actual QEMU permissions, host firewall rules or
  packet-level guest network isolation.
- Other privileged users/processes may change XML or disk content immediately
  after a check (a point-in-time/TOCTOU limitation).
- No guest is booted, shut down, registered, reconfigured or modified.
- Original backups/VMs, Windows partitions/EFI and user files are not touched.
- On 8 GiB machines, use only a benign recovery fixture for supervised tests;
  malware execution must not occur as part of routine developer acceptance.

Continue following the [Fedora hardware acceptance plan](FEDORA_ACCEPTANCE.md)
for physical-host boot/network checks before enabling automatic imports.
