# Nightglass Phase 24 — format-during-install backup responsibility

**Status: DRAFT. The current Nightglass software is not an operating-system or disk formatter.** This phase adds the user-facing disclosure and an explicit non-persistent acknowledgment in first-run discovery for a *future* system installer.

## Corrected installation assumption

The intended installation is **not** inherently onto a new, empty disk. The user can choose an existing physical target for an installation that will **format the selected drive or selected partitions**, replacing their contents with the new operating system. Previous contents are expected to be destroyed, whether or not partitions or files currently exist.

Nightglass **does not make, restore, assess completeness of, or verify the user's independent backups** as a prerequisite to presenting this disclosure. It must prominently warn the user that backups are their own responsibility *before* they consent to destructive installation. Do not claim that a disk is empty or that a backup exists. The old "only a blank drive needs no backup" explanation was the wrong workflow.

### Intended future OS installer display

> **DATA LOSS WARNING — THIS INSTALLATION WILL FORMAT THE SELECTED TARGET.**
>
> Formatting the target drive or selected partitions will delete existing files, installed operating systems, applications and potentially hidden data on the formatted area. This can be irreversible.
>
> **You are responsible for backing up anything you wish to keep BEFORE installation. Nightglass does not create or verify your backups; continuing assumes that you have already handled them yourself.**
>
> Carefully confirm the exact target device and the partitions that will be modified. If you have not backed up important data, or are uncertain which disk is targeted, **cancel installation**.

A checkbox conveys only `I understand that formatting can permanently delete existing data and that I must have backed up anything I want to keep myself.` It does **not** prove a successful backup, independently established empty media, a safe target identity, or actual installation authorization.

For installations alongside Windows, a separate warning must explain EFI/boot and partition modification risk, even when another installation target is used. This does not require a backup certificate from Nightglass; it requires an informed user and separately reviewed target layout.

### Built into Nightglass now

- `nightglass/install_disclosure.py` contains a single validated source for `undecided`, `format_target`, and `coexist` notices. All objects always report **false** for every install/target/disk-authorization field.
- The seventh **System discovery** page now offers **Freshly format selected target (delete its data)** rather than an allegedly blank drive. A prominent warning and unchecked acknowledgment appear on intent selection. Changing intent resets acknowledgment. The control authorizes **nothing** and does not persist or touch disk files.
- `nightglass discover` includes the user-managed-backup reminder. The read-only JSON contains `backup_responsibility=USER_MUST_BACK_UP_DATA_BEFORE_FORMAT`, `format_warning_required=true`, `format_warning_accepted=false`, `installer_creates_or_verifies_backups=false`. Legacy `blank_drive_independently_verified=false` remains for backward compatibility; this is **no longer an assumption that the chosen target must be blank**.
- 8 targeted pure Python safety tests plus an extended Qt GUI smoke case confirm warning coverage, no false authorizations, no selected target and reset of acknowledgment. Host hardware scan behavior remains unchanged.
- The existing Nightglass installer (`setup-nightglass.sh`) is **only an application installer run after Fedora KDE is installed**, not a disk formatter or OS installer. Phase24 does not implement the future OS installer; carrying the disclosure from the preview into the actual destructive confirmation screen is a **future required acceptance gate**.

### Still required before a physical install

A future installer must display **exact disk identity, capacity, bus, partitions and proposed changes**, must reject unknown or protected targets until reviewed, must obtain a separate specific destructive-operation confirmation and must never select disks on its own. Disk indexes/letters can change, so an advisory discovery snapshot is insufficient by itself.

Nightglass will not claim that files can be recovered after formatting. Formatting is not necessarily secure erasure of physical storage. Any change to existing Windows/EFI partitions, BitLocker/TPM or shared boot entries requires additional review. The user can cancel freely at any point before the first destructive write. No auto-formatting, OS installation, backup scanning, EFI changes, guest VM launch, USB write, or PR merge is authorized by this phase.

The Phase23 source remains preserved at its independently verified commit `755cae15699ccee2189a9c983a474564c9542dd2`. Phase24 must be tested independently on Windows and Fedora/Qt before software-verification claims are updated.
