# Kali template version drift review (offline)

Nightglass can compare a previous **self-reported Kali package version lock**
to a newer **self-reported guest package inventory** for **the same, separately
installed Kali VM**. This makes it easier to spot accidental changes without
building one enormous security-tools guest or installing packages on the host.

The entire comparison reads **three small local JSON files only**. It does
not invoke `apt`, `dpkg`, `virsh`, `qemu-img`, a guest agent, a network
connection, or any Kali guest process.

## How to use

First generate and verify a separate setup plan for each Kali VM:

```bash
nightglass templates export recon /safe/private/recon-plan.json
nightglass templates verify /safe/private/recon-plan.json
```

After independently installing a **benign** Kali guest and obtaining
package metadata through an independently reviewed process (there is still
no built-in host/guest file transfer), save the first full inventory:

```bash
nightglass templates compare /safe/private/recon-plan.json /safe/private/first-inventory.json
nightglass templates lock /safe/private/recon-plan.json /safe/private/first-inventory.json /safe/private/first-lock.json
```

Only a **complete self-reported package set with a clean reported dpkg audit**
may be locked. Capture a newer inventory from the **same guest** later,
using the optional manual `scripts/kali/kali-guest-inventory.py` helper on the
guest and a separately approved transfer, then run:

```bash
nightglass templates drift /safe/private/recon-plan.json /safe/private/first-lock.json /safe/private/new-inventory.json
```

The optional `--report /safe/private/NEW-review.json` writes one new
private `0600` JSON report using exclusive-create; it refuses overwrites.

The GUI equivalent is **Prepare VM → Review package version drift**.
Select the plan, saved lock, then latest supplied inventory. Cancelling
does not trigger any read or guest action.

## What is compared

- Exact guest and template identity, template-catalog fingerprint, claimed
  installer ISO hash and Kali release.
- All selected tool package IDs, installed-version changes, packages no
  longer present, candidate versions missing from the latest inventory,
  and malformed/extra inventory entries.
- Whether the newer inventory explicitly reports a clean `dpkg --audit`.
  Unknown, failed or missing audit status is **not treated as unchanged**.
- The old private lock's fixed untrusted-source and
  `VERSION_SNAPSHOT_ONLY` labels; fields claiming verified repository
  signatures, dependency closure, or rollback are rejected if changed.

The CLI returns exit status **0** for `NO REPORTED DRIFT (UNVERIFIED)`,
**2** for drift or missing/unverified package state, and a nonzero status
for malformed, mismatched or inaccessible inputs.

Differences are labeled **VERSION CHANGE (DIRECTION UNKNOWN)**. Package
version syntax is not enough to safely decide upgrade versus downgrade:
Debian version comparison includes epochs and revision semantics.
A report **does not** execute upgrades, package removals or rollback.

## Trust, privacy and safety boundaries

- The baseline lock and newer inventory are **user-supplied untrusted JSON**.
  Neither is cryptographically signed or linked to the actual guest identity.
  A malicious or compromised guest can fabricate both inventories.
- SHA-256 fingerprints identify submitted JSON content, **not** publisher
  provenance, signed APT repositories or successful restore snapshots.
- V1 locks do not store historical APT candidate versions. The monitor
  cannot compare old-versus-new candidates or claim a complete dependency
  audit. Lock content can be edited along with its hashes; this is **not**
  a secure attestation system.
- A normal report with no observed drift is not proof that Kali is patched,
  secure, unchanged on disk, isolated, bootable or recoverable.
- The code never creates or starts a VM, runs Kali tools, attaches a
  shared host path, alters network access, writes to Windows/EFI/disk
  partitions, modifies an existing local file, or uses elevated privileges.

Next planned: real Fedora/KVM benign guest testing, full dependency
inventory and signed package provenance checks, plus per-VM cold
backup/restore validation. These gates are not bypassed by a green report.
