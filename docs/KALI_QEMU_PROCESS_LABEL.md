# QEMU process SELinux labels for an already-running benign Kali VM

Nightglass previously inspected libvirt's **reported** dynamic sVirt labels.
This opt-in step tries to observe the actual **QEMU process security context**
through Fedora's read-only Linux `/proc` filesystem. It is an additional
host-side observation, **not a certificate of isolation**.

## Requirements and sequence

The operator must have **already manually started an authorized, benign,
separate Kali recovery guest** and reviewed the offline recovery handoff.
Nightglass never boots that guest, initiates shell commands inside it, or
touches its qcow2 while running.

Use the original Kali template setup plan and exact **different** recovery
guest name:

```bash
nightglass templates process-label /path/to/original-recon-plan.json \
  --guest nightglass-kali-recon-rehearsal
```

Or choose **Prepare VM → Inspect effective QEMU sVirt label** in the GUI.
The Kali toolkit action buttons are arranged into a compact grid rather
than one overly wide row.

For local private, metadata-only evidence, choose a **NEW** file:

```bash
nightglass templates process-label /path/to/original-recon-plan.json \
  --guest nightglass-kali-recon-rehearsal \
  --report /path/to/NEW-private-label-observation.json
```

The report uses exclusive-create `0600` permissions. Existing files,
`.env`, virtual environments, guests and partitions are never overwritten.

## Actual read-only host observations

1. Validate the curated Kali setup plan and the **new** recovery guest name.
2. Reuse Nightglass's registered live/inactive/saved XML and host SELinux
   enforcing + libvirt dynamic sVirt metadata audit. If any part fails, do
   **not** inspect host processes or return a match.
3. Read the current system-libvirt guest XML and derive its current
   UUID and dynamic sVirt process label.
4. Enumerate numeric `/proc/PID` entries without using sudo. Match
   **exactly one** `qemu-system-*` or `qemu-kvm` process whose `-uuid`
   and `-name guest=...` arguments match the selected registered guest.
5. Read that process's `/proc/PID/attr/current`, then compare the full
   **effective process label** against the current libvirt dynamic sVirt
   label. Reject unknown/unconfined labels and MCS category differences.
6. Recheck process argv, start time (to narrow PID reuse), effective
   SELinux context, libvirt UUID/label and running VM state.

The only host-side process files read are bounded
`/proc/PID/cmdline`, `/proc/PID/stat`, and
`/proc/PID/attr/current`. This does not read environments, credentials,
QEMU memory, open file descriptors, guest disks, or guest files. No
subprocess, root or privileged host operation is invoked.

If your Fedora system uses `hidepid`, Linux process access controls or
SELinux rules that prevent an ordinary user reading these attributes,
**BLOCKED / UNVERIFIED** is the expected result. Do not grant broad
`/proc` access, disable SELinux, setuid the Nightglass process, or use
sudo just to make this check green.

## Critical limits

A process command line can be spoofed. Even a matching name, UUID and
SELinux context is **not cryptographically authenticated**, does not
prove the executable's origin and does not eliminate a privileged race.

This is **not** a verified Kali OS desktop boot, effective guest network
packet-denial test, QEMU disk inode security-context inspection, recovery
rollback test, virtual-machine escape assessment, or an attestation that
the guest is safe for untrusted malware.

The evidence intentionally contains **no PID**, raw QEMU command-line
arguments, SELinux MCS category IDs, host disk paths or other users'
process metadata. All attestations outside the observed process-label
comparison remain **false**.

Real supervised Fedora/KVM acceptance is still required, including
operator-recorded guest boot, QEMU process and disk labels, packet-level
network tests and a recovery rehearsal. The actual host check must be
run on your Fedora machine; CI only tests synthetic process fixtures.
