# Phase 27 — read-only untrusted installer operation proposal

**Status: draft software review stage. No operating-system installation, physical disk writes, partitioning, EFI changes, USB writing or guest VM startup are implemented.**

## Purpose

Midnight Provisioner does **not** currently have an OS installer that can identify and export an authoritative proposed partition plan. Until such a source exists, it must not invent partition sizes, deletions, EFI targets or drive identities.

Phase27 allows a user to explicitly supply a small **UNTRUSTED** illustrative JSON operation list for risk review. The app labels it as incomplete/unverified even when it looks internally consistent. A future real installer must independently bind observations to physical hardware and produce a reviewed BEFORE/AFTER write plan.

## Installed features

- `midnight_provisioner/install_proposal_review.py` parses a bounded, strict schema `midnight-provisioner.untrusted-install-proposal.v1`.
- Accepted intents: `format_target` (freshly format and replace target data) and `coexist`. An opaque `target_ref` such as `target_a` is **not** a hardware identity.
- Device declarations use strictly opaque token IDs, a role (`target`/`other`) and an optional partition **count**. No actual disk paths, serial numbers, UUIDs, user files, partition layouts or commands are permitted.
- Proposed operation names: `create_partition`, `delete_partition`, `format_partition`, `resize_partition`, `write_bootloader`, `update_firmware_entry`. These are **data labels, not commands**. Unknown operations, undeclared device references, duplicate JSON keys, invalid identifiers and oversized lists are rejected.
- Preview explicitly shows **OTHER-DRIVE** and **BOOT** claims. Omitting an other-drive or boot operation is NOT evidence they won't be changed. The module cannot certify a complete install manifest, physical target, backup or consent.
- The Fedora PySide6 **System discovery** page has a user-invoked **Review local operation proposal JSON — NO WRITES** button. No file is read on application startup. A new hardware scan discards the previous preview.
- CLI reads an **explicit** absolute local JSON file, rejects linked paths and supports console-only JSON output. No file content is copied, modified, sent to any service or automatically uploaded.

## Example (demonstration only)

`examples/untrusted-install-proposal.json` is not an installer export, approval, or actual workstation layout. It intentionally claims a bootloader write on a second declared drive to demonstrate the warning.

```powershell
python -m midnight_provisioner proposal-review --file "$PWD/examples/untrusted-install-proposal.json"
python -m midnight_provisioner proposal-review --file "$PWD/examples/untrusted-install-proposal.json" --json
```

### Limits

Every report returns `HOLD_UNTRUSTED_PROPOSAL_NO_DISK_WRITES`, with **all** identity, completeness, source-trust, backup-certification, consent and install/write-authorization flags false. The user is responsible for backing up anything they want to keep before a future reformat; Midnight Provisioner does not back up or certify the data.

Reviewing the operation list does **not** prove that the actual Fedora installer intends those operations. An official future installation tool must provide genuine provenance, confirm hardware identity, enumerate ALL affected drives and EFI/boot changes, establish proper before/after partition details, and obtain new device-specific destructive consent.

## Tests

`tests/test_install_proposal_review.py`: 17 new pure Python tests for valid-but-untrusted proposals, other-drive and boot warnings, impossible backup attestation, malformed JSON, duplicate/undeclared operations, links/unsafe paths, bounded input, and CLI behavior. `tests/test_gui_smoke.py` adds a **27th** offscreen Qt test for explicit file selection, no install capability and clearing the preview on rescan.

Phase26 parent source `f41b1a4c736af59c376afaa4bf85a22de6c03709` has exact Windows/Fedora green operator evidence. **Phase27 has no verified operator results yet; it needs a new exact-head Windows and Fedora Qt/full-suite run.** All Midnight Provisioner PRs remain DRAFT and unmerged.
