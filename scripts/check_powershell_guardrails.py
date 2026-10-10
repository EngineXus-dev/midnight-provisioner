#!/usr/bin/env python3
"""Read-only PowerShell 5.1 portability scanner (does not execute .ps1 files).

A lexical tripwire, not a full interpreter: native Windows AST parsing is a
separate requirement.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys

# PowerShell is case-insensitive: $home collides with the read-only $HOME.
RESERVED = frozenset({
    "home", "host", "pid", "pwd", "pshome", "psversiontable",
    "true", "false", "null", "error", "matches", "myinvocation",
    "psscriptroot", "pscommandpath", "input", "this", "args", "lastexitcode",
})
_ASSIGNMENT = re.compile(
    r"^\s*\$(?:\{(?P<braced>[A-Za-z][A-Za-z0-9_]*)\}|"
    r"(?P<plain>[A-Za-z][A-Za-z0-9_]*))\s*(?P<op>=|\+=|-=|\*=|/=|%=|\+\+|--)(?!=)",
    re.IGNORECASE,
)
_ASSIGNMENT_CMD = re.compile(
    r"^\s*(?:Set-Variable|New-Variable)\s+(?:-Name\s+)?"
    r"['\"]?(?P<name>[A-Za-z][A-Za-z0-9_]*)\b", re.IGNORECASE,
)
_FOREACH = re.compile(
    r"\bforeach\s*\(\s*\$(?P<name>[A-Za-z][A-Za-z0-9_]*)\s+in\b", re.IGNORECASE,
)
_PARAM_DECL = re.compile(
    r"^\s*\[(?:string|int|long|bool|object|switch|array|hashtable|datetime|guid)\]\s*\$(?P<name>[A-Za-z][A-Za-z0-9_]*)\b",
    re.IGNORECASE,
)


def candidates(source: str) -> list[tuple[int, str, str]]:
    """Return plausible protected-variable definitions (lexical check only)."""
    findings: list[tuple[int, str, str]] = []
    for lineno, raw in enumerate(source.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        names: list[str] = []
        for regex in (_ASSIGNMENT, _ASSIGNMENT_CMD, _FOREACH, _PARAM_DECL):
            match = regex.search(raw)
            if not match:
                continue
            groups = match.groupdict()
            op = groups.pop("op", None)
            found = [v.lower() for v in groups.values() if v]
            # "$null = <expr>" is PowerShell's standard way to discard output.
            if regex is _ASSIGNMENT and op == "=" and found == ["null"]:
                continue
            names.extend(found)
        for name in set(names) & RESERVED:
            findings.append((lineno, name, raw.strip()))
    return findings


def scan(paths: list[Path]) -> list[str]:
    issues = []
    for path in paths:
        for number, name, source in candidates(path.read_text(encoding="utf-8-sig")):
            issues.append(f"{path}:{number}: prohibited protected variable {name}: {source}")
    return issues


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", metavar="PATH", nargs="*", type=Path)
    args = parser.parse_args(argv)
    paths = args.paths or sorted(Path(__file__).resolve().parent.rglob("*.ps1"))
    if not paths:
        print("No PowerShell files selected", file=sys.stderr)
        return 2
    missing = [str(p) for p in paths if not p.is_file()]
    if missing:
        print("Missing scripts: " + ", ".join(missing), file=sys.stderr)
        return 2
    issues = scan(paths)
    if issues:
        print("\n".join(issues), file=sys.stderr)
        return 1
    print(f"PowerShell reserved-variable scan PASS ({len(paths)} files); native AST parsing still required")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
