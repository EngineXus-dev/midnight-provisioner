"""Headless diagnostics and workspace inspection. Host-changing actions are GUI-gated."""
from __future__ import annotations
import argparse
from pathlib import Path
from dataclasses import replace
import sys
from .settings import load_workspaces
from .models import WorkspaceError
from .diagnostics import collect_checks, resource_advice, total_ram_gib
from .hypervisor import Hypervisor
from .runner import ToolError
from .portability import (
    MachinePreferences, budget_for, current_budget, load_machine_preferences,
    save_machine_preferences,
)
from .updates import SourceUpdater
from .provisioning import OfflineProvisioner, build_plan
from .backups import ColdBackup, verify_backup
from .recovery import RecoveryStager, verify_staging
from .readiness import RecoveryReadiness
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
    apply_profile = profiles.add_parser("apply", help="Select machine profile (Auto detects hardware)")
    apply_profile.add_argument("target", choices=("auto", "compact", "balanced", "performance"))
    apply_profile.add_argument("--yes", action="store_true", help="Confirm without an interactive prompt")

    updates = sub.add_parser("update", help="Safe opt-in source updates from official main branch")
    update_actions = updates.add_subparsers(dest="update_action")
    update_actions.add_parser("check", help="Fetch update metadata without modifying local source")
    update_apply = update_actions.add_parser("apply", help="Fast-forward a clean main checkout only")
    update_apply.add_argument("--yes", action="store_true", help="Confirm without an interactive prompt")
    update_setting = update_actions.add_parser("checks", help="Opt into startup update notices")
    update_setting.add_argument("state", choices=("on", "off"))
    wizard = sub.add_parser("provision", help="Read-only VM ISO integrity and guest XML preflight")
    wizard.add_argument("kind", choices=("pentest", "analysis"))
    wizard.add_argument("--iso", required=True)
    wizard.add_argument("--sha256", required=True, help="Checksum from the official publisher")
    wizard.add_argument("--name")
    wizard.add_argument("--ram-mib", type=int)
    wizard.add_argument("--vcpus", type=int)
    wizard.add_argument("--disk-gib", type=int)
    backup = sub.add_parser("backup", help="Cold VM backup plan/create and integrity verification")
    backup_actions = backup.add_subparsers(dest="backup_action")
    bp = backup_actions.add_parser("plan", help="Verify shutdown and show eligible backup assets")
    bp.add_argument("key", help="Bound workspace key, such as pentest or analysis")
    bc = backup_actions.add_parser("create", help="Make a NEW offline backup; never overwrite")
    bc.add_argument("key", help="Bound VM workspace key")
    bc.add_argument("destination", help="New, nonexistent backup directory")
    bc.add_argument("--yes", action="store_true", help="Explicitly confirm backup creation")
    bv = backup_actions.add_parser("verify", help="Read-only SHA-256 integrity checks")
    bv.add_argument("directory", help="Existing Nightglass backup folder")
    recover = sub.add_parser("recover", help="Stage cold backups as NEW, disconnected, unregistered VMs")
    recover_actions = recover.add_subparsers(dest="recover_action")
    recover_plan = recover_actions.add_parser("plan", help="Read-only verified recovery plan")
    recover_plan.add_argument("backup", help="Existing Nightglass cold backup folder")
    recover_plan.add_argument("destination", help="NEW, nonexistent recovery destination")
    recover_plan.add_argument("new_name", help="NEW, unique libvirt guest name")
    recover_stage = recover_actions.add_parser("stage", help="Copy verified backup into a NEW isolated staging area")
    recover_stage.add_argument("backup")
    recover_stage.add_argument("destination")
    recover_stage.add_argument("new_name")
    recover_stage.add_argument("--yes", action="store_true", help="Confirm staging without a terminal prompt")
    recover_verify = recover_actions.add_parser("verify", help="Re-verify staging hashes and offline XML")
    recover_verify.add_argument("directory")
    recover_preflight = recover_actions.add_parser("preflight", help="Read-only Fedora/KVM import readiness check")
    recover_preflight.add_argument("directory")
    args = parser.parse_args(argv)
    cmd = args.command or "gui"
    try:
        if cmd == "recover":
            if args.recover_action == "preflight":
                print(RecoveryReadiness().check(Path(args.directory)).describe())
                return 0
            if args.recover_action == "verify":
                for line in verify_staging(Path(args.directory)):
                    print(line)
                print("Staged files and offline XML verified. VM is NOT defined or boot-tested.")
                return 0
            if args.recover_action not in {"plan", "stage"}:
                parser.error("Choose recover plan, recover stage, recover verify or recover preflight")
            worker = RecoveryStager()
            plan = worker.plan(
                Path(args.backup), Path(args.destination), args.new_name
            )
            print(plan.describe())
            if args.recover_action == "plan":
                return 0
            if not args.yes:
                if not sys.stdin.isatty() or input("Type STAGE to create a new recovery copy: ").strip() != "STAGE":
                    print("Cancelled; no files created.")
                    return 1
            dest = worker.stage(
                Path(args.backup), Path(args.destination), args.new_name, confirmed=True
            )
            print(f"New offline recovery staged: {dest}")
            print("Next: inspect domain.xml, permissions, firmware and SELinux, then import manually.")
            return 0
        if cmd == "backup":
            if args.backup_action == "verify":
                for line in verify_backup(Path(args.directory)):
                    print(line)
                print("Integrity checked; test a real restore before relying on this copy.")
                return 0
            if args.backup_action not in {"plan", "create"}:
                parser.error("Choose backup plan, backup create or backup verify")
            space = next((s for s in load_workspaces() if s.key == args.key), None)
            if space is None or space.kind != "vm" or space.policy not in {"lab", "isolated"}:
                parser.error("Choose a configured isolated or lab VM workspace")
            service = ColdBackup()
            plan = service.plan(space.identifier, space.policy)
            print(plan.describe())
            if args.backup_action == "plan":
                return 0
            if not args.yes:
                if not sys.stdin.isatty() or input("Type BACKUP to copy the powered-off VM: ").strip() != "BACKUP":
                    print("Cancelled. No backup created.")
                    return 1
            directory = service.create(
                space.identifier, space.policy, Path(args.destination), confirmed=True
            )
            print(f"Cold backup saved at: {directory}")
            print("Verify the backup with: nightglass backup verify", directory)
            return 0
        if cmd == "provision":
            plan = build_plan(
                args.kind, args.iso, args.sha256, name=args.name,
                ram_mib=args.ram_mib, vcpus=args.vcpus, disk_gib=args.disk_gib,
            )
            print(OfflineProvisioner().preview(plan).describe())
            return 0
        if cmd == "profile":
            if args.profile_action in (None, "show"):
                print(current_budget().explain())
                return 0
            current = load_machine_preferences()
            ram = total_ram_gib()
            # The selected mode is only a *preference*: the effective limits
            # are always clamped to actual host capacity on every VM launch.
            preset = MachinePreferences(
                preset=args.target,
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
