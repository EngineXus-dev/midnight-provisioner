# Kali Studio and desktop appearance

Open **Kali Studio** in Midnight Provisioner's sidebar, or choose **Prepare new VM** on the Authorized Pentesting workspace. The studio provides a dedicated dark interface for the existing Kali planning, package, backup, recovery, and observation workflows. Generic analysis-VM preparation remains under **Prepare VM**.

## Choose a toolkit

The **Toolkits** tab presents all seven [curated profiles](KALI_TEMPLATES.md) plus Custom Kali. Each card shows its package count and suggested RAM/vCPU allocation. Select a card to see its package list, then choose **Configure selected toolkit**. The selected guest identity is shown above the tabs.

Choosing a profile only changes the planning form. Each curated profile is intended for a separate guest with its own disk. Resource limits still follow the host's machine profile.

## Follow the workflow

| Tab | Controls |
| --- | --- |
| Setup | Guest name, local ISO, publisher hash and resources; save/verify a private plan; preview both VM XML stages; check host/storage readiness; open virt-manager |
| Packages | Toolkit details, guest inventory instructions, local inventory comparison, saving a guest-reported version snapshot, and version drift |
| Recovery | Installed-guest audit, cold-backup binding, recovery-copy checks, registered recovery audit, and access to the existing backup tools |
| Runtime | Observations of an already-running benign recovery guest and its effective QEMU sVirt label |
| Appearance | Saved studio accents and instructions for optional guest desktop theming |

**Activity & results** shows the output from these actions. Existing checks and dialogs are shared with Prepare VM. Actual VM installation is performed separately in virt-manager; package inventory is collected inside the guest using the [standalone helper](KALI_GUEST_INVENTORY.md). The studio does not add a guest command or file-transfer channel.

## Studio accents

Choose **Appearance → Studio accent**:

- **Crimson eclipse:** red/pink accents on obsidian surfaces.
- **Ultraviolet:** violet accents on the same dark layout.
- **Venom:** green accents on the same dark layout.

The choice is stored in the existing private machine preferences as `kali_studio_theme`. Changing it preserves resource limits and update preferences. This affects the studio interface, not the Fedora desktop or a guest.

## Optional Kali Xfce desktop theme

The Appearance tab offers **Kali Dark** and **Kali Light**, with guest-side instructions. Kali's own graphical alternative is **Settings → Appearance → Style**, followed by **Settings → Window Manager → Style**; choose the corresponding installed Kali theme in both places. Icon themes can be selected separately in Appearance.

For a reversible two-setting change, manually transfer the reviewed `scripts/kali/kali-desktop-theme.py` into the intended guest through your independently chosen process. Inside an existing Kali **Xfce desktop session**, run it as the guest's regular user:

```bash
# Preview: changes nothing and requires no elevated privileges.
python3 kali-desktop-theme.py --theme Kali-Dark

# Apply the installed GTK and window-decoration theme after saving prior values.
python3 kali-desktop-theme.py --theme Kali-Dark --apply

# Alternative choice, if installed:
python3 kali-desktop-theme.py --theme Kali-Light --apply
```

Apply requires Kali Linux, a nonroot Xfce session, `xfconf-query`, and the selected theme already installed under `/usr/share/themes`. It does not install packages, replace wallpaper/icons, configure Qt applications, or change security/network settings. Other desktops are refused; use their native appearance settings.

Each apply saves a new private snapshot under `~/.config/midnight-provisioner/GuestThemeSnapshots`, respecting `$XDG_CONFIG_HOME`. You can provide `--snapshot /absolute/existing-folder/NEW-snapshot.json`; existing files are refused. The helper prints the exact path and undo command:

```bash
python3 kali-desktop-theme.py --undo /absolute/path/to/saved-snapshot.json
```

Undo restores both earlier values only while they still match what Apply set, so later manual theme edits are preserved. Snapshots remain available. If a partial setting change fails, the helper attempts rollback and reports when manual review is required. Theme behavior depends on the installed Kali release; the automated tests use a simulated Xfce backend rather than a live Kali VM.

## Sources

- [Kali Xfce appearance instructions](https://www.kali.org/docs/general-use/xfce-faq/)
- [Kali theme package source](https://gitlab.com/kalilinux/packages/kali-themes)
- [Xfconf query reference](https://docs.xfce.org/xfce/xfconf/xfconf-query)
- [Qt for Python](https://doc.qt.io/qtforpython-6/)
