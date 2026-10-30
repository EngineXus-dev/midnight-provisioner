# Fedora host-acceptance phase — safe prerequisite gate

**Status:** IMPLEMENTED, NOT EXECUTED ON REAL FEDORA HARDWARE.

Fedora 43 container testing already passed on Windows Docker Desktop:
381 full-suite tests (23 opt-in GUI skips), the 23 GUI tests in a
separate real Qt pass, and six native QEMU/libvirt fixture tests.
None of this verifies a physical Fedora KDE host, actual guest
isolation or a successful VM recovery.

## Phase A: non-root, read-only host prerequisites

On a separate, properly configured **Fedora KDE test installation**,
from a clean Midnight Provisioner source checkout **on the Fedora machine**:

    bash scripts/install/fedora-host-acceptance.sh

This command uses Python standard-library plus the existing Midnight Provisioner
host-posture module. It does not require PySide6, download packages,
contact GitHub, use sudo, open a guest or modify libvirt.

It checks, fail-closed:

- Actual Linux OS release identifies as Fedora
- Ordinary unprivileged user, not root
- SELinux enforcing, using existing host-posture observations
- Read/write access to character device /dev/kvm as that user
- Installed virsh, virt-xml-validate and qemu-img binaries
- A real non-root read-only system-libvirt inventory query

The output can say **HOST PREREQUISITES: MET**; it will **always say
HARDWARE SECURITY ACCEPTANCE: PENDING** until independent supervised
host and guest evidence is collected. Fedora KDE itself, package
signatures, kernel/QEMU image labeling and guest behavior remain
separate acceptance requirements.

To explicitly create **a NEW 0600 JSON evidence file** in an existing
directory:

    bash scripts/install/fedora-host-acceptance.sh --report "$HOME/midnight-provisioner-host-prerequisites-new.json"

Never run this example twice with the same filename. It uses exclusive
creation and will refuse an existing destination or a direct symlink;
it does not automatically create folders, erase files, or upload
results. Reports contain static gate statuses and a sanitized Fedora
release number only—not domain names, usernames, hostnames, IPs, PIDs,
paths, process labels or guest disk identities. Keep reports local.

Exit codes: **0** prerequisites met (NOT release certification);
**1** at least one prerequisite blocked; **2** a requested evidence
write failed safely or the shell launcher is unavailable/inappropriate.

## Phase B: manually supervised physical host checks (NOT automated)

Proceed on a **disposable, separately backed-up Fedora test host**;
do not run suspicious samples or untrusted guest disk images as fixtures.

1. Review actual Fedora KDE install state, kernel/libvirt/QEMU versions,
   source provenance, SELinux enforcing, Secure Boot/firmware assumptions
   and legitimate user permissions. Record sensitive evidence only
   locally. Do not change security settings to make a check green.
2. Independently inspect a **harmless** newly prepared guest's
   XML and storage: current/inactive/saved domain definitions, no
   unintended NIC, no host files/devices/clipboard/shared folders, safe
   independent disk path, isolated NVRAM and correct immutable baseline.
3. On the supervised host, confirm actual sVirt enforcement:
   active QEMU process context, effective SELinux labels, disk inode
   contexts and MCS separation. Compare with libvirt runtime XML.
   A metadata-only PASS is **not** equivalent to effective isolation.
4. Verify actual bridge/firewall policy and guest network reachability,
   using only authorized controlled network endpoints. No internet
   scanning, unspecified external addresses, or shared home networks.
   An offline analysis guest must have no NIC; a lab NIC must use a
   properly isolated, no-forward test network and peer/host filtering
   must be independently checked.
5. After explicit human approval, perform a **benign** VM boot on the
   test host, shut it down and independently cold-restore its verified
   backup to a separate name/disk/identity. Prove the original guest
   and baseline remain intact; record a rollback/cleanup result.
6. Test denial cases: wrong hash, changed NIC XML, VM-name collisions,
   inaccessible /dev/kvm or SELinux not enforcing must not receive
   trusted approval. The separate headless Python 3.11–3.13
   compatibility matrix PASSED in Linux Docker containers on 2026-10-09;
   this does not replace real Fedora host validation.

Never run virsh define --validate as a supposedly read-only check:
it registers a domain. The safe Midnight Provisioner XML validator is
virt-xml-validate.

## Explicit hold points

- Do not manually import or boot real malware-analysis images during
  this acceptance stage.
- Do not automatically create/start guests, enable host/guest clipboard,
  mount other users' disks, weaken SELinux, switch on network routing,
  or elevate with sudo to get a PASS.
- Do not push user workstation logs or process/disk identifiers into
  the public/private GitHub PR unless they have been reviewed and
  minimized.
- Do not merge any of the stacked draft PRs merely because the Docker
  test suite passed. Physical acceptance, dependency review, and
  explicit owner approval remain mandatory.

Related: [full Fedora acceptance checklist](FEDORA_ACCEPTANCE.md),
[effective QEMU sVirt observation](KALI_QEMU_PROCESS_LABEL.md), and
[verified container run](FEDORA_DOCKER_VERIFICATION.md).
