# Windows 11 Pro — requested privacy, AI and developer profile

> Privacy note: hardware and installation scenarios are illustrative. Discover actual device details independently; historical scenarios are not current authorization.

**Configuration status: STAGED ONLY — nothing installed, downloaded or
applied to Windows.** the selected edition requires a valid **Pro activation key**.
Never store or print the key in this project; verify genuine Pro
activation during/after the future clean install. This supersedes the
earlier Home-default plan. Use the official Windows 11 26H2 x64 ISO
current as of 2026-10-09, or re-check the then-current release when
actually building later.

The user is not ready to install. The only scheduled action is NONE.
No USB formatting, data backup copying, third-party debloat execution,
OneDrive uninstall, registry edits, edition changes, Windows 11 setup,
WSL/Sandbox activation or Fedora installation has occurred.

## Source review: supplied scripts and upstream controls

The user supplied `Get.ps1` (~9 KiB) and a `winutil-main.zip`
(~2.7 MiB compressed, 417 archive entries). Their role differs:

- `Get.ps1` is **a Win11Debloat bootstrapper**, NOT the actual
  `Win11Debloat.ps1`. It queries GitHub Releases and downloads ZIP
  content at runtime, clears/replaces a temporary program directory,
  and launches the downloaded PowerShell with elevation. A quick
  `-WhatIf` assumption would NOT make the downloader passive. The
  Nightglass helper rejects it as a candidate for later ApplyCore.
- The supplied WinUtil ZIP contains source code, app/tweak/feature
  configuration and automation. Its configuration includes choices
  that can remove Windows widgets, disable hibernation, change
  Windows services and even alter Store database ACLs. Do **not**
  run its default Standard/Advanced preset on top of Win11Debloat.
  WinUtil's presence in the archive does NOT establish that any of
  those side effects are appropriate to this machine.
- The **current actual Win11Debloat.ps1** must be downloaded and
  independently reviewed later, the script version and SHA256 must
  be pinned, and individual flags validated against that version.
  No project code fetches/executes the uploaded downloader.

Official/vendor references:
- Microsoft official ISO: https://www.microsoft.com/en-us/software-download/windows11
- Microsoft Windows release health: https://learn.microsoft.com/en-us/windows/release-health/status-windows-11-26H2
- Win11Debloat CLI: https://github.com/Raphire/Win11Debloat/wiki/Command-line-Interface
- Win11Debloat backup/undo: https://github.com/Raphire/Win11Debloat/wiki/Reverting-Changes
- Microsoft Windows Sandbox: https://learn.microsoft.com/en-us/windows/security/application-security/application-isolation/windows-sandbox/windows-sandbox-install
- Microsoft WSL: https://learn.microsoft.com/en-us/windows/wsl/install
- Windows Pro optional diagnostic data: https://learn.microsoft.com/en-us/windows/privacy/configure-windows-diagnostic-data-in-your-organization

## Your 32 preferences + three extra application/AI requests

**Core candidate** = proposed for later, *after* a clean,
licensed Windows 11 Pro install and independently tested backup.
It is not applied today. **Separate** means it must never be mixed
into an automatic "just do everything" pass.

