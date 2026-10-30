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
- [Kali workspace templates](KALI_TEMPLATES.md)
- [Kali setup manifests](KALI_SETUP_MANIFESTS.md)
- [Guest software inventory](KALI_GUEST_INVENTORY.md)
- [Template readiness checks](KALI_TEMPLATE_PREFLIGHT.md)
- [Registered guest audits](REGISTERED_GUEST_AUDIT.md)

## Backups and recovery

- [Cold VM backups](COLD_BACKUP.md)
- [Stage a recovery copy](RECOVERY_STAGING.md)
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
