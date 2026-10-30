#requires -Version 5.1
<#
.SYNOPSIS
  Midnight Provisioner: full Fedora/Linux synthetic, GUI and native fixture tests
  inside an isolated Docker container, on Windows 10/11.
.DESCRIPTION
  Fetches ONLY the integration branch, creates a NEW detached sibling git
  worktree, builds a Fedora 43 test image without copying host files, and
  runs the full Linux test suite WITHOUT network, privileges or VM devices.
  No changes to main, .env, .venv, other files or existing worktrees.
  First image build needs network for official Fedora RPMs. Runtime does not.
.EXAMPLE
  powershell -NoProfile -ExecutionPolicy Bypass -File .\Run-Midnight-Provisioner-Fedora-Checks.ps1
.EXAMPLE
  powershell -NoProfile -ExecutionPolicy Bypass -File .\Run-Midnight-Provisioner-Fedora-Checks.ps1 -RepoPath "C:\path\to\midnight-provisioner"
#>
[CmdletBinding()]
param(
    [string]$RepoPath = "",
    [switch]$Focused,
    [switch]$ForceImageBuild
)
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$branch = "chore/offline-integration-verification"
$success = $false
$transcriptStarted = $false
$buildDir = $null
$logPath = $null

function Assert-ExitCode {
    param([string]$Operation)
    if ($LASTEXITCODE -ne 0) {
        throw "$Operation failed with exit code $LASTEXITCODE. Your original checkout was not modified."
    }
}

function Resolve-MidnightProvisionerRepo {
    param([string]$ExplicitPath)
    # Windows PowerShell 5.1 turns redirected native stderr (e.g. git's "not a git
    # repository") into a terminating error under 'Stop'; probes must continue instead.
    # Function-local: the caller keeps 'Stop'.
    $ErrorActionPreference = 'Continue'
    $candidates = @()
    if ($ExplicitPath.Trim()) {
        $candidates += $ExplicitPath
    } else {
        $candidates += (Get-Location).Path
        $candidates += (Join-Path ([Environment]::GetFolderPath("MyDocuments")) "midnight-provisioner")
        $candidates += (Join-Path $PSScriptRoot "midnight-provisioner")
    }
    foreach ($candidate in $candidates) {
        if (-not (Test-Path -LiteralPath $candidate -PathType Container)) { continue }
        $top = (& git -C $candidate rev-parse --show-toplevel 2>$null | Out-String).Trim()
        if ($LASTEXITCODE -ne 0 -or -not $top) { continue }
        $url = (& git -C $top remote get-url origin 2>$null | Out-String).Trim()
        if ($LASTEXITCODE -ne 0) { continue }
        if ($url -match '(?i)(^|[:/])EngineXus-dev/midnight-provisioner(\.git)?$') {
            return (Resolve-Path -LiteralPath $top).Path
        }
    }
    throw "Could not find the Midnight Provisioner checkout with the expected GitHub origin. Run from that checkout or specify -RepoPath. No files changed."
}

