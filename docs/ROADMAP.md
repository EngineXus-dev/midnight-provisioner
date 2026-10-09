# Development roadmap

> Privacy note: hardware and installation scenarios are illustrative. Discover actual device details independently; historical scenarios are not current authorization.

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

## v0.3g — opt-in Kali guest inventory collection, without installation (draft)
- [x] Standalone, standard-library Python helper for explicit execution inside an ALREADY-INSTALLED, benign Kali guest
- [x] Local read-only dpkg-query, apt-cache policy and dpkg --audit commands — no apt install/update or network access
- [x] Fail closed on unknown distro, root execution, missing/malformed local package data or changed safety flags
- [x] Save only a NEW private guest inventory matching the host v0.3f schema, with no secret/disk collection
- [x] GUI and CLI show the manual guest steps without executing guest commands or transferring files
- [x] Synthetic tests for missing packages, malformed metadata, insufficient permissions, symlinks and no-overwrite
- [ ] Supervised Kali/Fedora hardware validation of actual dpkg/apt output and package availability
- [ ] Implement/test a separately approved quarantined host↔guest transfer channel (NOT enabled here)
- [ ] Independently verify signed Kali package provenance, dependency closure and rollback before tool installation automation

## v0.3h — Kali template package lock drift review (draft)
- [x] Compare previous private version lock and newer manually supplied Kali package inventory for the SAME curated guest
- [x] Verify original template catalog fingerprint, guest identity, Kali release and installer ISO claim before comparing
- [x] Report missing/uninstalled packages, observed version changes, unavailable candidates and non-clean/unknown dpkg audit
- [x] Distinguish version change from upgrade/downgrade; do not invent Debian version ordering from string comparison
- [x] Reject locks falsely claiming signed provenance, dependency closure or tested rollback
- [x] Provide read-only CLI and GUI three-file workflow plus optional NEW private local JSON evidence
- [x] Unit and Qt GUI tests for wrong guest, modified provenance, version drift, invalid metadata, no overwrite and cancellation
- [ ] Real Fedora/Kali inventory/lock drift acceptance, reproducible signed dependencies and cold restore validation
- [ ] Authenticated guest state evidence and independently reviewed transfer remain unavailable

## v0.3i — Kali guest ISO and host-readiness preflight (draft)
- [x] Link immutable separate-VM Kali template manifest to real local publisher-claimed ISO SHA-256 verification
- [x] Reuse both real `virt-install --dry-run --print-xml` stages and exact guest identity/network policy checks
- [x] Refuse already-used guest name; enforce hardware-aware RAM/concurrency limits for system-libvirt guests
- [x] Read-only free-space heuristic for an existing target volume with full qcow2 expansion caution
- [x] Block missing RAM, failed system-libvirt inspection, exhausted guest cap, low headroom, mismatched ISO, invalid XML
- [x] Read-only CLI and explicit GUI action bound to saved template/guest identity; no VM or disk writes
- [x] Synthetic regression tests for failures and offscreen Qt UI selection/cancel flow
- [ ] Supervised Fedora/KVM physical machine acceptance of RAM, storage, ISO installer and network behavior
- [ ] Real disk-space reservation/verified boot/guest-only installation/rollback are still NOT implemented

## v0.3j — read-only Kali template registration and independent-disk review (draft)
- [x] Connect each curated Kali setup plan to a registered, MANUALLY installed, SHUT-OFF system-libvirt VM
- [x] Check current/inactive XML identity, persistent UUID, no managed save, exact one qcow2 disk and initial no-NIC policy
- [x] Reject mounted installer media, extra disks, unexpected storage types and native qcow2 backing/snapshot/encryption metadata
- [x] Read-only compare exact selected disk source path across current/inactive/saved definitions of other system libvirt guests
- [x] Validate guest RAM/vCPU against current host resource caps and reject inaccessible/conflicting libvirt data
- [x] Add opt-in GUI audit, CLI and NEW private local metadata report with no host/guest writes
- [x] Unit and offscreen Qt regression tests for cross-guest plan reuse, duplicate disk paths, unknown VM states and unsupported image metadata
- [ ] Strongly verify same-inode/hardlink/alias disk collisions without trusting libvirt XML alone
- [ ] Real Fedora/KVM benign-guest install, Kali package check, runtime network/SELinux and independent cold restore tests
- [ ] Do not automatically install, clone, define or boot a Kali VM without hardware acceptance and explicit user confirmation

