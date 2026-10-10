# Kali offline guest package inventory helper (manual use, read-only)

Nightglass now includes a **standalone Python 3 helper** at
`scripts/kali/kali-guest-inventory.py` in the source checkout. It reduces manual
copying of package versions by using read-only, locally installed
`dpkg-query`, `apt-cache policy`, and `dpkg --audit` commands **inside
an already-installed, benign Kali test guest**.

It does **not** install, update or download packages, start or clone VMs,
enable a network, use root privileges, invoke a guest agent or change the
host. It has no PySide6/third-party Python dependencies.

## 1. Make a host-side plan

On the Nightglass host:

```bash
nightglass templates list
nightglass templates export recon /path/to/NEW-recon-plan.json
nightglass templates verify /path/to/NEW-recon-plan.json
nightglass templates guest-help recon
```

The last command (also shown by **Prepare VM → Guest inventory instructions**)
prints the specific offline steps. If a plan changes, the host-side
`templates verify` command refuses it rather than silently updating it.

## 2. Collect inside one manually installed benign Kali VM

Nightglass **does not implement a host/guest file-transfer mechanism**,
and does **not** copy scripts or invoke commands inside Kali.
Only after a separately reviewed, safe, user-controlled transfer of the
verified setup plan and the standalone helper into the intended Kali VM,
as an ordinary Kali user (never root), run:

```bash
python3 kali-guest-inventory.py \
  --plan NEW-recon-plan.json \
  --output NEW-recon-inventory.json
```

The helper verifies that the guest reports `ID=kali` in `/etc/os-release`,
refuses dangerous/wide template packages, uses fixed command argument
vectors and a non-networking `apt-cache` query (it never runs `apt update`),
and reads only the packages in that plan, not all installed software.

The report is private `0600` JSON created with exclusive-create. Existing
files, including symlinks, are refused. Collection stops with a nonzero
exit if the selected package state cannot be determined reliably.

**Do not circumvent** Nightglass's no-host-share, no-clipboard, no-USB,
and no-unapproved-network policies to move files. If you have not separately
established a reviewed transfer path for a benign guest, stop after creating
the host-side plan and defer these guest steps until a safe broker exists.

## 3. Compare the self-reported metadata on the host

Only when the guest output has been transferred back through an approved
manual process (outside Nightglass):

```bash
nightglass templates compare \
  /path/to/NEW-recon-plan.json /path/to/NEW-recon-inventory.json
```

A missing package receives `installed_version: null`; an absent cached
candidate becomes `candidate_version: null`. If `dpkg --audit` produces
problems, `dpkg_audit_clean` is false. All values come from the guest's
own report, so a compromised guest **could lie**. The guest-reported Kali
release and package versions are not authenticated and are **not**
signed-package verification, dependency-closure verification, a clean
restore certificate or proof of effective guest isolation. Candidate
versions may be stale if apt caches have not been refreshed, and the helper
does not refresh them.

The existing `templates lock` command can record a private version
snapshot only after a complete self-reported inventory with clean
`dpkg --audit`; its provenance/rollback fields remain explicitly false.

## Security gates before more automation

- Add a quarantined, auditable host↔guest transfer broker; never add a host
  shared folder or clipboard channel to restricted malware guests.
- Independently verify Kali repository signatures and the exact
  package/dependency versions in a benign Fedora/KVM VM.
- Prove tested rollback of each **independent** VM disk and UEFI NVRAM.
- Supervise packet-level network denial and real Fedora SELinux runtime
  behavior before calling any profile ready for untrusted workloads.
- Only after those checks could any explicit guest-scoped package installer
  be considered. The current helper is **not** one.

The helper is intended for **source checkouts**; a standalone binary
distribution must explicitly package and audit it before advertising this
workflow.