| # | Requested change | Proposed phase | Important behavior or limitation |
|---:|---|---|---|
| 1 | Reduce optional telemetry, history, app launch tracking, ad targeting | Manual verification | Required Windows Pro diagnostics cannot be fully eliminated; activity tracking, advertising ID and consent settings must be verified individually. |
| 2 | Disable lock-screen and Edge suggestions, tips and advertising | Core candidate | Edge browser version/policy support varies. |
| 3 | Disable location services, app access and Find My Device tracking | Core + privacy review | Disables location-dependent features and device-finding. |
| 4 | Hide Microsoft 365 ads in Settings Home (do not remove entire Home default) | Core candidate | Hide the entire Home page only as a separately selected preference. |
| 5 | Prevent WSAIFabricSvc automatic start | Core candidate | Service may be absent; no service deletion. |
| 6 | Disable Edge, Paint, Notepad AI; Chrome AI requires separately verified Chrome policy | Core + browser review | Chrome browser version-managed settings/manual review; do not write unsupported policies. |
| 7 | Disable Windows Drag Tray file sharing | Core candidate | — |
| 8 | Use classic Windows 10 context menu | Core candidate | Shell update can revert this; avoid patching Explorer binaries. |
| 9 | Disable Sticky Keys activation shortcut | Core candidate | Accessibility shortcut changes; Sticky Keys feature remains available manually. |
| 10 | Disable Storage Sense automatic cleanup | Core candidate | Keep manual cleanup; verify disk headroom. |
| 11 | Disable Windows Fast Startup | Core candidate | Needed to avoid hibernated Windows NTFS when dual booting; separate from turning off full hibernation. |
| 12 | Disable automatic device encryption of new installation, keep manual BitLocker possible | Separate security approval | Security tradeoff. Does NOT decrypt existing volumes; verify actual encryption and recovery keys before any change. |
| 13 | Disable Modern Standby network connectivity | Core candidate | Only on supported S0 Modern Standby hardware, may affect background connectivity. |
| 14 | Do not receive preview/nonsecurity updates as soon as available | Core candidate | Keep monthly security patches, Defender updates and servicing enabled. |
| 15 | Prevent update-triggered restart while a user is signed in | Core candidate | Not a total restart prevention; still schedule reboots for security patches. |
| 16 | Disable Delivery Optimization peer-to-peer update distribution | Core candidate | Keep direct Windows Update downloads working. |
| 17 | Prevent automatic device companion app download | Core candidate | Must preserve normal driver installation. |
| 18 | Enable dark mode for apps and system | Core candidate | — |
| 19 | Disable transparency, animations and unnecessary effects | Core candidate | Some visual effects and accessibility/animation controls require manual verification. |
| 20 | Disable desktop/lock screen Spotlight background | Core candidate | Desktop and lock screen settings can be independent. |
| 21 | Clear pinned Start apps, hide recommendations, review All Apps layout | Separate layout approval | ClearStart changes custom pins; explicit optional opt-in only; UI may vary by Windows 26H2. |
| 22 | Disable Start menu Phone Link integration | Core candidate | Separate uninstall of Phone Link app optional. |
| 23 | Disable Bing web/Copilot search and Store recommendations | Core candidate | Avoid filesystem-permission hacks on Store databases. |
| 24 | Enable End Task on taskbar right-click | Core candidate | Can force-close unsaved apps. |
| 25 | Show extensions for known file types | Core candidate | Security-positive. |
| 26 | Show hidden files/folders/drives | Core candidate | Do not disable hiding protected OS files by default. |
| 27 | Hide Home, Gallery and OneDrive in Explorer pane | Core candidate | Does not remove personal files. |
| 28 | Disable window snapping | Core candidate | May reduce workflow convenience; leave as requested. |
| 29 | Enable Windows Sandbox | Separate admin/restart | Windows 11 Pro and AMD virtualization; 8GB class host: avoid concurrent VM use; admin and restart required. |
| 30 | Enable WSL and Virtual Machine Platform | Separate admin/restart | Admin, optional reboot, WSL distro installation separate; preserve Docker Desktop. |
| 31 | Disable Xbox Game Bar recording/integration and uninstall app optionally | Separate app removal | Game DVR and Game Bar disabled by default profile; app removal separate review. |
| 32 | Disable Brave browser AI/crypto/news bloat | Separate browser review | Apply only if Brave installed; verify Chrome/Brave policies against browser release. |
| 33 | Remove OneDrive app and hide Explorer integration | Separate app removal | Unlink and verify cloud files are locally backed up before removal; do not delete files; no automatic app uninstall in core. |
| 34 | Remove optional promotional apps and Widgets | Separate app removal | Core disables Widgets surface; optional Appx removals require explicit per-app selection and separate restore validation. |
| 35 | Disable Copilot, Recall and Click to Do | Core candidate | Recall/Click-to-Do require Copilot+ hardware and may be absent on target CPU (verify compatibility); prefer supported policies; no component store surgery. |

### Additional guardrails and unsupported absolutes

- **Telemetry cannot be zero guaranteed** on ordinary Windows 11 Pro.
  Minimize optional diagnostic/ads, disable activity collection and
  search personalization where supported; allow required diagnostics,
  security update and Defender traffic. Stop if a proposed "privacy"
  preset breaks Windows Update, firewall or SmartScreen.
- **Recall/Click to Do** are principally Copilot+ PC features and may
  be **absent** on the detected RAM capacity target CPU (verify compatibility). No reason to remove
  component-store packages or interfere with system servicing to
  suppress a nonexistent feature.
- **Encryption:** requested prohibition of *future automatic* device
  encryption is a security tradeoff, not an instruction to decrypt
  existing volumes. Decrypting existing BitLocker is **not in scope**.
  Review Windows 11 activation/TPM/backup recovery keys before this
  independent security decision.
- **Windows Sandbox** on Windows 11 Pro can require **8 GiB RAM
  recommended** and virtualization support; this laptop only reports
  detected RAM capacity usable. Enable only after a separate admin action, reboot
  approval and resource checks; **do not run an additional VM at
  the same time**. Sandbox itself is not a replacement for Nightglass
  high-risk offline malware VM isolation, and may have networking.