## v0.3k — registered Kali disk hardlink and path-alias hardening (draft)
- [x] Refuse selected qcow2 images with kernel hardlink count other than one, even for hardlinks outside the selected folder
- [x] Compare lexically normalized registered disk sources across current/inactive and managed-save XML
- [x] Detect symlinked foreign-guest disk references within the user-selected, previously validated disk directory using lstat only
- [x] Recheck selected qcow2 disk inode identity and link count after native metadata and libvirt XML reads
- [x] Keep native disk inspection limited to the single user-selected guest disk; no arbitrary file opens from other VM XML
- [x] Synthetic regression tests for cross-folder hardlinks, lexical aliases, saved-session aliases, same-folder symlinks and mid-inspection link races
- [ ] Paths outside the selected storage directory may still refer to the disk via symlink, bind mounts or storage indirection, and are NOT automatically resolved
- [ ] Real Fedora/KVM isolation, cold backup/restore, package provenance and controlled guest execution acceptance remain pending

## v0.3l — independently verified Kali template cold backup baseline (draft)
- [x] Link a registered shut-off Kali VM, its selected independent disk and an existing cold backup to the same curated template
- [x] Rehash all backup assets before using archived XML, NVRAM, manifest disk sources or QEMU metadata
- [x] Refuse guest-name/UUID mismatches, unexpected NIC, ISO, extra disk, absent or wrong UEFI NVRAM copy
- [x] Refuse hardlinked/shared backup disk, invalid qcow2 header, backing layers or differing guest disk virtual size
- [x] Recheck VM shutdown state and archived image inode after inspection; flag backups stored on the same filesystem as the guest
- [x] Opt-in CLI/GUI read-only baseline audit with optional NEW private metadata evidence and synthetic test coverage
- [ ] Independently stage, import, boot and restore a benign Kali guest on supervised Fedora/KVM
- [ ] Signed backup manifest and effective guest/host network/SELinux verification remain unavailable
- [ ] Do not automate Kali package installs or in-place rollback based on hash matches alone

## v0.3m — Kali backup-to-offline-recovery linkage (draft)
- [x] Bind independently staged NEW offline recovery guest to exact original curated Kali plan, original VM name and lab policy
- [x] Rehash verified cold backup and staged copy before trusting any XML/disk metadata
- [x] Refuse nested backup/staging destinations, missing/mismatched qcow2 or NVRAM assets, link-count and inode reuse
- [x] Compare canonical staged XML to deterministic offline transformation of original verified backup XML
- [x] Reject copied images that changed even after someone rewrote staging manifest checksums, and reverify file/inode state after comparison
- [x] CLI/GUI read-only source-copy verification with optional NEW private report and synthetic tests
- [ ] Manual supervised Fedora/KVM staged import preflight, benign new-guest registration, handoff check, boot and actual rollback evidence
- [ ] Guest package provenance, packet-level isolation and SELinux runtime remain unverified; no automatic import/restore

## v0.3n — registered Kali recovery import handoff (draft)
- [x] Bind original curated Kali plan, verified cold backup and separate offline recovery stage to MANUALLY REGISTERED new VM
- [x] Reuse full existing registered recovery handoff policy and QEMU disk metadata checks; require shut-off state/no saved resume
- [x] Reject recovered VM UUID reuse, missing/inconsistent current/inactive UUID and wrong template/new guest identity
- [x] Require explicit libvirt autostart OFF; unknown or enabled state fails closed and is rechecked
- [x] Read-only scan of other registered current/inactive/saved disk-source XML for aliases to recovered qcow2
- [x] Rehash staging files and recheck recovered VM shutoff status after libvirt observations
- [x] CLI and opt-in Qt GUI audit plus NEW private non-attestation JSON evidence; synthetic regression tests
- [ ] Actually boot, exercise and restore a benign Kali VM under supervised Fedora/KVM with packet and SELinux verification
- [ ] Actual external disk alias resolution, provenance/authenticated backup signatures and automatic guest lifecycle remain out of scope

