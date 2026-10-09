# Nightglass — future-proofing and release verification

**Status:** Engineering safeguards and planned gates, not release approval. Nightglass remains independent of EngineXus/YenEngine.

## Runtime and platform compatibility

- **Windows:** PowerShell 5.1 is the baseline for .ps1 scripts. Its automatic variables are case-insensitive: assigning to $home is the same as overwriting read-only $HOME. Run the lexical checker with python scripts/check_powershell_guardrails.py, and parse all PowerShell sources using the native Windows parser. Use descriptive locals such as $testHome instead of automatic-variable names.
- **Python:** Pin supported interpreter versions and validate all of them separately. Do not silently install or upgrade interpreters or libraries. A passing Python 3.12 run does not prove Python 3.13+ compatibility.
- **Qt:** Real offscreen PySide6 is an independent gate. Missing Qt, empty test discovery, every test skipped, or a test timeout must not count as a pass. The GUI test must never start a real VM.
- **Fedora:** POSIX private file modes, native QEMU/libvirt, SELinux/sVirt confinement, symlink edge cases and cold restore must be tested on Linux. Windows os.fchmod mocks are NOT Fedora acceptance.
- **Low-memory:** Resource checks must work with 8 GiB RAM, CPU fallback and missing/inaccessible KVM. Reject unsupported isolation claims.

## Non-negotiable security boundaries

1. Offline malware-analysis VMs must remain disconnected and reject shared mounts, device passthrough and forwarding. Kali templates should install selected tooling only; do not install every tool by default.
2. Before handoff/recovery, validate live and persistent guest XML, managed-save XML, disk provenance, aliases and hardlinks, memory caps and shutdown state. XML checks are not proof of packet-level denial or SELinux confinement.
3. Security tests skipped on Windows must remain NOT VERIFIED and require native Linux acceptance. Never weaken production Linux file-permission checks to pass Windows mocks.
4. Do not merge into main, reset/clean the user checkout, overwrite .env/.venv/untracked files, operate on USB/backup disks, install an OS, or start VMs during automated regression verification.
5. Changes to persisted plans/reports require schema versioning, unknown-version rejection, tested migrations and recovery paths.

## Evidence and release gates

- Run the portable suite at one exact pinned commit in detached worktrees, recording test counts and skips separately.
- Test Qt offscreen and native Fedora tooling independently; real packet filtering, SELinux and cold restore require explicit authorization.
- Persist final evidence under Documents/Nightglass-Verification-Results in unique session folders with source ZIP, extracted logs, Git commit, summary, and SHA-256 inventory. Preserve failures; never overwrite sessions.
- Hash inventories are not signed attestations. Validate the archive script on Windows before relying on it for compliance or release verification.
- Treat evidence archive failures as failures and keep the untouched ZIP for recovery.
- On every Windows/Fedora/Python/Qt/QEMU/libvirt upgrade, record version differences, review security advisories, run syntax/automatic-variable guards, repeat synthetic tests and native integration gates.
- Publishing, installing or altering physical disks always requires separate explicit permission.

## Backlog — not yet implemented

Reproducible dependency locks and SBOM; cryptographically signed builds and source-image provenance; automatic schema migrations; exhaustive Windows/Fedora version matrix; continuous evidence validation; network packet-denial proof; real sVirt/SELinux acceptance; cold-restore drills; installer and rollback tests.

Do not call planned backlog functionality implemented until supporting executable tests exist. Both PR #54 and its stacked portability hardening branch remain draft and unmerged.
