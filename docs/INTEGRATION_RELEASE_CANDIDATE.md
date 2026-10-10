# Nightglass Cumulative Source Release Candidate

**Purpose:** one reproducible, testable Fedora KDE Nightglass application SOURCE baseline for the next engineer. Not a Windows executable, finished Fedora OS installer, boot image, hardened appliance, or production release.

## GitHub integration inventory

- GitHub main observed at SHA 7ed599e9724551fffc203203a1ab4173bb7510c9.
- 64 open DRAFT PRs, 63 in one continuous chain: #1–29, #31–52, #54–65.
- PR #30 does not exist. PR #53 diverges off #52 and is explicitly *not* part of the chain. Its Windows test fixture, secret-path and OS-disk assertion fixes already have mainline equivalents. Preserve #53 and its report; do not blindly merge its outdated candidate-reference updates.
- Verified predecessor #65: Windows Python 3.12 (65 passed, two expected symlink skips) and Fedora 43 cached Docker (681 full-suite cases, 646 pass, 35 expected skips), 27 actual offscreen Qt tests, six native QEMU/libvirt fixtures. These results apply ONLY to exact SHA 2902acbeb1402cf1fc18d0374aad4951bd8d60a2, not automatically to later integration commits.

## What this source build includes

Python CLI, PySide6 Fedora GUI, curated separate Kali VM template profiles, libvirt/KVM and Distrobox control modules, read-only Windows/dual-boot planning, safe storage recognition, non-authorizing installation-impact/proposal reviews, tests, and documentation.

The Fedora application installer is scripts/setup-nightglass.sh. It runs on an **already-installed Fedora** user account and installs dependencies into the user's Nightglass-specific environment only after explicit operator action. It is NOT a physical operating system installer or USB boot medium.

The package creator scripts/Package-Nightglass-ReleaseCandidate.ps1:
1. Requires an explicitly pinned complete Git SHA and checks the source remote.
2. Rejects tracked secret, environment, OS-image and VM-image filenames.
3. Uses Git archive to include **tracked files at exactly that SHA**; does not copy user secrets, ignored files, virtual environments, backups, external disks or private untracked files.
4. Records the ZIP SHA-256 and original main SHA in RELEASE-MANIFEST.json.
5. Writes only new release files into Documents/Nightglass-ReleaseCandidates, outside the checkout. No git pull/merge/reset/clean, installer, device formatting, reboot, VM action or EFI changes.

This is a **source package**, not a precompiled desktop binary and not proof of a tested install on physical Fedora hardware.

## Merge and release gates

1. Audit all 63 PR edges, exact SHAs, original main SHA, and #53 divergent fork via scripts/Review-Nightglass-Integration.py with the v2 pinned JSON snapshot. The default audit does not execute git commands.
2. Inspect the cumulative main-to-RC source diff and scan for secrets, binaries, unresolved migration docs and unsafe config defaults.
3. Verify Windows PowerShell AST, Windows Python synthetic suite including integration-only tests, Fedora 43 full Python suite, real offscreen Qt GUI and native libvirt/QEMU fixtures at the **same exact RC SHA**.
4. Review PR53 historical investigation and do not reintroduce its obsolete release-gate candidate pointer; keep every original draft PR branch intact.
5. Obtain **explicit owner approval before any PR merge or mutation of main**. Prefer a single cumulative PR merge after exact-source verification; do not merge the 63 individual PRs afterwards and accidentally replay the changes. Keep an immutable record of previous PR identities.

No installer/USB/EFI/partition, Windows/Fedora OS installation, hardware VM launch, password/key change, backup restore or production deployment is part of this source candidate.

## Remaining high-risk engineering work

Physical Fedora KDE boot and KVM/SELinux/sVirt enforcement, actual two-OS boot/recovery, signed and authenticated installation media, a real installer with exact per-disk before/after changes and separate destructive consent, verified restoration and VM isolation, end-to-end GUI on native Fedora, customer-ready distribution and release-security review. The user's independent backups are their responsibility before any future formatting; Nightglass does not create or verify them.

The next advanced AI should take this pinned integration branch and all test evidence as the **software baseline**, rather than mistake the planning previews for an installed operating system.
