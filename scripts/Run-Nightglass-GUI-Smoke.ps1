# Opt-in Windows Qt GUI smoke against an explicitly pinned Nightglass commit.
# No VM startup, OS changes, package installs, or backup-disk operations.
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)]
    [ValidatePattern('^[A-Fa-f0-9]{40}$')]
    [string] $ExpectedSha,
    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9_./-]{0,119}$')]
    [string] $Branch = 'fix/pr52-windows-synthetic-fixtures',
    [ValidateRange(30,3600)]
    [int] $TimeoutSeconds = 600
)
$ErrorActionPreference = 'Stop'
$sha = $ExpectedSha.ToLowerInvariant()
$repoRoot = (& git rev-parse --show-toplevel 2>$null)
if ($LASTEXITCODE -ne 0 -or -not $repoRoot) { throw 'Run from the Nightglass repository.' }
$repoRoot = ($repoRoot -join '').Trim()
$origin = (& git -C $repoRoot remote get-url origin)
if ($LASTEXITCODE -ne 0 -or ($origin -join '').Trim() -notmatch '^https://github\.com/EngineXus-dev/nightglass-workspaces(?:\.git)?/?$') { throw 'Unexpected Git remote.' }
$python = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw 'Python 3.12 required; no auto-install.' }
$version = (& $python -c 'import sys; print(sys.version_info.major,sys.version_info.minor)' 2>&1)
if ($LASTEXITCODE -ne 0 -or ($version -join ' ').Trim() -ne '3 12') { throw 'Python version mismatch.' }
$session = Join-Path $env:TEMP ('Nightglass-QtSmoke-' + [guid]::NewGuid().ToString('N'))
$checkoutRoot = Join-Path $session 'source'
New-Item -ItemType Directory -Path $session | Out-Null
& git -C $repoRoot fetch --no-tags origin $Branch
if ($LASTEXITCODE -ne 0) { throw 'Git metadata fetch failed.' }
$fetchedSha = (& git -C $repoRoot rev-parse FETCH_HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $fetchedSha -ne $sha) { throw "Candidate branch changed: $fetchedSha" }
& git -C $repoRoot worktree add --detach $checkoutRoot $sha
if ($LASTEXITCODE -ne 0) { throw 'Detached worktree creation failed.' }
$actualSha = (& git -C $checkoutRoot rev-parse HEAD).Trim()
if ($actualSha -ne $sha) { throw 'Worktree SHA mismatch.' }
$test = 'test_gui_smoke.py'
if (-not (Test-Path -LiteralPath (Join-Path $checkoutRoot "tests\$test") -PathType Leaf)) { throw 'GUI test missing.' }
$archiveScript = Join-Path $checkoutRoot 'scripts\Archive-Nightglass-TestResults.ps1'
if (-not (Test-Path -LiteralPath $archiveScript -PathType Leaf)) { throw 'Archive helper missing.' }

# Never assign $HOME: PowerShell has a read-only automatic variable with that name.
$prior = @{}
foreach ($key in @('TMP','TEMP','HOME','XDG_CONFIG_HOME','XDG_DATA_HOME','PYTHONPATH',
                   'PYTHONNOUSERSITE','PYTHONDONTWRITEBYTECODE','QT_QPA_PLATFORM',
                   'NIGHTGLASS_GUI_SMOKE','NIGHTGLASS_GUI_PREVIEW')) {
    $prior[$key] = [Environment]::GetEnvironmentVariable($key,'Process')
}
$scratch = Join-Path $session 'scratch'
$testHome = Join-Path $session 'test-home'
New-Item -ItemType Directory -Path $scratch,$testHome | Out-Null
$env:TMP = $scratch
$env:TEMP = $scratch
$env:HOME = $testHome
$env:XDG_CONFIG_HOME = Join-Path $testHome 'config'
$env:XDG_DATA_HOME = Join-Path $testHome 'data'
$env:PYTHONNOUSERSITE = '1'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:QT_QPA_PLATFORM = 'offscreen'
$env:NIGHTGLASS_GUI_SMOKE = '1'
$env:NIGHTGLASS_GUI_PREVIEW = Join-Path $session 'nightglass-gui-smoke.png'
Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue

