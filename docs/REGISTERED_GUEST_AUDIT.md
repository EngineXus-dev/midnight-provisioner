# Read-only audit of a registered Fedora/KVM guest

Midnight Provisioner can inspect an **existing, registered** libvirt virtual machine without
starting, stopping, defining, snapshotting or modifying it. This complements
the **recover preflight** command, which checks a *staged* guest before it has
been imported.

## Commands

Run on Fedora KDE as your usual desktop user:

```bash
# Check an actual libvirt VM against the strict offline analysis policy:
midnight-provisioner accept new-recovered-vm --policy isolated

# Kali lab VMs may use only the separately reviewed midnight-provisioner-lab network:
midnight-provisioner accept midnight-provisioner-kali --policy lab

# Save local, private evidence to a file that does NOT already exist:
midnight-provisioner accept new-recovered-vm --policy isolated --report ~/vm-audit-01.json
```

Or use **Midnight Provisioner → Backup & verify → Audit registered VM**. The companion
**Save local audit report** button writes JSON in a new location, with user-only
file permissions. Nothing is uploaded to GitHub or any cloud service.

The auditor reads from `qemu:///system` and compares the **current
definition** (usually the live XML for running guests), the **inactive
definition** (the next-boot configuration), and any **managed-save XML**. All
present definitions must pass the selected policy. An offline profile must
have **no guest NICs**, host filesystem pass-through, unsafe guest channels,
SPICE sharing or unapproved devices. For lab networking, Midnight Provisioner also
checks the `midnight-provisioner-lab` libvirt network configuration, including absence
of forwarding.

The report stores the domain name, policy, state, checked definition classes,
declared memory and interface count, plus errors/warnings. It intentionally
does **not** include full guest XML, host filesystem paths, VM disk contents
or credentials. Do not treat it as anonymous: even VM names can disclose
sensitive information.

## How the results should be interpreted

- **PASS (XML ONLY)** means the inspected declarations fit Midnight Provisioner's
  conservative policy. It is **not** a runtime isolation certification.
- **BLOCKED** identifies deviations that require manual investigation.
  Midnight Provisioner will not auto-repair the guest to make an audit pass.
- **Powered-off VM:** there is no running guest traffic to observe.
- **Running VM:** Midnight Provisioner checks XML but cannot establish whether its
  network traffic or host-facing services are truly blocked.
- **Lab network:** even a libvirt network without forwarding may still expose
  host bridge services. Routing and firewall policy must be tested separately.

The JSON explicitly marks these items **NOT VERIFIED**:
guest boot, actual packet-level network denial, SELinux enforcement,
hypervisor-escape resistance and rollback success.

## Manual acceptance procedure on a dedicated test host

1. First complete `midnight-provisioner recover preflight` against the staged image.
2. With separate authorization, manually register the restored guest as a
   **new** libvirt VM on a disposable or dedicated Fedora test computer.
   Confirm the original guest/disk/backup remain unchanged.
3. Run `midnight-provisioner accept NEW-NAME --policy isolated --report /local/path/new.json`
   and ensure all current, inactive and saved-session XML definitions pass.
4. Separately inspect the live libvirt interfaces, host-side firewall routes,
   SELinux labels, VNC exposure, and QEMU service permissions. If a guest must
   be booted, use a benign test image, not malware.
5. Document the observed boot/shutdown behavior and the network-denial result.
   Do not mark a check as passed based solely on an XML inspection.
6. Keep all report files on protected local or encrypted storage. Only share a
   redacted summary if needed for review.

There is **no automatic guest import, boot, snapshot, restore or deletion** in
this acceptance workflow. Privileged modifications between the audit and
another tool's actions remain possible; Midnight Provisioner is not Qubes OS.

Related: [Fedora acceptance plan](FEDORA_ACCEPTANCE.md),
[Recovery staging](RECOVERY_STAGING.md) and
[Security model](SECURITY_MODEL.md).
