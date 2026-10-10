# Guided offline VM preparation (v0.2 preview)

Nightglass offers **Prepare VM** on the Kali / malware workspace cards and in the
side navigation. The wizard is a **non-mutating preparation tool**: it does not
define virtual machines, create storage, download images, partition disks,
alter boot entries, or start guests. Actual VM installation still takes place
in virt-manager under your control.

## Workflow

1. Download Kali Linux or another Linux installer ISO from its publisher's
   official website. Obtain the **SHA-256 checksum from an authenticated
   publisher page**; do not rely on a hash supplied by an untrusted mirror.
2. On Fedora KDE, install the virtualization dependencies separately after
   reviewing `scripts/install/fedora-dependencies.sh`. The VM preview requires
   `virt-install` (the `virtinst` package), working `qemu:///system`
   connectivity and a supported UEFI firmware setup.
3. Start Nightglass, choose **Prepare VM**, and select *Pentesting* or
   *Malware analysis*. Browse for the local ISO and paste its 64-character
   official checksum.
4. Review the detected machine profile. The proposed VM RAM / CPU values are
   clamped to this host's available resources. By default, no virtual NIC is
   requested for either workspace. The analysis guest must remain entirely
   offline; the pentesting guest may be attached to a separately verified,
   non-forwarding lab network later.
5. Press **Verify ISO + preview VM**. A chunked SHA-256 check runs first.
   Next, virt-install is invoked **only with both `--dry-run` and
   `--print-xml`**, for the install-stage and post-install-stage XML.
   Both XML definitions must pass Nightglass's conservative VM audit.
6. If the preview passes, inspect the proposed command and settings.
   Open **virt-manager** and create the actual VM there. During VM creation,
   remove guest-host integration features that fail Nightglass's launch
   policy. Nightglass **does not run** the proposed command.
7. After the guest is created, use **Bind VM** in Nightglass. Its current
   libvirt XML is audited before Nightglass starts the VM.

The command line offers the same read-only preview:

```bash
nightglass provision pentest --iso /absolute/path/to/kali.iso --sha256 <PUBLISHER_SHA256>
nightglass provision analysis --iso /absolute/path/to/linux.iso --sha256 <PUBLISHER_SHA256>
```

## Important limitations

- **Dry-run XML is not a hardened isolation guarantee.** virt-install,
  libvirt, virt-manager, firmware and QEMU defaults may differ at actual
  creation time. Verify the *real* VM definition before starting it.
- `--print-xml` **without** `--dry-run` can create disk storage. Never
  remove that safeguard for preflight.
- This preview does **not** ensure the ISO is trustworthy, only that its bytes
  match the provided checksum. A checksum sourced from an attacker provides
  no assurance.
- Guest image and VM backup/restore automation are not available yet.
- On an 8 GiB laptop, use one VM at a time; even one guest with 2–3 GiB RAM
  may require closing memory-heavy host applications.
- Malware labs must not be treated as safe for high-risk samples until
  guest isolation is validated on real Fedora/KVM hardware. For high-risk
  malware, prefer a dedicated physical analysis host.
- Nightglass never silently changes an existing guest, storage pool,
  partition, UEFI configuration, Windows installation, or network.

Reference: [virt-install man page](https://github.com/virt-manager/virt-manager/blob/main/man/virt-install.rst), especially the `--dry-run` and `--print-xml` flags.
