# Registered Kali recovery handoff (read-only)

The final **pre-boot** Nightglass audit for an independently recovered
Kali template checks that a **manually registered, still shut-off** guest
matches its source template, verified cold backup and independent offline
recovery copy.

This feature does **not** import or boot any guest; successful results are
**configuration metadata only**, not successful rollback or a security
certification.

## Recommended sequence

After deliberately preparing a benign Kali VM and shutting it down,
make a cold backup on independent, preferably encrypted storage:

```bash
nightglass templates baseline /path/to/original-kali-plan.json \
  --disk /absolute/original-guest.qcow2 \
  --backup /path/to/cold-backup
```

Using the existing confirmation-gated recovery staging workflow, create
a **new guest name** and **new empty destination folder**. Verify that
copy is independently linked to the source:

```bash
nightglass templates recovery-link /path/to/original-kali-plan.json \
  --backup /path/to/cold-backup \
  --staged /path/to/new-offline-recovery-stage
```

After separately reviewing the **benign** staged XML and independently
and manually registering this **new**, **powered-off** guest with
virt-manager/libvirt, run:

```bash
nightglass templates recovery-registered /path/to/original-kali-plan.json \
  --backup /path/to/cold-backup \
  --staged /path/to/new-offline-recovery-stage
```

The GUI equivalent is **Prepare VM → Audit registered Kali recovery**.
Select the **original** curated toolkit and guest, the original plan,
original backup and independent staged recovery. The GUI does not
perform libvirt registration.

Optionally write a **NEW**, private local report (never overwrite):

```bash
nightglass templates recovery-registered /path/to/original-kali-plan.json \
  --backup /path/to/cold-backup \
  --staged /path/to/new-offline-recovery-stage \
  --report /path/to/NEW-registration-audit.json
```

## Additional checks

- **Backup-to-stage binding:** recheck source and staged hashes, copied
  qcow2/NVRAM integrity, template guest identity, restricted no-network
  policy and deterministic offline recovery XML.
- **Registered recovery handoff:** existing audit of current/persistent
  libvirt XML, guest shut-off state, managed-save status, restricted
  devices, declared disk paths and read-only QEMU image metadata.
- **Identity renewal:** inspect the backup's original guest UUID and both
  registered recovery definitions. Refuse a missing or reused original UUID,
  inconsistent recovered UUIDs or the wrong recovered guest identity.
- **Autostart safety:** read the registered recovered VM's
  `virsh dominfo`; autostart must be explicitly **disabled**. Enabled,
  missing, unknown or inconsistently reported status blocks the audit.
  This matters because an external libvirt client/host reboot can start
  a guest **without** using Nightglass's guarded Start command.
- **Disk independence:** read current/next-boot/managed-save XML of every
  other registered system-libvirt guest. Refuse exact or lexically aliased
  recovery image paths and same-directory symlink sources without opening
  unrelated VM disk files. Inaccessible definitions block the audit.
- **Final recheck:** verify staged asset hashes again and recheck the
  recovered guest is shut off with autostart still disabled.

The report says **PASS (METADATA ONLY — NOT BOOT/RESTORE-PROVEN)** only
when all of those checks pass. All provided records remain susceptible
to privileged changes and are not a security attestation.

## Boundaries

This phase does not actually measure guest-to-host or guest-to-Internet
packet denial; host SELinux/sVirt enforcement; guest OS bootability;
data equivalence after a real restore; signed Kali package provenance;
or disk aliasing through unregistered hypervisors, bind mounts, foreign
symlinks outside the selected storage directory or storage snapshots.
Static audits cannot close every time-of-check/time-of-use race.

**Never boot a suspicious or untrusted guest merely because the static
report passes.** Only a supervised, benign Fedora/KVM rehearsal can
provide physical runtime evidence. These safeguards do not make privileged
host-side automatic import, start, software installation or rollback safe
by themselves.
