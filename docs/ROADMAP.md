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

## v0.2.3 — Fedora import readiness checks (draft)
- [x] Read-only staged-image integrity and installed libvirt domain schema check
- [x] Read-only QEMU image format, backing-chain and snapshot inspection
- [x] Verify KVM access, unused VM name and host-aware guest RAM limits
- [x] GUI/CLI readiness check and explicit Fedora smoke-test script
- [x] Synthetic tests for refusal cases and no VM mutation
- [ ] Real Fedora/KVM smoke results and supervised guest boot/network acceptance evidence
- [ ] Automatic NEW-VM import remains disabled until actual host acceptance

## v0.2.4 — registered guest acceptance evidence (draft)
- [x] Read-only current/live, inactive, and managed-save libvirt XML inspection
- [x] Fail if any registered definition contains prohibited devices or networking
- [x] Check inspected VM identity, machine RAM budget, and non-forwarding lab network definition
- [x] GUI and CLI audit with local JSON export that never overwrites existing reports
- [x] Tests against simulated libvirt responses and explicit unverified runtime observations
- [ ] Fedora/KVM physical-host audit and observed guest boot/network-denial test results
- [ ] Controlled automatic import remains disabled until those results exist

## v0.2.5 — native libvirt/QEMU fixture verification (draft)
- [x] Real libvirt schema validation on a benign offline KVM XML fixture in GitHub CI
- [x] Real qemu-img metadata checks using temporary qcow2/raw images
- [x] Native QCOW2 backing-file chain refusal and schema-valid NIC policy denial
- [x] Separate native-tools CI job alongside mocked Python unit tests
- [ ] Confirm test results on Fedora KDE with the distribution's installed utilities
- [ ] Real KVM boot, packet-level isolation and snapshot/restore tests remain unverified

## v0.2.6 — live host resource and external VM awareness (draft)
- [x] Read-only MemAvailable and swap-occupancy status, not misleading MemFree figures
- [x] Account for all active system-libvirt guests, including externally started/unbound VMs
- [x] Compare observed activity with clamped host-specific resource budgets
- [x] Opt-in, Diagnostics-only 20-second GUI refresh and read-only CLI command
- [x] Unknown backend/resource state never returns an all-clear result
- [x] Synthetic test coverage for memory and hypervisor failure modes
- [ ] Validate on Fedora KDE with real 8/16/32 GB RAM pressure and out-of-band VM starts
- [ ] Actual VM allocation/reservation accounting and measured host-pressure behaviors

## v0.3a — Fedora host security posture read-only baseline (draft)
- [x] Inspect SELinux mode, KVM character-device permissions, and non-root process state
- [x] Report firewalld daemon state and IPv4/IPv6 host forwarding as INFO only, never isolation proof
- [x] Fail to UNKNOWN on missing, inconsistent or unreadable mandatory host settings
- [x] Reject restricted VM/disk XML explicitly disabling security labels or relabeling
- [x] Host security CLI command and on-demand Diagnostics GUI action
- [x] Synthetic host-policy and sVirt opt-out regression tests; offscreen Qt button coverage
- [ ] Real Fedora enforcing/sVirt label and polkit functionality acceptance
- [ ] Independently measured guest-to-host and guest-to-Internet traffic isolation

## v0.3 — defense in depth
- [ ] Polkit actions and minimal privileged policy service, no trusted XML audit from user-editable settings
- [ ] SELinux device/volume access review; stronger VM security architecture tests
- [ ] Filesystem transfer broker with quarantine, checksums and explicit user acceptance
- [ ] Snapshot lifecycle with qcow2, NVRAM/UEFI safety and comprehensive restore tests
- [ ] Autostart off by default, deny-by-default isolated environment actions

