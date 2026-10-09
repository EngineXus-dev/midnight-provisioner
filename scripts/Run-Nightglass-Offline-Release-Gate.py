#!/usr/bin/env python3
"""Offline, read-only-at-runtime integration gate for the stacked Nightglass code.

Default: plan only; no Git/network/Docker/filesystem mutation.
--run: fetch ONE named release-candidate branch into a NEW detached sibling
worktree (Git metadata changes only in the original repo), validate all
PowerShell source with the native parser, run Python source syntax
and isolated Linux Docker synthetic/Qt/native-fixture suites sequentially.

No installation, USB writing, partition, VM launch, GitHub Actions,
automatic merge/reset/clean, environment-file overwrite or elevated shell.
"""
from __future__ import annotations

import argparse
import ast
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import time

BRANCH = "verification/windows-one-command-offline-gates"
ORIGIN = re.compile(
    r"^(?:https://github\.com/|git@github\.com:)"
    r"enginexus-dev/nightglass-workspaces(?:\.git)?/?$",
    re.IGNORECASE,
)
VERSIONS = ("3.11", "3.12", "3.13")
FEDORA_CONTAINERFILE = Path("docker/Containerfile.fedora-verification")
CHECKS = ("windows_powershell_ast", "python_source_ast", "python_311",
          "python_312", "python_313", "fedora_43")
VERDICT = {"PASS", "FAIL", "BLOCKED", "NOT_RUN"}


class GateError(RuntimeError):
    """A blocked test must never be reported as PASS."""


def checked(argv: list[str], *, cwd: Path, timeout: int = 30) -> str:
    run = subprocess.run(argv, cwd=cwd, text=True, encoding="utf-8",
                         errors="replace", stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, timeout=timeout,
                         check=False, shell=False)
    if run.returncode:
        raise GateError(f"{argv[0]} returned {run.returncode} ({' '.join(argv[1:3])})")
    return run.stdout.strip()


def repo_root(start: Path) -> Path:
    if not (shutil.which("git") and shutil.which("docker")
            and shutil.which("powershell.exe")):
        raise GateError("Requires git, Docker Desktop Linux engine and native Windows PowerShell.")
    root = Path(checked(["git", "-C", str(start), "rev-parse", "--show-toplevel"],
                        cwd=start)).resolve()
    remote = checked(["git", "-C", str(root), "remote", "get-url", "origin"], cwd=root)
    if not ORIGIN.fullmatch(remote):
        raise GateError("This is not the authorized Nightglass GitHub origin.")
    if not (root / "pyproject.toml").is_file():
        raise GateError("Nightglass pyproject.toml missing.")
    engine = checked(["docker", "info", "--format", "{{.OSType}}"], cwd=root, timeout=35)
    if engine != "linux":
        raise GateError("Docker Desktop must use Linux containers.")
    return root


def docker_base(checkout: Path, *, label: str, memory: str, tmpfs: str) -> list[str]:
    """All test images see only this detached, read-only source tree."""
    return [
        "docker", "run", "--rm", "--pull", "never", "--name", label,
        "--network", "none", "--read-only", "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges:true", "--user", "10001:10001",
        "--pids-limit", "160", "--cpus", "2", "--memory", memory,
        "--ipc", "private", "--tmpfs", f"/tmp:rw,nosuid,nodev,size={tmpfs}",
        "--mount", f"type=bind,source={checkout},target=/workspace,readonly",
    ]


def fedora_tag(checkout: Path) -> str:
    containerfile = checkout / FEDORA_CONTAINERFILE
    if not containerfile.is_file():
        raise GateError("Fedora verification Containerfile missing.")
    digest = hashlib.sha256(containerfile.read_bytes()).hexdigest()[:12]
    return "nightglass-fedora-verifier:43-" + digest


def image_cached(tag: str, *, cwd: Path) -> bool:
    # Docker image inspect on a cache miss emits stderr that is a fatal
    # pipeline error in Windows PowerShell 5.1. Listing handles misses.
    out = checked(["docker", "image", "ls", "--format",
                   "{{.Repository}}:{{.Tag}}", "--filter",
                   "reference=" + tag], cwd=cwd, timeout=30)
    return tag in out.splitlines()


