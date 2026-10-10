# Nightglass — Windows 11 Pro: activate now OR later

> Privacy note: hardware and installation scenarios are illustrative. Discover actual device details independently; historical scenarios are not current authorization.

**User-requested option: ACTIVATION LATER (default), with during-setup
activation also supported.** This is a future clean-install decision,
not permission to install Windows today, and not a product-key collector.

## Two genuine Microsoft activation paths

### Option A — Activate later (DEFAULT)

1. At a future user-authorized boot of the **official, verified**
   Windows 11 installer, proceed through normal Microsoft setup.
2. **If the product-key page is shown**, choose **I don't have a product
   key**. If Windows detects a firmware-embedded OEM Home key and does
   not allow Pro selection, STOP and use a separately verified supported
   **Pro-only edition image** or genuine Microsoft-supported edition
   selection method. Do NOT let an OEM Home key silently select the
   wrong edition. Do NOT enter a bogus generic activation key or use
   TPM/Secure Boot/activation bypass tools.
3. Select **Windows 11 Pro**, not Home. Check the final intended edition
   carefully BEFORE confirming any clean-install disk operations.
4. Complete supported Windows setup. The machine may remain
   **unactivated** until you choose to activate it; Windows feature
   restrictions and personalization limitations may apply while
   unactivated. Do not claim activation or full entitlement at this
   stage.
5. Later, when ready, enter the private, valid Pro key in **Settings >
   System > Activation > Change product key**. Confirm Windows displays
   **Windows 11 Pro** and **Active**. Use Microsoft's Activation
   Troubleshooter or Microsoft support if the key is rejected.

Microsoft confirms product-key entry after install is supported:
https://support.microsoft.com/en-us/windows/activation/activate-windows

### Option B — Activate during installation

Enter your valid Windows 11 Pro product key **only in authentic
Microsoft Setup** if the installer asks for one. Follow Microsoft's
online activation flow and verify the edition and activation state
after installation. The image build, USB manifest, GitHub repo and
PowerShell customization scripts must NEVER require or record the
actual 25-character key.

Microsoft's clean-install instructions note that the visible key-skip
and edition-selection screens depend on licence/media conditions:
https://support.microsoft.com/en-us/windows/deployment/install-upgrade/reinstall-windows-with-the-installation-media

**Warning:** The current Windows was Windows 10 Home, and its OEM
firmware may contain a Home edition key. Owning a separate Pro key
does not automatically make a generic multi-edition Windows image
install Pro. A human must check the chosen Pro edition and valid
activation rights. An NTLite Pro-only image can make edition selection
explicit, subject to testing; keep an untouched, official Microsoft
recovery ISO and do not weaken boot signatures/security.

## Nightglass configuration

The local config `config/windows11-pro-custom.json` provides:

- `target.activation.default = "activate_later"`
- `options = ["activate_during_setup", "activate_later"]`
- `status = PLAN_ONLY_NOT_INSTALLED`

`scripts/windows/Invoke-Nightglass-Win11ProCustom.ps1` offers
`-ActivationTiming ActivateLater` (default) or
`-ActivationTiming DuringSetup`. This only displays future manual
steps; `ExportPlan` can record the timing in a **new** local JSON
report. No script reads a key, invokes activation or enters Windows
Setup.

For a platform-neutral, pure-Python media plan:

    python scripts/windows/Plan-Nightglass-InstallMedia.py

This default prints a JSON proposal with activation deferred. To
preview the alternative:

    python scripts/windows/Plan-Nightglass-InstallMedia.py --activation activate_during_setup

Both default previews do NOT inspect, hash, download or write any ISO,
USB, partition, firmware entry or personal files.

### Future only: safe ISO size preflight for the separate 16 GB USB

Once the actual official Windows 11 Pro ISO and Fedora KDE Live ISO
have been obtained and separately publisher-verified, run:

    python scripts/windows/Plan-Nightglass-InstallMedia.py --check-files --windows-iso "X:/official-Win11.iso" --fedora-iso "X:/official-Fedora.iso" --usable-usb-bytes 15000000000

**Those names and sizes are examples only, not actual paths/capacity.**
Use the **observed free/usable capacity** of the disposable USB stick,
not a guessed 16 GB marketing figure or the example backup-drive capacity backup drive.
This tool reads two regular local ISO files without mounting them,
and adds a conservative 1 GiB headroom in its *size-only* estimate.
It does not create a bootloader, image USB, run Setup, approve a disk
target or verify Secure Boot.

Optionally add `--sha256` to compute hashes by reading both files
without writing to them. SHA-256 checks a file's data, but **does
not alone prove it originated from Microsoft or Fedora**. Fedora's
signed ISO checksum and Microsoft's current download provenance
must be checked independently. The tool can write a NEW, exclusive
status-only JSON with `--report new-file.json`; it refuses to overwrite
an existing file and never stores Windows product keys.

**Hard stops:** missing backups/recovery key, unverified Pro edition,
USB does not fit ISO files plus reserve, unknown bootloader Secure
Boot behavior, or any attempt to select the example backup-drive capacity portable drive as
USB/OS target. Those remain actual installation BLOCKERS. The user
has explicitly deferred all operating-system and USB actions.

See WINDOWS11_CLEAN_INSTALL_STAGED.md,
WINDOWS11_PRO_32_POINT_PROFILE.md, ONE_USB_MULTIBOOT_PLAN.md and
OFFLINE_RELEASE_CANDIDATE_GATE.md.

## Backup verification before activating or installing Windows

The optional [backup integrity preflight](BACKUP_INTEGRITY_PREFLIGHT.md)
is completely separate from Windows activation. It never asks for a
product key, and `Verify` checks a copied directory's regular-file
hashes without copying or changing it. A successful comparison is
not permission to wipe Windows or install Fedora. The Pro key can
still be used later in Windows Settings (default), as preferred.