## v0.3o — read-only running Kali recovery metadata observation (draft)
- [x] Introduce an opt-in observation for an ALREADY manually started benign recovered Kali guest, separate from the original guest
- [x] Bind curated original template and SHA-256-verified INACTIVE cold backup to unique live VM UUID, selected disk and current/inactive libvirt definition
- [x] Reuse existing host SELinux enforcing and sVirt label observation; refuse runtime labels/policy not positively verified
- [x] Require truly running libvirt state, explicit autostart OFF, no NIC/mounted ISO/host devices, and no managed save
- [x] Read other registered guest current/inactive/saved XML for known disk path aliases, without opening foreign guest disk images
- [x] Do NOT hash or use qemu-img on the active writable qcow2; recheck only disk inode identity while rehashing inactive source backup
- [x] Add CLI/Qt GUI, synthetic fail-closed tests and private metadata-only evidence with no VM lifecycle changes
- [ ] Verify real QEMU /proc SELinux labels, guest OS boot, packet-level network denial and actual restore on supervised Fedora/KVM
- [ ] Authenticated guest provenance and resilient protection from privileged libvirt/storage races still unavailable

## v0.3p — actual QEMU process SELinux context observation (draft)
- [x] Match exactly one already-running QEMU process to live system-libvirt guest UUID AND name using read-only bounded /proc metadata
- [x] Compare actual /proc/PID/attr/current effective sVirt process label against libvirt's explicit dynamic current-domain SELinux label
- [x] Require prior registered policy, SELinux enforcing host/capabilities, matching live sVirt MCS metadata and running guest state
- [x] Recheck process start time, argv, effective label and libvirt UUID/label/state to narrow PID-reuse or privilege-race windows
- [x] Fail closed on unreadable/missing /proc, duplicate QEMU process identity, unknown labels, or unsupported SELinux configuration
- [x] No sudo/privilege fallback and no QEMU guest/file/active-disk probes; preserve process PID/cmdline/MCS/host path privacy
- [x] Compact GUI Kali actions in 3-column grid; add opt-in CLI/GUI effective-label check and synthetic /proc/Qt regression coverage
- [ ] Run on real Fedora KDE/KVM hardware (ordinary user); verify permissions, QEMU process label format and false-negative behavior
- [ ] Confirm QEMU disk inode SELinux context, actual guest boot and packet-level network denial under supervised Fedora acceptance
- [ ] Actual OS recovery, unsigned package/authenticated image provenance, unregistered storage aliases and privileged races remain unverified

## v0.4 — distro switching and portable workspaces
- [ ] Safe distrobox templates and apps for multiple trusted distros with exported launchers
- [ ] Controlled VM export/import bundles (only with user-confirmed paths and snapshot hygiene)
- [ ] Polished KDE system tray and per-domain launcher interface
- [ ] Optional dedicated browser VM for personal isolation on >= 16/32 GB memory

## v0.3r — Windows dual-boot safety gate and rollback preparation (draft)
- [x] Standalone native Windows read-only firmware, RAM/CPU virtualization, Secure Boot, Fast Startup, OS disk and BitLocker-status inspection
- [x] Do not collect recovery keys, modify partitions/EFI/BCD/boot entries, disable protection or trigger system restart
- [x] Treat unknown firmware, encryption, partition or recovery status as HOLD — no automated OS install/shrink decision
- [x] Document Fedora live-USB hardware checks, Windows recovery USB, verified offline backups and rollback stop conditions
- [x] Add native Windows PowerShell parser check instructions and static Python no-mutation regression guards
- [ ] Execute the Windows reviewer on the intended PC and inspect results; no system changes before backup validation
- [ ] Confirm exact target-disk/EFI plan and recovery strategy before any Fedora graphical installer use
- [ ] Boot Fedora live USB and verify drivers, input, network, external storage, suspend/resume and return to Windows
- [ ] Explicit user authorization for installation is still REQUIRED; no automated partitioning or EFI setup
- [ ] Real Fedora KVM/SELinux/sVirt/live guest/restore gates remain separate and unverified

## v0.3s — optional Windows 11 upgrade-first planning (draft)
- [x] Record 2026-10-09 read-only Windows 10 Home baseline: UEFI, Windows GPT Disk 0, distinct GPT Disk 1 subsequently user-confirmed portable, RAM and firmware status
- [x] Revise native Windows reviewer to display read-only TPM presence/readiness/version and second-disk bus/partition metadata without extracting TPM keys or selecting storage
- [x] Preserve manufacturer firmware, TPM, encryption and Windows recovery protections; no BitLocker suspension or unsupported Windows 11 bypass
- [x] Add optional Windows 11-first route and separate post-upgrade re-baseline before Fedora installation
- [x] Extend static safety regression checks; maintain a clear manual hold on OS upgrade/partitioning/EFI changes
- [ ] Run updated read-only Windows 10/11 reviewer and real PowerShell AST parser on target Windows computer
- [ ] Review official PC Health Check Windows 11 eligibility, TPM 2.0/Secure Boot capability, encryption status and Windows recovery keys privately
- [x] Confirm Disk 1 is the user's PORTABLE drive; permanently exclude it from proposed Fedora and multiboot-USB formatting targets
- [ ] Investigate a safe Fedora storage layout on the actual Windows internal disk after Windows recovery is proven; portable Disk 1 remains off-limits
- [ ] If Windows 11 chosen: user-selected clean install must be independently approved, verified and recovered before Fedora live-USB/partitioning
- [ ] Fedora KDE host/KVM/sVirt isolation/benign guest recovery acceptance remains unverified; never auto-install or merge drafts without owner approval

