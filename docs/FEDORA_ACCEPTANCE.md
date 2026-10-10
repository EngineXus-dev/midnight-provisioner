# Fedora/KVM recovery acceptance — read-only preflight and manual live drill

Nightglass's safety model must be evaluated on the **actual Fedora host** before
a recovered VM is registered. CI tests use simulated libvirt commands and do
not establish isolation or successful recovery.

## Phase start: safe Fedora host prerequisite audit (no VM required)

A separate non-root audit is now available for an actual Fedora test
installation. It does not require a staged backup or an existing guest:

    bash scripts/fedora-host-acceptance.sh

Optional NEW 0600 local status-only evidence (never uploads or overwrites):

    bash scripts/fedora-host-acceptance.sh --report "$HOME/nightglass-host-prerequisites-new.json"

It checks Fedora identity, ordinary-user privileges, SELinux enforcing
state, accessible KVM, native validation utilities and read-only
system-libvirt inventory availability. A successful prerequisite result
is NOT proof of real sVirt process/disk labels, guest packet isolation,
benign boot or cold rollback. **Actual Fedora hardware acceptance
remains PENDING.** Use the [full gate plan](FEDORA_HOST_PREFLIGHT.md);
do not run with sudo to suppress permissions failures.

## Automated *read-only* prerequisite

On a Fedora KDE test machine, install the Nightglass app and the reviewed
virtualization packages. Use a normal desktop user (not root), with legitimate
libvirt/polkit permissions. Copy an already checked, staged recovery folder
onto access-controlled encrypted storage, and run:

```bash
nightglass doctor
nightglass recover verify /path/to/recovered-new-guest
nightglass recover preflight /path/to/recovered-new-guest

# Or run the combined non-root, read-only script from the project root:
bash scripts/fedora-recovery-smoke.sh /path/to/recovered-new-guest
```

The last check uses installed **virt-xml-validate** and **qemu-img info** to
verify libvirt schema validity and disk metadata, as well as the already
implemented staged-file hashes and offline-device audit. It checks that
`/dev/kvm` is accessible, the new domain identifier is unused, and the
proposed RAM fits this machine's Nightglass profile. If the check fails,
nothing is imported or fixed automatically.

**Never substitute `virsh define --validate` for a read-only schema check.**
That command validates *and registers* a guest definition.

References:
- https://libvirt.org/manpages/virt-xml-validate.html
- https://libvirt.org/manpages/virsh.html
- https://www.qemu.org/docs/master/tools/qemu-img.html

## After *manual* registration — audit actual libvirt state

Once a human authorizes importing a **separate** guest on a disposable
test system, run:

```bash
nightglass accept new-recovered-vm --policy isolated
nightglass accept new-recovered-vm --policy isolated --report ~/guest-audit-new.json
```

Or select **Backup & verify → Audit registered VM**. The audit compares
current, next-boot, and any saved-state XML. Reports are written locally,
not uploaded. A passing XML result does NOT establish that a guest boots,
has no network reachability, or is safe for malware execution.

See [registered-guest acceptance details](REGISTERED_GUEST_AUDIT.md).

## Compare the actual manually registered guest against staged disks

After the separate manual, benign-guest registration and the read-only
registered XML audit, use:

```bash
nightglass recover handoff /path/to/recovered-new-guest
```

This checks all disk/NVRAM paths and QEMU formats in the registered domain
against the verified recovered files, including both live/current and
inactive/persistent definitions. It **does not import or boot** the VM.
See [recovery handoff policy](RECOVERY_HANDOFF.md).

## Separate supervised live acceptance (not automated by Nightglass)

| Check | Expected observation |
|---|---|
| Host distro, virtualization support, polkit | Fedora KDE and working non-root `qemu:///system` access |
| Preflight on 8 GiB device | One VM at a time, guest memory within conservative host limit |
| Check recovered image, XML and UEFI metadata | Integrity matches; actual firmware and paths reviewed |
| Guest identity | New guest name/UUID, original VM remains unchanged |
| Guest interface state | No virtual NIC in staged XML **and** actual defined domain |
| Host integration | No shared folders, virtiofs, USB passthrough, guest channels or SPICE clipboard |
| Controlled boot | Only after a manual authorization/isolated test plan, benign fixture guest boots |
| Shut down and recovery | VM shuts down cleanly, independent original backup remains unchanged |
| Portability | Recheck RAM/CPU and firmware assumptions on a second machine |
| Negative cases | Changed image hash, malicious disk path, network interface and name collision all fail |

Before any manual registration of a staged guest, review the **exact**
`domain.xml`, the proposed storage location, ownership/permissions, SELinux
file contexts and guest firmware loader. Only register a **NEW** domain on a
**disposable test host**. Never import a sample VM or suspicious images into a
personal-use desktop without a dedicated risk assessment. Do not use live
malware during development smoke tests.

After supervised registration, repeat a read-only libvirt domain audit,
including the *actual* runtime device and networking configuration. A
successful preflight cannot prove guest reachability is blocked or that the
guest will successfully boot; these must be separately observed and recorded.
Any subsequent automatic import/rollback workflow must remain disabled until
that evidence exists.

## Evidence to record locally

For each host test, note Fedora version, kernel/libvirt/QEMU versions, host RAM,
KVM availability, package versions, schema validation result, image format,
guest memory budget, external firmware/NVRAM dependencies, real guest device
inventory, network test outcome, first boot status and cleanup result.
Retain diagnostic output locally. Do not publish guest disk images, host
credentials or personal system identifiers to GitHub.
