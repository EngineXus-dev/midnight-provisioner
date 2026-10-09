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

## v0.2 — workspace provisioning
- [ ] Installer-assisted Kali and disposable analysis VM templates from verified checksummed images
- [ ] Dynamic RAM-pressure and swap indicator, VM runtime resource controls and external launch detection
- [ ] VM backups and tested offline baseline/restore procedure (not just managedsave)
- [ ] Network diagnostics including measured denial of lab to host/Internet reachability
- [ ] Read/write policy validation for live XML changes

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
