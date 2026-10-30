# Scripts

| Folder | Use it for |
|---|---|
| [`install/`](install/README.md) | **Start here.** Installing and setting up Midnight Provisioner on Fedora |
| [`iso/`](iso/README.md) | Building the Windows 11 + Fedora dual-boot installer ISO, VM testing, USB |
| `windows/` | Read-only Windows checks before a dual boot, install-media planning, optional Windows 11 preference tweaks |
| `backup/` | Inspecting and verifying backups, recovery smoke checks |
| `kali/` | Guest-side package inventory helper and optional Kali Xfce Dark/Light theme helper with preview and undo; see [Kali Studio](../docs/KALI_STUDIO.md) and the [complete workflow](../README.md#kali-linux-workspaces-and-toolkits) |
| `testing/` | Test runners and verification (local, Fedora Docker, GUI smoke, release gate) |
| `release/` | Maintainer tools: PR-stack audits, release packaging, publishing the repo |

Scripts in `windows/` that can change settings default to a preview and require a typed confirmation.
