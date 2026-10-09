"""Headless diagnostics and workspace inspection. Host-changing actions are GUI-gated."""
from __future__ import annotations
import argparse
from dataclasses import replace
import sys
from .settings import load_workspaces
from .models import WorkspaceError
from .diagnostics import collect_checks, resource_advice
from .hypervisor import Hypervisor
from .runner import ToolError
from .portability import (
    MachinePreferences, budget_for, current_budget, load_machine_preferences,
    save_machine_preferences,
)
from .diagnostics import total_ram_gib
from .updates import SourceUpdater
import os


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="nightglass", description="Nightglass secure-workspace controller")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("doctor", help="Read-only host readiness checks")
    sub.add_parser("list", help="List configured workspaces (read-only)")
    sub.add_parser("gui", help="Launch workspace manager graphical interface")
    info = sub.add_parser("inspect", help="Read-only policy audit of a configured VM")
    info.add_argument("key", help="Workspace key, e.g. pentest or analysis")
    profile = sub.add_parser("profile", help="Inspect or switch portable hardware profiles")
    profiles = profile.add_subparsers(dest="profile_action")
    profiles.add_parser("show", help="Show active hardware resource limits")
    apply_profile = profiles.add_parser("apply", help="Apply one of the two machine setup profiles")
    apply_profile.add_argument("target", choices=("8gb", "up-to-32gb"))
    apply_profile.add_argument("--yes", action="store_true", help="Confirm without an interactive prompt")

    updates = sub.add_parser("update", help="Safe opt-in source updates from official main branch")
    update_actions = updates.add_subparsers(dest="update_action")
    update_actions.add_parser("check", help="Fetch update metadata without modifying local source")
    update_apply = update_actions.add_parser("apply", help="Fast-forward a clean main checkout only")
    update_apply.add_argument("--yes", action="store_true", help="Confirm without an interactive prompt")
    update_setting = update_actions.add_parser("checks", help="Opt into startup update notices")
    update_setting.add_argument("state", choices=("on", "off"))
    args = parser.parse_args(argv)
    cmd = args.command or "gui"
    try:
        if cmd == "profile":
            if args.profile_action in (None, "show"):
                print(current_budget().explain())
                return 0
            current = load_machine_preferences()
            ram = total_ram_gib()
            if args.target == "8gb" or ram is None or ram < 11:
                preset = MachinePreferences(
                    preset="compact", guest_ram_cap_gib=3.0,
                    active_vm_cap=1, vcpu_cap=2,
                    automatic_update_checks=current.automatic_update_checks,
                )
                if args.target != "8gb":
                    print("Less than 11 GiB RAM detected: using the 8 GB-safe profile.")
            else:
                preset = MachinePreferences(
                    preset=("performance" if ram >= 28 else "balanced"),
                    automatic_update_checks=current.automatic_update_checks,
                )
            preview = budget_for(ram, os.cpu_count(), preset)
            print(preview.explain())
            print("Only Nightglass machine.json will change; no VM disk, network, bootloader, or workspace definition changes.")
            if not args.yes:
                if not sys.stdin.isatty() or input("Type APPLY to save these settings: ").strip() != "APPLY":
                    print("Cancelled; settings unchanged.")
                    return 1
            save_machine_preferences(preset)
            print("Saved. Future launches through Nightglass use this machine's resource guardrails.")
            return 0
        if cmd == "update":
            if args.update_action == "checks":
                current = load_machine_preferences()
                save_machine_preferences(replace(current, automatic_update_checks=args.state == "on"))
                print(f"Automatic update notifications: {args.state}; code will never auto-install.")
                return 0
            if args.update_action == "check":
                result = SourceUpdater().check()
                print(f"Official main: {result.behind} behind, {result.ahead} ahead")
                return 0
            if args.update_action == "apply":
                if not args.yes:
                    if not sys.stdin.isatty() or input("Type UPDATE to fast-forward clean main: ").strip() != "UPDATE":
                        print("Cancelled; source unchanged.")
                        return 1
                print(SourceUpdater().apply(confirmed=True))
                return 0
            parser.error("Specify: update check, update apply, or update checks on/off")
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
            print(f"{space.name}: {audit.summary} ({space.policy}; managed save: {'yes' if audit.saved_state else 'no'})")
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