try {
    Write-Host "Midnight Provisioner - FEDORA DOCKER INTEGRATION TEST" -ForegroundColor Cyan
    Write-Host "Tests are offline, nonroot, without /dev/kvm, and source checkout is read-only."
    Write-Host "Docker image BUILD may download Fedora packages; runtime network is disabled."
    Write-Host "NO merges, resets, git clean, force-push, GitHub Actions, VM boot or .env/.venv overwrite."

    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        throw "Git was not found on PATH."
    }
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        throw "Docker CLI missing. Install/start Docker Desktop with Linux containers enabled before running."
    }

    $root = Resolve-MidnightProvisionerRepo -ExplicitPath $RepoPath
    $parentDir = Split-Path -Parent $root
    $token = [guid]::NewGuid().ToString("N").Substring(0, 8)
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $checkout = Join-Path $parentDir ("Midnight-Provisioner-Fedora-Check-" + $stamp + "-" + $token)
    $logPath = Join-Path $parentDir ("Midnight-Provisioner-Fedora-Check-" + $stamp + "-" + $token + "-results.txt")
    if ((Test-Path -LiteralPath $checkout) -or (Test-Path -LiteralPath $logPath)) {
        throw "Refusing to reuse an existing checkout or report path."
    }
    Start-Transcript -LiteralPath $logPath -NoClobber | Out-Null
    $transcriptStarted = $true

    Write-Host ""
    Write-Host "[1/6] Checking Docker Desktop Linux engine" -ForegroundColor Yellow
    # 'Continue' so a stopped Docker Desktop reaches Assert-ExitCode's clear message
    # instead of a raw PowerShell 5.1 NativeCommandError.
    $ErrorActionPreference = 'Continue'
    try { $engine = (& docker info --format '{{.OSType}}' 2>&1 | Out-String).Trim() }
    finally { $ErrorActionPreference = 'Stop' }
    Assert-ExitCode -Operation "Docker daemon connectivity check"
    if ($engine -ne "linux") {
        throw "Docker Desktop is using $engine containers. Switch Docker Desktop to Linux containers."
    }
    Write-Host "Docker Linux engine is accessible."

    Write-Host ""
    Write-Host "[2/6] Fetching ONLY the dedicated Midnight Provisioner integration branch" -ForegroundColor Yellow
    Write-Host "Original checkout: $root"
    & git -C $root fetch --no-tags origin ("refs/heads/{0}:refs/remotes/origin/{0}" -f $branch)
    Assert-ExitCode -Operation "Git fetch"
    & git -C $root worktree add --detach $checkout ("refs/remotes/origin/" + $branch)
    Assert-ExitCode -Operation "Create separate detached worktree"
    $head = (& git -C $checkout rev-parse HEAD | Out-String).Trim()
    Assert-ExitCode -Operation "Read integration commit"
    Write-Host "New checkout: $checkout"
    Write-Host "Integration commit: $head"

    $containerfile = Join-Path $checkout "docker\Containerfile.fedora-verification"
    if (-not (Test-Path -LiteralPath $containerfile -PathType Leaf)) {
        throw "Containerfile is missing from the fetched branch. Checkout left intact for investigation."
    }
    $sha = (Get-FileHash -LiteralPath $containerfile -Algorithm SHA256).Hash.ToLowerInvariant()
    $imageTag = "midnight-provisioner-fedora-verifier:43-" + $sha.Substring(0, 12)
    Write-Host ""
    Write-Host "[3/6] Checking cached Fedora test image $imageTag" -ForegroundColor Yellow
    # A fresh workstation normally has no cached image. In Windows PowerShell
    # 5.1, docker image inspect's expected "No such image" stderr can become a
    # terminating error with ErrorActionPreference=Stop, before $LASTEXITCODE
    # can be inspected. Listing by exact tag succeeds with an empty result.
    $imageList = @(& docker image ls --format '{{.Repository}}:{{.Tag}}' --filter ("reference=" + $imageTag))
    Assert-ExitCode -Operation "Docker image cache lookup"
    $cached = @($imageList | Where-Object { $_.Trim() -eq $imageTag }).Count -gt 0
    if ($ForceImageBuild -or -not $cached) {
        Write-Host "Building an isolated image from Fedora 43. First build downloads Fedora RPMs."
        $buildDir = Join-Path ([IO.Path]::GetTempPath()) ("Midnight-Provisioner-Fedora-Build-" + [guid]::NewGuid().ToString("N"))
        [void](New-Item -ItemType Directory -Path $buildDir -ErrorAction Stop)
        Copy-Item -LiteralPath $containerfile -Destination (Join-Path $buildDir "Containerfile") -ErrorAction Stop
        # The build context contains ONLY this one Containerfile: no project code,
        # worktree, .env, .venv, SSH key or generated data goes to the build daemon.
        & docker build --pull=false --file (Join-Path $buildDir "Containerfile") --tag $imageTag $buildDir
        Assert-ExitCode -Operation "Fedora image build"
    } else {
        Write-Host "Cached image available; no package download required."
    }

    Write-Host ""
    Write-Host "[4/6] Running Fedora tests with Docker network disabled" -ForegroundColor Yellow
    $runArgs = @(
        "run", "--rm",
        "--name", ("midnight-provisioner-verify-" + $token),
        "--network", "none",
        "--read-only",
        "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges:true",
        "--user", "10001:10001",
        "--pids-limit", "160",
        "--cpus", "2",
        "--memory", "2048m",
        "--ipc", "private",
        "--tmpfs", "/tmp:rw,nosuid,nodev,size=512m",
        "--mount", ("type=bind,source={0},target=/workspace,readonly" -f $checkout),
        $imageTag
    )
    if ($Focused) {
        $runArgs += @("--focused", "--gui", "--native")
        Write-Host "Mode: focused Kali tests + Qt GUI + native QEMU/libvirt fixtures"
    } else {
        $runArgs += "--all"
        Write-Host "Mode: COMPLETE Fedora Python suite + Qt GUI + native QEMU/libvirt fixtures"
    }
    Write-Host "No original worktree mounts. No network, privileged mode, KVM or Docker socket."
    & docker @runArgs
    Assert-ExitCode -Operation "Fedora container verification"

    Write-Host ""
    Write-Host "[5/6] Interpreting result" -ForegroundColor Yellow
    Write-Host "[PASS] Requested Fedora container suites completed successfully." -ForegroundColor Green
    Write-Host "This is NOT real host Fedora SELinux/VM-boot/network/restore validation."

    Write-Host ""
    Write-Host "[6/6] Final safety summary" -ForegroundColor Yellow
    Write-Host "Original checkout: untouched (except shared Git fetch/worktree metadata)"
    Write-Host "Original main branch: unchanged"
    Write-Host "PRs: unmerged"
    Write-Host "GitHub Actions: never invoked"
    Write-Host "Worktree: $checkout"
    Write-Host "Log: $logPath"
    $success = $true
} catch {
    Write-Host ("[FAILED / INCOMPLETE] " + $_.Exception.Message) -ForegroundColor Red
    Write-Host "No pull requests were merged and the original tracked files were not overwritten."
    if ($logPath) { Write-Host "Check report: $logPath" }
} finally {
    # Remove ONLY a context directory created by this script (not user repos).
    if ($buildDir -and (Test-Path -LiteralPath $buildDir)) {
        try { Remove-Item -LiteralPath $buildDir -Recurse -Force -ErrorAction Stop }
        catch { Write-Warning "Unable to remove script-created temporary Docker build context: $buildDir" }
    }
    if ($transcriptStarted) {
        try { Stop-Transcript | Out-Null }
        catch { Write-Warning "Could not close results transcript." }
    }
}
if (-not $success) { exit 1 }
exit 0