## v1 — documented secure workstation deployment
- [ ] Host support matrix (AMD-V, IOMMU, Secure Boot, LUKS, libvirt, Fedora releases)
- [ ] Reproducible installation artifact and hardware-specific verification on test machines
- [ ] Audited, tested isolation rules; no unsupported security guarantees
- [ ] Clearly documented Windows 10 coexistence and rollback procedures

## v0.3t — dedicated multi-ISO deployment USB (draft plan)
- [x] Design one USB with unmodified official Windows 11 x64 and Fedora KDE Plasma 44 Live ISOs and independent boot-menu choices
- [x] Require THIRD dedicated expendable USB stick; user-confirmed portable Disk 1 MUST be excluded from USB writer and OS installer targets
- [x] Document Ventoy Secure Boot compatibility and policy risks; permit fallback to separate official USB installers
- [x] Distinguish in-place and clean Windows 11 installation; user chose clean-install LATER, after verified portable backups
- [ ] Obtain and verify signed Fedora checksum and official Windows ISO, test UEFI boot menus without starting any installation
- [ ] Validate dedicated USB target and its explicitly approved destructive formatting; no automatic Ventoy/partition execution
- [ ] User-approved clean Windows 11 installation AFTER verified backups and recovery, then Windows re-baseline and separate Fedora host security acceptance

## v0.3u — deferred clean Windows 11 and 16 GB one-USB readiness (planning)
- [x] Record user choice: CLEAN Windows 11 later, not an in-place upgrade and not immediate
- [x] Record user-owned separate 16 GB USB; verify Windows/Fedora ISO cumulative sizes before proposing a multiboot writer
- [x] Preserve example backup-drive capacity portable Disk 1 for user backups only; do not format/select it for Windows, Fedora or boot USB
- [x] Add staged data-backup review for local Git/untracked/ignored files, secrets and reproducible project environments
- [x] Require future backup verification, offline recovery keys as applicable, correct Windows Home edition/licence and later explicit approval
- [ ] Verify actual copied backups and USB media/ISO checksums; no current execution authorization
- [ ] Confirm Windows 11 hardware eligibility and clean-install EFI/partition target by physical identity, not existing disk numbers
- [ ] Do NOT schedule, boot, install, partition, format or merge PRs until user explicitly requests each next stage

## v0.3v — Windows 11 Lite image build policy (draft / no ISO built)
- [x] Verify official Windows 11 download now lists 26H2; reject stale 25H2-only assumption
- [x] Require licensed Home (existing Windows) or separately licensed Pro, not automatically Pro-only media
- [x] Specify two-stage NTLite Free edition/working-WIM -> conservative app tweaks -> final install.esd / bootable ISO, retaining original untouched ISO
- [x] Keep Windows Update/WinRE/Defender/firewall, TPM/Secure Boot/BitLocker, Store/WebView2, AMD drivers, WSL2/Hyper-V and developer runtime dependencies
- [x] Explicitly reject 3 GB ISO / 2 GB RAM / 9 GB install as guarantees or required size targets
- [x] Avoid stacking WinUtil + Win11Debloat + invasive RemoveWindowsAI system component removals
- [x] Commit opt-in HKCU-only dark/quiet preferences helper with preview default, consent gating, exclusive snapshot and undo
- [ ] Validate helper syntax via Windows PowerShell AST, run synthetic tests and test Apply/Undo on disposable Windows 11 VM first
- [ ] Check actual official Windows/Fedora ISO sizes vs separate 16 GB USB before any download/USB writing
- [ ] Do not build ISO, format USB, run setup, install Windows/Fedora, weaken security or merge draft PRs without separate future approval

