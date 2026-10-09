"""Headless diagnostics and workspace inspection. Host-changing actions are GUI-gated."""
from __future__ import annotations
import argparse
import sys
from .settings import load_workspaces
from .models import WorkspaceError
from .diagnostics import collect_checks, resource_advice
from .hypervisor import Hypervisor
from .runner import ToolError


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="nightglass", description="Nightglass secure-workspace controller")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("doctor", help="Read-only host readiness checks")
    sub.add_parser("list", help="List configured workspaces (read-only)")
    sub.add_parser("gui", help="Launch workspace manager graphical interface")
    info = sub.add_parser("inspect", help="Read-only policy audit of a configured VM")
    info.add_argument("key", help="Workspace key, e.g. pentest or analysis")
    args = parser.parse_args(argv)
    cmd = args.command or "gui"
    try:
        if cmd == "doctor":
            for chk in collect_checks():
                print(("PASS" if chk.ok else "WARN") + f"  {chk.name}: {chk.message}")
            print(resource_advice())
            return 0
        if cmd == "list":
            for item in load_workspaces():
                print(f"{item.key:14s} {item.kind:9s} {item.policy:9s} {item.identifier or '-'}")
            return 0
        if cmd == "inspect":
            space = next((s for s in load_workspaces() if s.key == args.key), None)
            if space is None or space.kind != "vm":
                parser.error("inspect requires a configured VM workspace key")
            audit = Hypervisor().audit(space.identifier, space.policy)
            print(f"{space.name}: {audit.summary} ({space.policy})")
            for note in audit.warnings:
                print(f"  - {note}")
            return 0 if audit.ok else 2
        if cmd == "gui":
            from .ui import run_gui
            return run_gui()
    except (WorkspaceError, ToolError) as exc:
        print(f"Nightglass: {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
