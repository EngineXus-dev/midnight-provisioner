# Read-only runtime sVirt metadata observation

Midnight Provisioner can collect SELinux/sVirt **metadata** for an already-running
**benign, restricted guest** without starting it or interacting with its
operating system:

```bash
midnight-provisioner runtime-label SAFE_GUEST --policy isolated
midnight-provisioner runtime-label SAFE_GUEST --policy lab \
  --report /path/to/NEW-private-report.json
```

In the application, use **Diagnostics → Observe running VM sVirt labels**,
then optionally **Save local runtime observation**.

This is only a **point-in-time metadata observation**. It is not automatic
guest startup, an isolation test, or a reason to boot suspicious software.

## What is inspected

- An **already-registered**, **running/paused/idle** VM under
  `qemu:///system`. Shut-off or unrecognized states are not approved.
- The existing registered guest audit for current/live, persistent/next-boot,
  and any managed-save libvirt XML: guest identity, RAM budget, devices,
  declared network policy, and explicit security-label opt-outs.
- Fedora host `getenforce` / kernel SELinux state, which must positively
  report **Enforcing**; permissive, disabled, conflicting, or unavailable
  results block the report.
- `virsh capabilities` advertises a **selinux** host security model.
- Running guest's libvirt XML includes exactly one SELinux domain
  `<seclabel type="dynamic" model="selinux" ...>` with an expected
  `svirt_t` process label and `svirt_image_t` image label, whose MCS
  categories agree.
- The guest's running state is still the same at the end of inspection.

Reports show PASS (METADATA ONLY) or UNVERIFIED / BLOCKED, using text as
well as the user interface theme's colors. Missing or inconsistent evidence
never becomes a pass.

## What this does **not** establish

The XML labels reported by libvirt are **not direct measurements** of the
QEMU process's effective Linux security context or the on-disk image
inodes' actual SELinux labels. Verifying those would require separate
host-side inspection and is not performed here.

Likewise, the report does not establish packet-level guest-to-host/Internet
denial, successful guest boot, firewall rules, image trustworthiness, escape
resistance, or malware containment. The checker does not call `virsh start`,
`define`, `shutdown`, run a guest agent, execute guest commands, alter
host policy, change EFI/Windows partitions or upload telemetry.

A passing report is not a security certificate. Other privileged clients
can change configuration immediately afterwards. Only run any live
isolation tests with a benign guest on a supervised Fedora test host.

The optional JSON evidence file is created with mode `0600` and will
**never overwrite** another file. It deliberately withholds full
SELinux category identifiers, host storage paths and guest disk contents.
