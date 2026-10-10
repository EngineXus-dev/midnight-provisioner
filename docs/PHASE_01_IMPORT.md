# Nightglass Phase 1 import

The full v0.1 source archive is distributed with this project's release package and is not yet fully synchronized to this GitHub branch.

To import the reviewed source safely:
1. Extract `Nightglass-Workspaces-v0.1.0.zip` to a separate local folder.
2. In that folder, run the updated `scripts/release/Push-ExistingRepo.ps1` from the latest Nightglass package.
3. The script clones this specific repository into a temporary directory, switches to `feat/nightglass-phase-01`, and stages only Nightglass project paths.
4. Inspect the changes and confirm the upload. It does not force-push, overwrite your original extraction, or touch the Windows installation.

Security limits: VM XML policy checks are best-effort and are not a Qubes-equivalent security boundary.