## v0.3b — guarded VM start audit parity (draft)
- [x] Audit libvirt current/live AND persistent/next-boot XML before restricted guest starts
- [x] Audit managed-save XML as a third independent configuration
- [x] Reject next-boot network/device/sVirt-label drift even if current XML is acceptable
- [x] Reject mismatched VM name or conflicting UUID among inspected definitions
- [x] Apply declared maximum RAM limits to persistent and saved definitions, not only live XML
- [x] Synthetic tests verify that drift blocks before any `virsh start` or VM mutation
- [ ] Independently confirm managed-save resume and persistent definition behavior on Fedora/KVM
- [ ] Reduce possible races with other privileged libvirt clients; XML snapshots are point-in-time only

## v0.3c — verified recovered-guest handoff (draft)
- [x] Reject staged VM XML disk driver format mismatches before native QEMU processing
- [x] Inspect live/current and persistent/next-boot registered libvirt XML against verified staging disk paths
- [x] Refuse unexpected disks, mounted ISOs, extra NVRAM, wrong formats, and inconsistent guest UUIDs
- [x] Refuse active and managed-saved recovered guests for offline handoff
- [x] Read-only `qemu-img info` against verified staged files only, with known-good format and chain checks
- [x] CLI/GUI comparison, private exclusive-create JSON report and mock regression coverage
- [ ] Supervised benign Fedora/KVM manual-import and network isolation measurements
- [ ] No automatic import/boot; privileged-host races and arbitrary disk content trust remain unresolved

## v0.3d — read-only running guest SELinux/sVirt metadata observation (draft)
- [x] Inspect only ALREADY-running restricted guests: never boot malware or invoke guest agents
- [x] Require host SELinux Enforcing and libvirt-advertised SELinux security model
- [x] Verify dynamic sVirt process/image label metadata and matching MCS categories, without exporting categories
- [x] Recheck VM state and existing live/inactive/saved XML policy audit; unknown state fails closed
- [x] CLI/GUI on-demand observation and private local exclusive-create JSON evidence
- [x] Synthetic refusal tests for permissive host, missing security labels, category drift and unsafe NICs
- [ ] Verify on actual Fedora KDE/libvirt with a benign running guest
- [ ] Independently inspect effective QEMU process and disk inode labels, and measure network denial

## v0.3e — curated Kali VM tool templates (draft)
- [x] Seven purpose-specific white-hat and red-team templates with small package selections
- [x] One planned unique Kali VM name and separate qcow2 disk per template; no all-tools image
- [x] Conservative RAM/CPU/disk suggestions clamped to actual host limits (8 GiB laptop compatible)
- [x] GUI/CLI catalog selection integrated with existing Kali installer SHA-256 and two-phase XML dry-run
- [x] Keep all initial VM definitions network-disconnected, with no default host shares or USB passthrough
- [x] Read-only package suggestions; never auto-install, auto-download, clone, define or start a guest
- [x] Unit and Qt GUI smoke coverage for catalog, unsafe packages, template/analysis separation
- [ ] Verify actual Kali apt package availability/dependency versions inside a benign Fedora/KVM guest
- [ ] Independently tested per-guest installation/rollback manifests, template snapshots and manual package setup
- [ ] Only consider user-confirmed guest-scoped automation after real Fedora isolation testing

## v0.3f — independent Kali guest setup manifests and version drift (draft)
- [x] Private exclusive-create setup records with catalog fingerprint, small per-guest package set and offline policy
- [x] Reject catalog/package/guest-policy drift and modified installation/provenance claims when reloading plans
- [x] Validate bounded user-supplied Kali inventory JSON; report missing packages, wrong VM identity, version drift and dpkg-audit status
- [x] Optional private untrusted version lock with false/unknown supply-chain and rollback assertions
- [x] GUI and CLI export, verify, compare and lock workflow; no host libvirt mutations, guest commands or apt installs
- [x] Synthetic unit and Qt GUI regression coverage for oversize/symlink inputs, plan tampering, and no-overwrite behavior
- [ ] Validate package availability and dependencies against Kali-signed repos within a benign guest
- [ ] Integrate real guest attestations, release pinning, rollback tests and supervised Fedora/KVM acceptance
- [ ] Automatic tool provisioning and VM cloning remain disabled until these guarantees are independently verified

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
