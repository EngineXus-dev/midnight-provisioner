"""Safe, argument-vector subprocess adapter. No shell interpolation or arbitrary commands."""

from __future__ import annotations
import os
import subprocess
from dataclasses import dataclass


class ToolError(RuntimeError):
    pass


@dataclass(frozen=True)
class Output:
    stdout: str
    stderr: str = ""
    code: int = 0


class Runner:
    def run(self, argv: list[str], timeout: int = 12) -> Output:
        if not argv or any(not isinstance(arg, str) or "\x00" in arg for arg in argv):
            raise ToolError("Invalid command argument")
        env = dict(os.environ)
        env["LC_ALL"] = "C"
        env["LANG"] = "C"
        try:
            # Undecodable tool output (e.g. a non-UTF-8 VM name) must not escape as UnicodeDecodeError.
            result = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", errors="replace",
                                    stdin=subprocess.DEVNULL, timeout=timeout, check=False, shell=False, env=env)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ToolError(f"Command unavailable or timed out: {argv[0]} ({exc})") from exc
        if result.returncode != 0:
            raise ToolError(f"{argv[0]} exited {result.returncode}: {(result.stderr or result.stdout).strip()[:500]}")
        return Output(result.stdout, result.stderr, result.returncode)