def power_shell_ast(checkout: Path) -> list[str]:
    """Parse, never execute PowerShell source, including this branch's tools."""
    literal = str(checkout / "scripts").replace("'", "''")
    script = (
        "$ErrorActionPreference='Stop';"
        "$paths=@(Get-ChildItem -LiteralPath '" + literal +
        "' -Filter '*.ps1' -File -Recurse);"
        "if($paths.Count -eq 0){throw 'No PowerShell files found'};"
        "foreach($p in $paths){"
        "$tokens=$null;$errors=$null;"
        "[System.Management.Automation.Language.Parser]::ParseFile("
        "$p.FullName,[ref]$tokens,[ref]$errors)|Out-Null;"
        "if($errors.Count -gt 0){"
        "foreach($e in $errors){[Console]::Error.WriteLine("
        "$p.Name+': '+$e.Message)};exit 1}};"
        "Write-Output ('PowerShell AST parser PASS: '+$paths.Count+' script(s)')"
    )
    # Encode as UTF-16LE to avoid PowerShell's codepage/quotation ambiguity.
    import base64
    command = base64.b64encode(script.encode("utf-16le")).decode("ascii")
    return ["powershell.exe", "-NoProfile", "-NonInteractive",
            "-ExecutionPolicy", "Bypass", "-EncodedCommand", command]


def source_ast(checkout: Path) -> int:
    """Parse fetched Python source without running arbitrary tests on Windows."""
    count = 0
    for name in ("nightglass", "tests", "scripts"):
        folder = checkout / name
        if not folder.is_dir() or folder.is_symlink():
            raise GateError("Missing or symlinked Python source folder.")
        for source in folder.rglob("*.py"):
            if source.is_symlink() or not source.is_file():
                raise GateError("Unexpected symlink/non-file Python source.")
            ast.parse(source.read_text(encoding="utf-8"), filename=source.name)
            count += 1
    if count < 20:
        raise GateError("Suspiciously incomplete Python source tree.")
    return count


def branch_checkout(root: Path, *, expected_sha: str | None = None) -> tuple[Path, str, Path, Path]:
    """Never checkout in place, reuse a folder, reset, clean or merge."""
    git_ref = "refs/remotes/origin/" + BRANCH
    if expected_sha is not None and not re.fullmatch(r"[0-9a-f]{40}", expected_sha):
        raise GateError("Expected commit must be a full lowercase SHA40.")
    checked(["git", "-C", str(root), "fetch", "--no-tags", "origin",
             f"refs/heads/{BRANCH}:{git_ref}"], cwd=root, timeout=120)
    fetched = checked(["git", "-C", str(root), "rev-parse", git_ref], cwd=root)
    if not re.fullmatch(r"[0-9a-f]{40}", fetched):
        raise GateError("Fetched candidate ref has invalid SHA.")
    if expected_sha is not None and fetched != expected_sha:
        raise GateError("Fetched branch has advanced since approved SHA; no worktree created.")
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    marker = secrets.token_hex(5)
    stem = "Nightglass-RC-" + stamp + "-" + marker
    checkout = root.parent / stem
    log = root.parent / (stem + "-local-log.txt")
    report = root.parent / (stem + "-summary.json")
    if any(path.exists() or path.is_symlink() for path in (checkout, log, report)):
        raise GateError("New candidate worktree/report name already exists.")
    checked(["git", "-C", str(root), "worktree", "add", "--detach",
             str(checkout), git_ref], cwd=root, timeout=120)
    sha = checked(["git", "-C", str(checkout), "rev-parse", "HEAD"], cwd=checkout)
    expected = checked(["git", "-C", str(root), "rev-parse", git_ref], cwd=root)
    if sha != expected or not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise GateError("Detached checkout commit disagrees with fetched target.")
    if expected_sha is not None and sha != expected_sha:
        raise GateError("Pinned commit changed during worktree creation; no tests allowed.")
    return checkout, sha, log, report