## v0.3w — Windows 11 Pro privacy and 32-request profile (draft)
- [x] Record valid Pro licence claim without storing key; require Windows 11 Pro activation validation
- [x] Map 32 preferences plus OneDrive/Widgets/promotional apps and AI suite to 35 reviewed groups
- [x] Inspect user-provided Get.ps1 launcher and WinUtil ZIP; do not run remote downloader or broad default preset
- [x] Stage read-only Preview / exclusive-new ExportPlan / explicitly gated later ApplyCore based on pinned local Win11Debloat.ps1 SHA256
- [x] Separate app uninstalls, automatic device encryption, Start pin clearing, Sandbox, WSL2 and Brave/Chrome policies from reversible core
- [x] Keep security patches, Defender, firewall, BitLocker capability, TPM/Secure Boot, WinRE, Store/WebView2 and WSL/Docker development dependencies
- [ ] Parse new PowerShell with native Windows 11 Pro; run unit tests and disposable VM Apply/Undo before user use
- [ ] Independently verify vendor script hash/flags/rollback semantics and each requested setting on 26H2
- [ ] No installed Windows, ISO/USB, backups, Fedora disk layout or PR merges altered as part of planning

## v0.3y — Windows 11 Pro activate-later and safe media preflight (draft)
- [x] Add alternate `activate_later` (default) vs `activate_during_setup` product-key flow, never collect/store keys
- [x] Explicitly handle user-reported valid Pro key vs possible OEM Windows Home firmware key selecting wrong edition
- [x] Update PowerShell Preview/ExportPlan to record key timing only, with user-verifiable Pro edition/activation later
- [x] Add pure-stdlib media preflight: two regular ISO sizes, optional streaming SHA-256, explicit measured USB usable bytes and 1 GiB capacity reserve
- [x] Require separate published ISO provenance; a raw file hash/fit estimate cannot verify publisher or secure boot
- [x] Preserve example backup-drive capacity portable disk as backup-only; no implicit USB writer, shrink, ISO download or Windows install
- [ ] Execute syntax/contract tests on latest cumulative branch in isolated offline release gate (source PR currently unverified)
- [ ] Later user-only decisions: verify separate 16GB stick, media hashes, real Pro edition, backups and install timing; NO install now

## v0.3x — cumulative release candidate offline integration gate (draft)
- [x] Implement an opt-in one-branch, new-detached-worktree verification runner to avoid all GitHub Actions usage
- [x] Default PLAN ONLY; no implicit fetch, Docker image acquisition, OS or filesystem mutation
- [x] Parse all fetched PowerShell and Python source on Windows WITHOUT running fetched code on the host
- [x] Run full Linux synthetic Python 3.11/3.12/3.13 matrix and Fedora 43 Qt/native fixture suites inside sequential rootless offline Docker containers
- [x] Refuse to claim green if any test is failed, missing, blocked or skipped as a mandatory verification stage
- [x] Write new exclusive-create local log and minimal check summary tied to the exact detached Git SHA, retaining clear physical Fedora hardware HOLD
- [x] Reconcile stale old-Home assertions with the reported Pro key, without storing that key or running Windows installation
- [ ] Have user run latest Windows parse-only and Docker test gate against exact current cumulative branch; review log and adjust actual failures
- [ ] Review draft branch ancestry and each diff before any explicit owner-approved PR merge (no automatic merge)
- [ ] Independently verify real Fedora SELinux/sVirt, KVM, guest networking and recovery before security acceptance
- [ ] Windows 11 Pro clean install/USB media/BitLocker decisions remain deferred by user; no automatic OS preparation or deployment

## v0.3z — release-candidate evidence audit (draft)
- [x] Introduce v2 local test evidence binding result to exact Git SHA and original main-ref before/after
- [x] Compute completed local log SHA256, mark evidence explicitly unauthenticated, refuse release/deployment claims
- [x] Build read-only offline auditor requiring expected Git SHA, matching log, complete six-check set and unchanged main ref
- [x] Detect missing, blocked, invalid, duplicate or tampered JSON fields and malformed/oversized evidence files
- [x] Add synthetic regression fixtures covering stale commits, forged hardware/deployment PASS, edited logs and link/path risks
- [x] Keep previous report v1 unsupported for latest branch acceptance, to prevent stale false positives
- [ ] Run the full latest branch AST / Python 3.11–3.13 / Fedora 43 Docker test gate on the user's Windows machine
- [ ] Independently audit the freshly produced v2 summary and log against the tested SHA
- [ ] Review stacked PRs explicitly; do NOT merge or deploy based solely on synthetic tests
- [ ] Real Fedora KVM/SELinux/sVirt/offline-guest/cold-recovery acceptance stays pending

