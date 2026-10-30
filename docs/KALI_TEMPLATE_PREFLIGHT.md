# Kali template readiness preflight (read-only, local)

This Midnight Provisioner phase connects the small, **separate** white-hat and red-team
Kali VM templates to a meaningful host readiness check before any manual
Fedora/KVM installation. It does **not** create, clone, start or define a VM.

## Run the preflight

First download the official Kali installer ISO through your own trusted
workflow, independently obtain its official publisher SHA-256 and generate
a **new private** profile-specific plan:

```bash
midnight-provisioner templates export recon /home/user/private/NEW-recon-plan.json \
  --iso-sha256 OFFICIAL_KALI_ISO_SHA256
midnight-provisioner templates verify /home/user/private/NEW-recon-plan.json
```

Then run the combined read-only check on an **existing** host storage
directory where a *future* independent qcow2 disk would live:

```bash
midnight-provisioner templates preflight \
  /home/user/private/NEW-recon-plan.json \
  --iso /home/user/Downloads/kali-installer.iso \
  --storage-dir /home/user/VMs
```

The GUI equivalent is **Prepare VM → Kali toolkit → Check Kali VM
readiness**. Pick the selected template and unique VM name, specify the
ISO and its claimed official SHA-256, then select your saved plan and
an existing destination volume.

### Checked before reporting dry-run pass

- The saved manifest still matches the **current curated template and its
  safe defaults**. It must contain a publisher SHA-256 digest; absent
  digests block preflight.
- The current libvirt domain inventory is readable and does not already
  contain the proposed name. A new separate disk/name is needed for every
  template; existing VMs are never overwritten.
- All system-libvirt running/paused guests are counted against the
  hardware-aware concurrent VM cap (one on typical 8 GiB laptops).
- Linux **MemAvailable** leaves at least the proposed guest RAM plus
  **1.5 GiB** of breathing room; unavailable RAM/state blocks the check.
- The selected existing storage volume has free space of at least
  `max(4 GiB, min(12 GiB, suggested disk/4))`. This is a **short-term
  free-space heuristic**, not an allocation of disk space or a guarantee
  that a qcow2 file won't grow to its full configured virtual size.
- The selected installer file is at least 16 MiB, a regular local
  `.iso`, and its full SHA-256 is actually hashed against the saved
  digest claim. The hash does **not** independently authenticate the
  source of the expected digest.
- The real local `virt-install` tool is asked to render **both**
  installation and post-installation domain XML stages using
  `--dry-run --print-xml`. Each stage is checked for the expected
  identity, absent networking and Midnight Provisioner restricted-VM policy.
  No virt-install without `--dry-run` is invoked.

Missing or unsafe requirements report **BLOCKED / UNVERIFIED** with a
nonzero CLI exit code; only a complete read-only check reports **DRY-RUN
PASSED — MANUAL REVIEW ONLY**.

## Important boundaries

A passing preflight **does not** certify Fedora SELinux isolation, actual
network packet denial, installed Kali packages, VM boot, snapshots,
rollback, a clean/reproducible apt dependency tree, or future memory/disk
availability. Another privileged libvirt client may change VM inventory
or definitions after the check.

No software is installed, no guest is started/imported, no ISO downloaded,
no host/guest transfers enabled, and no Windows/EFI/partition changes
occur. Manual, supervised benign guest deployment and the project's
[host acceptance plan](FEDORA_ACCEPTANCE.md) are still required.

**Why this matters for template VMs:** a 32–72 GiB independent Kali VM
may begin as a small sparse qcow2 file but grow considerably when installing
its tools. The preflight deliberately shows a caution if free storage is
less than the guest disk's full possible expansion.
