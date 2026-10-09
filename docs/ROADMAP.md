# Development roadmap

## v0.1 — foundation (this delivery)
- [x] Standalone project, name/design distinct from unrelated applications
- [x] Fedora-first GUI, real libvirt status/start/shutdown/managedsave, existing-VM binding
- [x] Per-workspace XML pre-start checks for disconnected or no-forward lab networking and host integration risks
- [x] Best-effort host RAM guard for under-11-GiB hosts (one active VM, max 3.5 GiB guest RAM)
- [x] Distrobox trusted-development creation and Konsole entry
- [x] Windows read-only preflight, Fedora opt-in dependencies, opt-in isolated lab network definition
- [x] Mock-based policy/lifecycle/metadata tests and CI definition
- [ ] Live testing with Fedora KDE, actual libvirt domains, guest networking, and no-root permission paths

## v0.1.2 — saved session audit and safe resume
- [x] Fail-closed managed-save XML verification (both saved and inactive VM configurations)
- [x] Memory pressure guard covers the saved VM memory allocation, not only the inactive definition
- [x] Disable managed-save for disposable analysis profiles; saved-session status in the UI and CLI
- [ ] Fedora/KVM end-to-end tests for resumed Kali sessions and manual out-of-band changes

## v0.1.3 — one install, portable machine tuning (draft)
- [x] One non-root Nightglass app setup script; remove separate 8/32 GB setup entrypoints
- [x] Detect RAM and CPU at every VM launch; clamp custom preferences to conservative budgets
- [x] Machine settings GUI with Automatic, Compact, Balanced, Performance and advanced controls
- [x] Machine-local settings isolated from portable workspace definitions and VM images
- [x] Optional source update check and user-confirmed fast-forward-only Git update
- [ ] Live Fedora/KDE setup, GUI and VM-limit smoke tests on 8, 16 and 32 GB systems
- [ ] Signature-verified release bundles and automatic dependency rollback before unattended installs

## v0.2 — offline provisioning preparation (draft)
- [x] GUI workflow for local ISO selection, independent VM identity and machine-aware guest defaults
- [x] Verify installer ISO against SHA-256 digest from the publisher
- [x] Fail-closed virt-install stage 1 AND stage 2 XML audits using --dry-run (no storage created)
- [x] Show reviewed settings and open virt-manager for intentional guest creation
- [ ] Full automatic guest creation **only** after Fedora live validation and verified offline hardening
- [ ] Real Kali and analysis guest install/boot/rollback tests on low-memory hardware

## v0.2 — workspace provisioning
- [ ] Installer-assisted Kali and disposable analysis VM templates from verified checksummed images
- [ ] Dynamic RAM-pressure and swap indicator, VM runtime resource controls and external launch detection
- [ ] VM backups and tested offline baseline/restore procedure (not just managedsave)
- [ ] Network diagnostics including measured denial of lab to host/Internet reachability
- [ ] Read/write policy validation for live XML changes

## v0.2.1 — cold backup and integrity verification (draft)
- [x] User-confirmed cold backup of inactive, file-backed, non-layered restricted guests
- [x] Copy virtual disks, NVRAM and inactive libvirt XML into a NEW private backup directory
- [x] Per-file SHA-256 manifest, failed-copy INCOMPLETE marker and read-only verifier
- [x] KDE backup/verify actions and CLI equivalents without automatic restore or deletion
- [ ] Fedora/KVM live backup/boot/restore drills, firmware handling and SELinux review
- [ ] Dedicated rollback workflow only after reproducible end-to-end restore tests

## v0.2.2 — verified offline recovery staging (draft)
- [x] Accept only verified cold backup manifests with disk/XML path consistency
- [x] Stage files into an exclusively new directory and recalculate SHA-256 digests
- [x] Generate a fresh VM name, remove prior identifiers, and rewrite new disk/NVRAM paths
- [x] Force restored guest XML offline, re-audit the staged definition and reject incomplete copies
- [x] GUI and CLI plan/stage/verify without automatic libvirt import or boot
- [ ] Fedora/KVM boot and recovery drill, SELinux/firmware validation and permission review
- [ ] Future automatic NEW-VM definition only after disposable isolated restore tests

## v0.3 — defense in depth
- [ ] Polkit actions and minimal privileged policy service, no trusted XML audit from user-editable settings
- [ ] SELinux device/volume access review; stronger VM security architecture tests
- [ ] Filesystem transfer broker with quarantine, checksums and explicit user acceptance
- [ ] Snapshot lifecycle with qcow2, NVRAM/UEFI safety and comprehensive restore tests
- [ ] Autostart off by default, deny-by-default isolated environment actions

## v0.4 — distro switching and portable workspaces
- [ ] Safe distrobox templates and apps for multiple trusted distros with exported launchers
- [ ] Controlled VM export/import bundles (only with user-confirmed paths and snapshot hygiene)
- [ ] Polished KDE system tray and per-domain launcher interface
- [ ] Optional dedicated browser VM for personal isolation on >= 16/32 GB memory

## v1 — documented secure workstation deployment
- [ ] Host support matrix (AMD-V, IOMMU, Secure Boot, LUKS, libvirt, Fedora releases)
- [ ] Reproducible installation artifact and hardware-specific verification on test machines
- [ ] Audited, tested isolation rules; no unsupported security guarantees
- [ ] Clearly documented Windows 10 coexistence and rollback procedures
