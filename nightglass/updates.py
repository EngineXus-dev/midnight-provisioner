"""Opt-in, source-checkout updater. Never overwrites modified files or guest data.

This is a convenient trusted-repository update path, NOT a signed-release
verifier. Unattended code installation remains intentionally unsupported until
authenticated/signature-verified release artifacts and rollback are available.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import subprocess

from .runner import ToolError

PROJECT_REMOTE_URLS = frozenset({
    "https://github.com/EngineXus-dev/nightglass-workspaces.git",
    "https://github.com/EngineXus-dev/nightglass-workspaces",
    "git@github.com:EngineXus-dev/nightglass-workspaces.git",
    "ssh://git@github.com/EngineXus-dev/nightglass-workspaces.git",
})
UPDATE_BRANCH = "main"


@dataclass(frozen=True)
class UpdateStatus:
    behind: int
    ahead: int
    current_sha: str
    upstream_sha: str

    @property
    def can_fast_forward(self) -> bool:
        return self.behind > 0 and self.ahead == 0


class SourceUpdater:
    """Operates only on the official, clean, checked-out main branch."""

    def __init__(self, root: Path | None = None):
        self.root = (root or Path(__file__).resolve().parents[1]).resolve()

    def _git(self, *args: str, timeout: int = 35) -> str:
        env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GIT_CONFIG_NOSYSTEM="1")
        try:
            call = subprocess.run(
                ["git", "-c", "core.hooksPath=/dev/null", *args],
                cwd=self.root, env=env, text=True, capture_output=True,
                timeout=timeout, check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ToolError(f"Git is unavailable or timed out: {exc}") from exc
        if call.returncode:
            raise ToolError(f"Git {args[0]} failed: {(call.stderr or call.stdout).strip()[:350]}")
        return call.stdout.strip()

    def _verify_checkout(self) -> None:
        if not (self.root / "pyproject.toml").is_file():
            raise ToolError("Updates require a Nightglass source checkout (not a wheel installation)")
        top = Path(self._git("rev-parse", "--show-toplevel")).resolve()
        if top != self.root:
            raise ToolError("Refusing to update from an unexpected working-tree root")
        remote = self._git("remote", "get-url", "origin")
        if remote not in PROJECT_REMOTE_URLS:
            raise ToolError("Origin does not match the official Nightglass repository")
        if self._git("symbolic-ref", "--quiet", "--short", "HEAD") != UPDATE_BRANCH:
            raise ToolError("Source updates only run on main; development branches are never overwritten")

    def _verify_clean(self) -> None:
        if self._git("status", "--porcelain", "--untracked-files=normal"):
            raise ToolError("Local source changes or untracked files found. Commit, remove, or stash them first; nothing was changed.")

    def check(self) -> UpdateStatus:
        self._verify_checkout()
        # This fetch alters Git tracking refs, never the working tree.
        self._git("fetch", "--no-tags", "origin", UPDATE_BRANCH, timeout=90)
        ahead_behind = self._git("rev-list", "--left-right", "--count", "HEAD...refs/remotes/origin/main").split()
        if len(ahead_behind) != 2 or not all(part.isdigit() for part in ahead_behind):
            raise ToolError("Unexpected Git ahead/behind status")
        # HEAD-side commits are 'ahead'; upstream-side commits are 'behind'.
        ahead, behind = map(int, ahead_behind)
        return UpdateStatus(
            behind, ahead, self._git("rev-parse", "HEAD"),
            self._git("rev-parse", "refs/remotes/origin/main"),
        )

    def apply(self, *, confirmed: bool = False) -> str:
        if not confirmed:
            raise ToolError("Update requires explicit confirmation")
        self._verify_clean()
        status = self.check()
        self._verify_clean()
        if status.ahead:
            raise ToolError("Local branch diverged from main; refusing automatic merge or reset")
        if status.behind == 0:
            return "Nightglass is already up to date."
        # Recheck HEAD after the network fetch before a fast-forward.
        if self._git("rev-parse", "HEAD") != status.current_sha:
            raise ToolError("Checkout changed during the update; please retry")
        self._git("merge", "--ff-only", "--no-edit", status.upstream_sha, timeout=90)
        return f"Updated Nightglass source to {status.upstream_sha[:12]}. Restart the app to load the new code."