$stdout = Join-Path $session "$test.stdout.log"
$stderr = Join-Path $session "$test.stderr.log"
$qtLog = Join-Path $session 'qt-prerequisite.log'
$exitCode = 99
$status = 'NOT_RUN_QT_UNAVAILABLE'
try {
    $oldPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        $probe = (& $python -B -c 'from PySide6.QtWidgets import QApplication' 2>&1)
        $probeExit = $LASTEXITCODE
    } finally { $ErrorActionPreference = $oldPreference }
    @($probe | ForEach-Object { [string]$_ }) | Out-File -LiteralPath $qtLog -Encoding UTF8
    if ($probeExit -eq 0) { Add-Content -LiteralPath $qtLog -Value 'PySide6.QtWidgets imported successfully.' }
    if ($probeExit -eq 0) {
        # Use .NET Process with asynchronous redirected streams instead of
        # Start-Process -PassThru, whose ExitCode can be null in PS5.1.
        $psi = New-Object System.Diagnostics.ProcessStartInfo
        $psi.FileName = $python
        $psi.Arguments = "-B -m unittest discover -s tests -p $test -v"
        $psi.WorkingDirectory = $checkoutRoot
        $psi.UseShellExecute = $false
        $psi.CreateNoWindow = $true
        $psi.RedirectStandardOutput = $true
        $psi.RedirectStandardError = $true
        $process = New-Object System.Diagnostics.Process
        $process.StartInfo = $psi
        try {
            if (-not $process.Start()) { throw 'Could not start the GUI test process.' }
            $stdoutTask = $process.StandardOutput.ReadToEndAsync()
            $stderrTask = $process.StandardError.ReadToEndAsync()
            $finished = $process.WaitForExit($TimeoutSeconds * 1000)
            if (-not $finished) {
                try { $process.Kill() } catch { }
                $process.WaitForExit()
            }
            [IO.File]::WriteAllText($stdout, $stdoutTask.Result)
            [IO.File]::WriteAllText($stderr, $stderrTask.Result)
            if (-not $finished) {
                $exitCode = 124
                $status = 'GUI_TEST_TIMEOUT'
            } else {
                $exitCode = [int]$process.ExitCode
                $status = if ($exitCode -eq 0) { 'SUITE_EXITED_ZERO_REVIEW_LOG' } else { 'GUI_TEST_FAILED' }
            }
        } finally {
            $process.Dispose()
        }
    } else {
        [IO.File]::WriteAllText($stdout, '')
        [IO.File]::WriteAllText($stderr, 'PySide6 unavailable; see qt-prerequisite.log')
    }
} finally {
    foreach ($key in $prior.Keys) {
        [Environment]::SetEnvironmentVariable($key,$prior[$key],'Process')
    }
}
$body = [IO.File]::ReadAllText($stderr)
$match = [regex]::Match($body,'(?m)^Ran (\d+) tests? in ')
$cases = if ($match.Success) { [int]$match.Groups[1].Value } else { 0 }
$skipped = [regex]::Matches($body,'(?m)^test_.*\.\.\. skipped ').Count
if ($exitCode -eq 0 -and ($cases -eq 0 -or $skipped -ge $cases)) { $status = 'FAILED_NO_EXECUTED_GUI_TESTS' }
[pscustomobject]@{Test=$test;ExitCode=$exitCode;Ran=$cases;Skipped=$skipped;Status=$status} | Export-Csv -LiteralPath (Join-Path $session 'summary.csv') -NoTypeInformation -Encoding UTF8
@("Expected SHA: $sha", "Actual SHA: $actualSha", "Python: $python", "Status: $status", 'Scope: synthetic offscreen widgets; no real VM or Fedora acceptance') | Set-Content -LiteralPath (Join-Path $session 'manifest.txt') -Encoding UTF8
$zip = Join-Path ([Environment]::GetFolderPath('UserProfile')) ("Downloads\Nightglass-QtSmoke-$([guid]::NewGuid().ToString('N')).zip")
if (Test-Path -LiteralPath $zip) { throw "Refusing to overwrite ZIP $zip" }
$files = @(Get-ChildItem -LiteralPath $session -File)
Compress-Archive -LiteralPath $files.FullName -DestinationPath $zip
Write-Host "Nightglass GUI evidence ZIP: $zip"
$archiveOk = $false
try {
    & $archiveScript -ResultsZip $zip -CommitSha $sha -Label 'QtOffscreen'
    if (-not $?) { throw 'Archive helper failed.' }
    $archiveOk = $true
} catch {
    Write-Warning "Archive failed: $($_.Exception.Message)"
    Write-Warning "Evidence ZIP retained at $zip"
}
Write-Host "GUI status: $status ($cases cases; $skipped skipped)"
if ($status -ne 'SUITE_EXITED_ZERO_REVIEW_LOG') { throw 'GUI smoke failed or produced no executed tests' }
if (-not $archiveOk) { throw 'GUI tests passed but persistent evidence archiving failed.' }