def run_logged(args: list[str], *, cwd: Path, stream, seconds: int = 900) -> bool:
    display = " ".join(
        "[encoded PowerShell parser command]" if i > 0 and args[i-1] == "-EncodedCommand"
        else part for i, part in enumerate(args)
    )
    if "-EncodedCommand" in args:
        # Do not put the encoded parser program in logs.
        display = "powershell.exe -NoProfile -NonInteractive -EncodedCommand <parse-only>"
    stream.write("\n[COMMAND] " + display + "\n")
    stream.flush()
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1",
           "PYTHONNOUSERSITE": "1", "PYTHONFAULTHANDLER": "1"}
    try:
        result = subprocess.run(args, cwd=cwd, env=env, text=True,
                                stdout=stream, stderr=subprocess.STDOUT,
                                timeout=seconds, check=False, shell=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        stream.write(f"[BLOCKED] {type(exc).__name__}\n")
        stream.flush()
        return False
    stream.write(f"[EXIT] {result.returncode}\n")
    stream.flush()
    return result.returncode == 0


def fresh_image(image: str, *, root: Path, allow_pull: bool, stream) -> bool:
    if image_cached(image, cwd=root):
        return True
    if not allow_pull:
        stream.write(f"[BLOCKED] Missing cached {image}; rerun with --pull-python-images.\n")
        return False
    return run_logged(["docker", "pull", image], cwd=root, stream=stream,
                      seconds=1800)


def prepare_fedora(tag: str, *, checkout: Path, allow_build: bool, stream) -> bool:
    if image_cached(tag, cwd=checkout):
        return True
    if not allow_build:
        stream.write("[BLOCKED] Missing Fedora 43 image; rerun with --build-fedora-image.\n")
        return False
    with tempfile.TemporaryDirectory(prefix="nightglass-fedora-context-") as context:
        # The build daemon receives ONLY this Containerfile, never source,
        # environment files, VM images or the original Git checkout.
        shutil.copyfile(checkout / FEDORA_CONTAINERFILE, Path(context) / "Containerfile")
        return run_logged(["docker", "build", "--pull=false", "--file",
                           str(Path(context) / "Containerfile"), "--tag",
                           tag, context], cwd=checkout, stream=stream,
                          seconds=2400)


def summary_file(path: Path, payload: dict) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(path, flags, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(payload, stream, sort_keys=True, indent=2)
        stream.write("\n")


def verify(*, root: Path, allow_pull: bool, allow_build: bool,
           expected_sha: str | None = None) -> int:
    # Capture main's ref both before and after test worktree preparation.
    # This proves equality of the observed refs, not a claim about all
    # external processes that could modify the repository concurrently.
    main_before = checked(["git", "-C", str(root), "rev-parse",
                           "refs/heads/main"], cwd=root)
    if not re.fullmatch(r"[0-9a-f]{40}", main_before):
        raise GateError("Cannot verify original main ref before testing.")
    checkout, sha, log_path, report_path = branch_checkout(root, expected_sha=expected_sha)
    print("New detached read-only test source:", checkout)
    print("Exact tested commit:", sha)
    print("No original tracked/untracked files overwritten; Git worktree metadata added.")
    results = {key: "NOT_RUN" for key in CHECKS}
    error = None
    try:
        fd = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as log:
            log.write(f"Nightglass OFFLINE INTEGRATION GATE\n"
                      f"Source SHA: {sha}\nBranch: {BRANCH}\n"
                      "Never share full logs without reviewing private paths.\n")
            # Parse-only PowerShell; never execute fetched tests on host Windows.
            for key, args, timeout in (
                ("windows_powershell_ast", power_shell_ast(checkout), 45),
            ):
                results[key] = "PASS" if run_logged(args, cwd=checkout, stream=log,
                                                    seconds=timeout) else "FAIL"
                print(f"{key}: {results[key]}")
            # Pure syntax tree; fetched unit tests execute only in rootless Docker.
            try:
                count = source_ast(checkout)
                log.write(f"[PASS] Python AST parsed {count} source files (no imports).\n")
                results["python_source_ast"] = "PASS"
            except (OSError, SyntaxError, UnicodeError, GateError) as exc:
                log.write("[FAIL] Python AST: " + type(exc).__name__ + "\n")
                results["python_source_ast"] = "FAIL"
            print("python_source_ast:", results["python_source_ast"])
            # Run each interpreter independently, never concurrently on an 8GB host.
            for version in VERSIONS:
                key = "python_" + version.replace(".", "")
                image = f"python:{version}-slim"
                if not fresh_image(image, root=checkout, allow_pull=allow_pull, stream=log):
                    results[key] = "BLOCKED"
                    continue
                args = docker_base(checkout, label="nightglass-rc-py-"+
                                   version.replace(".", "")+"-"+sha[:8],
                                   memory="1024m", tmpfs="512m")
                args += ["-w", "/workspace", "-e", "HOME=/tmp",
                         "-e", "XDG_CONFIG_HOME=/tmp/ng-config",
                         "-e", "PYTHONDONTWRITEBYTECODE=1",
                         "-e", "PYTHONNOUSERSITE=1", image,
                         "python", "-B", "scripts/run_headless_matrix.py"]
                results[key] = ("PASS" if run_logged(args, cwd=checkout,
                                   stream=log) else "FAIL")
                print(f"{key}: {results[key]}")
            # Fedora 43 full Linux suite including Qt offscreen + native
            # QEMU/libvirt fixtures. Still NOT physical Fedora acceptance.
            tag = fedora_tag(checkout)
            if not prepare_fedora(tag, checkout=checkout, allow_build=allow_build,
                                  stream=log):
                results["fedora_43"] = "BLOCKED"
            else:
                args = docker_base(checkout, label="nightglass-rc-fedora-"+sha[:8],
                                   memory="2048m", tmpfs="512m")
                args += [tag, "--all"]
                results["fedora_43"] = ("PASS" if run_logged(
                    args, cwd=checkout, stream=log, seconds=1200) else "FAIL")
            print("fedora_43:", results["fedora_43"])
    except (OSError, GateError, ValueError) as exc:
        error = type(exc).__name__
        print("[BLOCKED] Could not complete all checks:", error, file=sys.stderr)
    try:
        main_after = checked(["git", "-C", str(root), "rev-parse",
                              "refs/heads/main"], cwd=root)
        if not re.fullmatch(r"[0-9a-f]{40}", main_after):
            raise GateError("Invalid original main ref after test run.")
    except (OSError, GateError, subprocess.TimeoutExpired) as exc:
        main_after = "UNKNOWN"
        error = error or type(exc).__name__
    if main_after != main_before:
        error = error or "MainRefChanged"
    # Hash the completed local log before writing the independent report.
    try:
        log_digest = hashlib.sha256(log_path.read_bytes()).hexdigest()
    except OSError as exc:
        log_digest = "UNKNOWN"
        error = error or type(exc).__name__
    passed = all(results[k] == "PASS" for k in CHECKS) and error is None
    report = {
        "format": "nightglass-offline-rc-gate-v2",
        "collected_at_utc": datetime.now(timezone.utc).isoformat(),
        "branch": BRANCH, "tested_commit": sha, "checks": results,
        "test_gate_passed": passed, "execution_error": error,
        "original_main_before": main_before, "original_main_after": main_after,
        "local_log_sha256": log_digest, "report_authentication": "LOCAL_UNAUTHENTICATED",
        "deployment_approved": False, "release_attested": False,
        "physical_fedora_kvm_svirt_network_restore": "NOT_TESTED",
        "windows11_clean_install_usb_formatter": "NOT_RUN",
        "github_pr_merge_or_actions": "NOT_PERFORMED",
        "notice": "Synthetic/GUI/native fixtures only. No real VM isolation claim.",
    }
    try:
        summary_file(report_path, report)
    except OSError as exc:
        print("[BLOCKED] Could not exclusively create private summary:",
              type(exc).__name__, file=sys.stderr)
        return 1
    print("Local log (review before sharing):", log_path)
    print("Private status-only summary:", report_path)
    print("Independent local evidence auditor: scripts/Audit-Nightglass-Release-Evidence.py")
    print("Evidence remains UNAUTHENTICATED; review full logs and exact Git SHA.")
    print("Physical Fedora hardware acceptance: PENDING.")
    print("No OS install, USB formatting, PR merge or GitHub Actions.")
    print("OVERALL: " + ("ALL SELECTED GATES PASS" if passed else "INCOMPLETE / BLOCKED"))
    return 0 if passed else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Nightglass read-only offline integration gate")
    ap.add_argument("--repo", type=Path, default=Path.cwd(),
                    help="Existing Nightglass Git checkout (not overwritten)")
    ap.add_argument("--run", action="store_true",
                    help="Opt-in fetch, new detached worktree and local checks")
    ap.add_argument("--pull-python-images", action="store_true",
                    help="Explicitly allow first-time official Python image pulls")
    ap.add_argument("--build-fedora-image", action="store_true",
                    help="Explicitly allow Fedora test image build/RPM network")
    ap.add_argument("--expected-commit", default=None,
                    help="Optional SHA40 pin: refuse advanced branch before creating a test worktree")
    args = ap.parse_args(argv)
    print("Nightglass release candidate verification — branch:", BRANCH)
    print("Windows 10/11 and original Git checkout will not be modified.")
    if not args.run:
        print("PLAN ONLY (default): no fetch, new worktree, file, Docker or host changes.")
        print("Opt-in: --run; missing test images require explicit pull/build flags.")
        print("Phases: Windows PowerShell and Python AST (parse-only), Python 3.11–3.13 Docker, Fedora 43 Qt/native.")
        print("No GitHub Actions or merges. Real Fedora hardware acceptance still pending.")
        return 0
    if os.name != "nt":
        print("[BLOCKED] This runner must execute on native Windows.", file=sys.stderr)
        return 2
    try:
        root = repo_root(args.repo.resolve())
        return verify(root=root, allow_pull=args.pull_python_images,
                      allow_build=args.build_fedora_image,
                      expected_sha=args.expected_commit)
    except (OSError, ValueError, GateError, subprocess.TimeoutExpired) as exc:
        print("[BLOCKED] Setup:", type(exc).__name__, str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