- **WSL2** is useful for local dev and Docker Desktop. Preserve
  Windows virtualization features in the NTLite image; enable WSL2
  and choose any distro **after** the Windows 11 install, separately
  from sandbox enablement, with admin/restart approval.
- **Fast Startup** should be OFF before read/write interaction with
  a Windows NTFS partition from Fedora; do NOT automatically turn
  off all laptop hibernation support.
- **Remove OneDrive** after checking whether any files are
  cloud-only; unlink sync and verify external copies before
  uninstalling via Windows Settings/approved local package procedure.
  Merely hiding the navigation entry is reversible but **not** removal.
- **Remove Xbox/Game Bar:** disabling recording and overlay is in
  core candidate; optional app package removal is separate.
- **Settings Microsoft 365 ads:** prefer hide promos without
  deleting the entire Settings Home; hide the whole page only after
  separate UI acceptance.
- **Start pins/all-apps:** disable recommendations where supported,
  but do not clear personal pins in core. Windows 26H2 layout
  differences can make legacy policy keys ineffective.
- **Chrome/Brave:** treat browser-specific AI, Crypto and News
  options as independent browser version/policy decisions.
  Do not assume Edge policies apply to Chrome.
- **Updates:** Disable "Get latest as soon as available" toggle
  for optional preview rollouts and peer-to-peer Delivery Optimization;
  keep cumulative/security updates, servicing, Defender definitions
  and controlled restart windows. No indefinite block of updates.
- **File Explorer hidden items:** show file extensions and hidden
  files, but preserve hiding protected operating-system files.
- **Microsoft Store and WebView2 stay installed** because developer
  tools and Windows components depend on them.

## How to review safely now, without touching Windows

On **this branch's isolated files**, use the planner on *any Windows
PowerShell 5.1 session* only after its native parser passes:

    powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File scripts/Invoke-Nightglass-Win11ProCustom.ps1 -Mode Preview

Default `-Mode Preview` reads only the JSON in
`config/windows11-pro-custom.json`; it neither calls Win11Debloat,
the Get.ps1 bootstrapper nor WinUtil. It does not write to registry,
OS services, apps, startup or USB disks.

For an optional **new private plan-only JSON** in an existing directory:

    powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File scripts/Invoke-Nightglass-Win11ProCustom.ps1 -Mode ExportPlan -PlanPath "<new-plan-path>.json"

Exclusive `CreateNew` refuses an existing destination. This reports
which flags are candidates only; no app removal, automatic encryption
change, service/feature installation, Windows setup or USB writer.

### ApplyCore — intentionally NOT for current Windows 10

An optional `-Mode ApplyCore` is **future-only**. It fails closed on
anything other than an installed Windows 11 Pro machine; requires
separate administrator launch, a verified backup flag, exact literal
consent, a locally reviewed and SHA256-matched
`Win11Debloat.ps1`, and PS AST validation of every selected flag.
It passes only the hardcoded core allowlist (not all JSON switches)
with Win11Debloat's restore point request. Do not assume third-party
uninstall actions are fully reversible, or that a restore point
replaces a full backup. **Run first on disposable Windows 11 Pro VM
after independent parser/unit acceptance.** Native ApplyCore has not
been executed.

The helper does **not** uninstall OneDrive or gaming apps; change
BitLocker/TPM; enable Sandbox/WSL; reset Start pins; run Chrome
policies; remove Store/WebView2; disable Windows Update; or copy
user files. Those remain separate manual consent gates.

## Windows Pro NTLite edition change

Your Pro key changes the earlier edition decision: retain a genuine
Windows 11 **Pro** index when trimming the Windows 11 26H2 ISO
(and keep an untouched Microsoft ISO for recovery). Before relying
on an edited image, verify exact edition/index, architecture and
signature/boot behavior. Do not place product keys in unattended
setup files, GitHub or the multiboot menu. If activation fails, use
official supported activation/recovery instead of a bypass.

**User storage protection:** Internal Windows measured system-disk capacity GPT disk was
Disk 0 on the last observed Windows 10 installation. The example backup-drive capacity portable
drive was Disk 1 and must NEVER be a media-writer or OS installation
target. The separate 16 GB USB is plausible for the two ISOs **only
after size/usable-space review**; installation and USB preparation
are NOT authorized or scheduled.

**Security review status:** source and static checks only.
Windows 11 Pro has not been installed, native Windows 11 AST
parsing/Win11Debloat execution/Undo integration has not been tested.
