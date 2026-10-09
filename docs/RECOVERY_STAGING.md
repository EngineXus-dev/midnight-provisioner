# Verified offline recovery staging

Nightglass can now **copy an existing validated cold backup into a NEW folder**,
generate a new VM identity and update disk/NVRAM paths in a reviewable
\`domain.xml\`. **All virtual network interfaces are removed.** The original
backup, running VMs and Windows installation are left untouched.

**This is a staging workflow, not one-click VM restore.** Nightglass does NOT
call \`virsh define\`, import or start a virtual machine at this stage. The
generated XML is only for careful manual review on a Fedora/KVM host.

## User workflow

1. Use Nightglass **Cold backup** to export a fully shut-down dedicated VM.
2. Choose **Backup & verify → Verify saved backup** and check all hashes.
3. Choose **Recover into NEW folder**. Pick the original backup folder and a
   new destination *parent* directory, then enter a new, unique VM name.
4. Nightglass verifies every backup asset, validates its original XML, checks
   the intended destination is unused and has enough space, and shows a plan.
5. Approve the plan to create a *new* staging directory with:
   - Freshly copied QCOW2/RAW disk files;
   - Copied UEFI NVRAM, if present;
   - A proposed \`domain.xml\` containing the **new** guest name, rewritten
     disk/NVRAM paths, **no UUID or genid**, and **no virtual NICs**;
   - \`recovery-manifest.json\` containing SHA-256 digests;
   - \`INCOMPLETE\` during copying; it remains if an error occurs.
6. Run **Verify staged recovery** to check hashes, paths, new guest identity,
   and the offline device policy again.
7. On an isolated Fedora/KVM test system, manually review the staged VM XML,
   UEFI firmware paths, disk permissions and SELinux contexts. Only then
   consider defining a *separate* test guest in libvirt. Nightglass currently
   provides **no automated VM import**.

## CLI

\`\`\`bash
nightglass recover plan /path/to/backup /path/to/NEW-folder recovered-vm-01
nightglass recover stage /path/to/backup /path/to/NEW-folder recovered-vm-01
nightglass recover verify /path/to/NEW-folder
\`\`\`

Staging is confirmation-gated. It refuses an existing target directory,
existing VM name, original VM name, invalid backup manifest, hash mismatch,
unexpected source disk, symlink, attached ISO, unapproved host devices or
backup XML referencing external direct-boot kernels or disk backing chains.
It also refuses to stage a new folder inside the original backup.

No original disk, guest definition, firmware variable image or Windows file
is overwritten. Staged assets are created with private file permissions.

## What this does *not* prove

- **No boot test:** file hashes show consistency, not that the VM will boot.
- **No security certification:** the proposed XML must be rechecked *after*
  import because libvirt may add or adjust device settings.
- **No atomic snapshot/lock:** an external privileged process can change
  source data while it is being copied. Staging rejects source checksum
  mismatches and retains an \`INCOMPLETE\` marker on failure.
- **No signed provenance:** an attacker who controls both backup files and
  their manifest could make all SHA-256 hashes match malicious content.
- **No automatic lab network recreation:** even a restored Kali lab VM is
  staged with **all networking disabled** until a separate security review.
- **No implicit transfer of trust:** VM backup disks can contain credentials,
  malicious code or sensitive evidence. Store them on encrypted, access-
  controlled storage; keep them out of GitHub and sync folders.

If the recovered guest originally used UEFI, preserving its saved NVRAM does
not guarantee compatibility with firmware on a new computer. Review firmware
and machine-type compatibility before importing and perform an isolated
boot-and-rollback drill.

See [cold backup workflow](COLD_BACKUP.md) and
[security model](SECURITY_MODEL.md).