## v0.4a — comprehensive draft PR stack readiness (current draft)
- [x] Independently inspect actual GitHub PRs #1–40: 39 open drafts unmerged; PR #30 does not exist
- [x] Confirm GitHub dependency shape is one linear stack from main, not 39 independent merges
- [x] Compare final prior PR #40 head with main: 454 commits ahead, 0 behind and 136 changed paths in the 2026-10-09 snapshot
- [x] Flag .github/workflows/verify.yml for manual workflow safety review before any eventual integration
- [x] Commit a versioned explicit 39-PR base/head snapshot with no fabricated PR #30
- [x] Implement opt-in no-fetch local Git ancestry checker, HEAD/remote origin guards, path-only diff risk labels and exclusive new JSON
- [x] Add synthetic contract tests for duplicate JSON, broken PR graph, changed main, diff-sensitive path review and no merge/deployment permission
- [ ] Fetch latest origin refs on the user's Windows clone, then execute local graph audit and cumulative test runner on exact branch SHA
- [ ] Independently refresh GitHub PR draft/review/merge status before any merge; offline Git cannot do this
- [ ] Review complete cumulative source and workflow diff, test evidence and Fedora hardware acceptance separately
- [ ] DO NOT integrate/merge/change Windows/USB/Fedora without specific user authorization

## v0.4b — original-main compatible stack audit and CI trigger review (draft)
- [x] Identify and fix prior defect: old auditor looked for unmerged config manifest in user's original main checkout
- [x] Read versioned 40-predecessor-PR snapshot from exact fetched candidate Git SHA, no checkout or tracked/untracked file overwrites
- [x] Extend ancestor chain to PR #41, while explicitly retaining PR #30 as NOT_FOUND, not invented
- [x] Validate manual workflow_dispatch and global contents:read from same pinned Git object; flag mutable action version tags
- [x] Strictly reject malformed/ambiguous UTF-8 diff names, duplicate manifest fields and unexpected workflow trigger/permission blocks
- [x] Commit additional offline unit fixtures for pinned manifest, auto-trigger injection, token privilege escalation, and diff decoding
- [ ] Run new Python unit/PowerShell syntax checks on Windows/Docker; current branch remains untested on actual workstation
- [ ] Independently inspect action mutable tags, workflow job contents and exact SHA references before ever enabling GitHub Actions
- [ ] Latest cumulative Docker/Fedora acceptance, all PR diff review, native Fedora KVM/sVirt and OS deployment remain HOLD

## v0.4c — single-entry Windows offline verification (draft)
- [x] Add PowerShell 5.1 launcher with PLAN ONLY default and explicit -FetchRefs, -AuditStack, -RunDockerGate modes
- [x] Require literal confirmation for Docker execution; image pulls and Fedora image builds remain separate opt-ins
- [x] Read audited scripts from an exact fetched Git object into an entirely new TEMP directory; no main checkout or ignored-file overwrite
- [x] Pin cumulative Docker test branch SHA and fail before worktree creation if ref changes; recheck SHA before tests
- [x] Extend PR ancestry snapshot through 42 existing drafts (41 predecessors, PR #30 absent) and point offline evidence auditor at latest candidate
- [x] Add preview/no-Git/no-write, consent, SHA pin and native PowerShell AST test contracts
- [ ] Run Windows PowerShell AST and cumulative Python/Fedora Docker tests for the newest candidate, using the user's 8GB host only with explicit approval
- [ ] Independently audit exact-SHA local test logs and verify current GitHub PR status before any user-approved integration
- [ ] Real Fedora SELinux/sVirt, guest isolation, backup restore and Windows 11 Pro installation remain separately held

## v0.4d — fail-closed offline test completeness (draft)
- [x] Fix detached-worktree regression wrongly assuming worktree add was always Git command #2
- [x] Require actual non-skipped Fedora GUI and native QEMU/libvirt cases, at least five each
- [x] Missing Linux Bash syntax validation under `--all` now fails
- [x] Require 60 discovered / 40 executed cases in each Python 3.11–3.13 container
- [x] Add mocked regression tests for zero tests, skipped tests and partial execution
- [x] Extend PR snapshot through #43 with #30 accurately absent
- [ ] Run real Windows PowerShell AST and cumulative Docker suites for the newest exact SHA
- [ ] Audit resulting private v2 logs and examine workflow actions before any separately approved merge
