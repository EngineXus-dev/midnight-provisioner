# Midnight Provisioner documentation

## Installation and host setup

- [Install Midnight Provisioner on Fedora](../scripts/install/README.md)
- [Build Fedora and Windows installer media](../scripts/iso/README.md)
- [Standalone Windows 11 installation and customization](../README.md#standalone-windows-11-installation-and-customization)
- [Shared-disk and separate-drive dual boot](../README.md#optional-windows-11-and-fedora-dual-boot)
- [Script directory](../scripts/README.md)
- [Disk encryption](DISK_ENCRYPTION.md)
- [Fedora host preflight](FEDORA_HOST_PREFLIGHT.md)
- [Host security posture](HOST_POSTURE.md)
- [Resource monitoring](RESOURCE_MONITOR.md)

## Workspaces and virtual machines

- [Security model and workspace policies](SECURITY_MODEL.md)
- [Prepare a guest from a local ISO](VM_PREPARATION.md)
- [Registered guest audits](REGISTERED_GUEST_AUDIT.md)
- [Running guest sVirt observations](RUNTIME_SVIRT_OBSERVATION.md)

## Kali Linux profiles and lifecycle checks

- [Complete Kali workflow in the main README](../README.md#kali-linux-workspaces-and-toolkits)
- [Seven curated Kali workspace templates](KALI_TEMPLATES.md)
- [Private setup plans and version snapshots](KALI_SETUP_MANIFESTS.md)
- [Manual guest software inventory](KALI_GUEST_INVENTORY.md)
- [Package version drift](KALI_VERSION_DRIFT.md)
- [Host, ISO, and storage readiness](KALI_TEMPLATE_PREFLIGHT.md)
- [Registered template audit](KALI_REGISTERED_TEMPLATES.md)
- [Independent cold baselines](KALI_COLD_BASELINES.md)
- [Backup-to-recovery copy binding](KALI_RECOVERY_LINK.md)
- [Registered recovery handoff](KALI_REGISTERED_RECOVERY.md)
- [Already-running recovery observations](KALI_RUNNING_OBSERVATION.md)
- [Effective QEMU process sVirt labels](KALI_QEMU_PROCESS_LABEL.md)

## Discovery and installation review

- [Read-only system discovery](PHASE23_FIRST_RUN_DISCOVERY.md)
- [Formatting warning and backup responsibility](PHASE24_FORMAT_WARNING.md)
- [Target and encryption preview](PHASE25_TARGET_PREVIEW.md)
- [Partition and EFI impact review](PHASE26_INSTALL_CHANGE_REVIEW.md)
- [Explicit untrusted operation-list review](PHASE27_UNTRUSTED_PROPOSAL_REVIEW.md)

## Windows installation, customization, and readiness

- [Windows installation media and optional AtlasOS](../scripts/iso/Windows11/README.md)
- [Single-edition image preparation](WINDOWS11_LITE_IMAGE_PROFILE.md)
- [Windows customization profile and supported core subset](WINDOWS11_PRO_32_POINT_PROFILE.md)
- [Activation choices and media-capacity planning](WINDOWS11_PRO_ACTIVATE_LATER.md)
- [Windows host gate](PHASE18_WINDOWS_HOST_GATE.md)
- [Preinstall observation review](PHASE19_PREINSTALL_BLOCKERS.md)
- [Recovery posture](PHASE20_WINDOWS_RECOVERY_POSTURE.md)
- [WinRE triage](PHASE21_WINRE_TRIAGE.md)
- [Read-only recovery and backup acceptance](PHASE22_RECOVERY_BACKUP_ACCEPTANCE.md)

## Backups and recovery

- [Cold VM backups](COLD_BACKUP.md)
- [Stage a recovery copy](RECOVERY_STAGING.md)
- [Inspect recovery and backup acceptance](PHASE22_RECOVERY_BACKUP_ACCEPTANCE.md)
- [Review a staged-to-registered recovery handoff](RECOVERY_HANDOFF.md)
- [Fedora acceptance checks](FEDORA_ACCEPTANCE.md)
- [Backup integrity preflight](BACKUP_INTEGRITY_PREFLIGHT.md)
- [Verify a multi-source backup set](MULTI_SOURCE_BACKUP_READINESS.md)

## Development and verification

- [Contribution guide](../CONTRIBUTING.md)
- [Security reporting](../SECURITY.md)
- [Native virtualization-tool fixtures](NATIVE_TOOLS_TESTING.md)
- [Fedora tests in Docker](FEDORA_DOCKER_VERIFICATION.md)
- [Python compatibility checks](PYTHON_COMPATIBILITY_MATRIX.md)
- [Offline release verification](OFFLINE_RELEASE_CANDIDATE_GATE.md)
- [Release evidence audit](RELEASE_EVIDENCE_AUDIT.md)

The other files in this directory include design notes, historical implementation records, and maintainer runbooks. Instructions tied to a specific branch, machine, or past deployment decision should be read in that context.
