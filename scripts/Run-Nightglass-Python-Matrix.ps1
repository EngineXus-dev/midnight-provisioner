#requires -Version 5.1
<#
 Nightglass Python 3.11/3.12/3.13 Linux synthetic unit matrix.
 Explicit, offline-at-runtime, read-only Docker validation, no GitHub Actions.
 Produces a NEW detached sibling worktree; never updates existing working files.
 Does not run Qt, native QEMU/libvirt fixtures, or actual Fedora/KVM guests.
#>
[CmdletBinding()]
param([string]$RepoPath = "")
$ErrorActionPreference = "Stop"
$branch = "verification/fedora-host-acceptance-preflight"
$success = $false
$transcriptStarted = $false
$logPath = $null

function Assert-Exit {
    param([string]$Stage)
    if ($LASTEXITCODE -ne 0) { throw "$Stage failed with exit code $LASTEXITCODE" }
}

try {
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw "Git is required" }
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw "Docker is required" }
    if (-not $RepoPath.Trim()) { $RepoPath = (Get-Location).Path }
    if (-not (Test-Path -LiteralPath $RepoPath -PathType Container)) {
        throw "Repository directory does not exist"
    }
    $root = (& git -C $RepoPath rev-parse --show-toplevel | Out-String).Trim()
    Assert-Exit "Locate original checkout"
    $origin = (& git -C $root remote get-url origin | Out-String).Trim()
    Assert-Exit "Read original origin"
    if ($origin -notmatch '(?i)(^|[:/])EngineXus-dev/nightglass-workspaces(\.git)?$') {
        throw "Origin does not match dedicated Nightglass repository"
    }

    $token = [guid]::NewGuid().ToString("N").Substring(0, 8)
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $parent = Split-Path -Parent $root
    $checkout = Join-Path $parent ("Nightglass-Python-Matrix-" + $stamp + "-" + $token)
    $logPath = Join-Path $parent ("Nightglass-Python-Matrix-" + $stamp + "-" + $token + "-results.txt")
    if ((Test-Path -LiteralPath $checkout) -or (Test-Path -LiteralPath $logPath)) {
        throw "Refusing to reuse existing checkout or log"
    }
    Start-Transcript -LiteralPath $logPath -NoClobber | Out-Null
    $transcriptStarted = $true

    Write-Host "Nightglass PYTHON 3.11-3.13 MATRIX — NO HOST MODIFICATION"
    Write-Host "Images may be pulled from Docker Hub on first use; each test container has --network none."
    Write-Host "No merges, resets, git clean, force-push, GitHub Actions, guest boot or .env/.venv overwrite."
    $engine = (& docker info --format '{{.OSType}}' | Out-String).Trim()
    Assert-Exit "Docker daemon"
    if ($engine -ne "linux") { throw "Docker Linux containers engine required" }

    & git -C $root fetch --no-tags origin ("refs/heads/{0}:refs/remotes/origin/{0}" -f $branch)
    Assert-Exit "Fetch dedicated acceptance branch"
    & git -C $root worktree add --detach $checkout ("refs/remotes/origin/" + $branch)
    Assert-Exit "Create new independent test worktree"
    $head = (& git -C $checkout rev-parse HEAD | Out-String).Trim()
    Assert-Exit "Read test commit"
    Write-Host "Isolated worktree: $checkout"
    Write-Host "Test commit: $head"

    foreach ($version in @("3.11", "3.12", "3.13")) {
        $image = "python:$version-slim"
        Write-Host ""
        Write-Host "[MATRIX $version] Checking locally cached official Python image"
        $existing = @(& docker image ls --format '{{.Repository}}:{{.Tag}}' --filter ("reference=" + $image))
        Assert-Exit "Image cache lookup for $version"
        if (@($existing | Where-Object { $_.Trim() -eq $image }).Count -eq 0) {
            Write-Host "Image not cached. Pulling $image (test runtime remains offline)."
            & docker pull $image
            Assert-Exit "Image pull for $version"
        }

        Write-Host "[MATRIX $version] Running Linux synthetic unittest suite, offline"
        $argsDocker = @(
            "run", "--rm", "--pull", "never",
            "--name", ("nightglass-py-" + $version.Replace(".", "") + "-" + $token),
            "--network", "none", "--read-only", "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges:true",
            "--user", "10001:10001", "--pids-limit", "160",
            "--cpus", "2", "--memory", "1024m",
            # Backup/recovery test fixtures require 256 MiB free *reserve*
            # beyond the small fixture files themselves. A 256m tmpfs
            # inevitably fails those safe storage-capacity gates.
            "--tmpfs", "/tmp:rw,nosuid,nodev,size=512m",
            "--mount", ("type=bind,source={0},target=/workspace,readonly" -f $checkout),
            "-w", "/workspace", "-e", "HOME=/tmp", "-e", "XDG_CONFIG_HOME=/tmp/nightglass-config",
            "-e", "PYTHONDONTWRITEBYTECODE=1", "-e", "PYTHONNOUSERSITE=1",
            $image, "python", "-B", "-m", "unittest", "discover",
            "-s", "tests", "-p", "test*.py", "-q"
        )
        & docker @argsDocker
        Assert-Exit "Python $version synthetic tests"
        Write-Host "[PASS] Python $version Linux synthetic suite."
    }

    Write-Host ""
    Write-Host "[PASS] Three Python runtimes completed headless Linux synthetic tests."
    Write-Host "GUI/native fixtures NOT run in this matrix; Fedora 43 container ran them separately."
    Write-Host "Real Fedora host SELinux/KVM/VM-network/restore acceptance remains PENDING."
    Write-Host "Original checkout and main unchanged; no PRs merged or Actions triggered."
    Write-Host "Result log: $logPath"
    $success = $true
} catch {
    Write-Host ("[FAILED / INCOMPLETE] " + $_.Exception.Message) -ForegroundColor Red
    if ($logPath) { Write-Host "Report: $logPath" }
} finally {
    if ($transcriptStarted) {
        try { Stop-Transcript | Out-Null }
        catch { Write-Warning "Unable to close test transcript" }
    }
}
if (-not $success) { exit 1 }
exit 0
