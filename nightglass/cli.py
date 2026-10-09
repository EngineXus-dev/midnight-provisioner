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
from .kali_templates import get_template, list_templates, plan_template
from .kali_setup import (
    build_setup_plan, save_setup_plan, load_setup_plan,
    compare_inventory_files, save_version_lock, guest_inventory_instructions,
)
from .kali_drift import compare_version_lock_files, save_drift_review
from .kali_preflight import KaliPreflight
from .kali_registration import KaliRegistrationInspector, save_registration_report
from .kali_cold_baseline import KaliColdBaselineInspector, save_cold_baseline_report
from .kali_recovery_link import KaliRecoveryLink, save_kali_recovery_link
from .kali_recovery_registration import KaliRecoveryRegistrationInspector, save_registered_recovery
from .kali_running import KaliRunningInspector, save_kali_running_observation
from .backups import ColdBackup, verify_backup
from .recovery import RecoveryStager, verify_staging
from .readiness import RecoveryReadiness
from .acceptance import RegisteredGuestAuditor, save_acceptance
from .runtime_labels import RuntimeLabelInspector, save_runtime_observation
from .handoff import RecoveryHandoff, save_handoff
from .resources import collect_resources
from .host_posture import inspect_host_posture
import os


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="nightglass", description="Nightglass secure-workspace controller")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("doctor", help="Read-only host readiness checks")
    sub.add_parser("resources", help="Inspect live host RAM pressure and active system libvirt VMs (read-only)")
    sub.add_parser("host-security", help="Review Fedora SELinux/KVM/firewall posture without changes")
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
    template_cli = sub.add_parser("templates", help="Browse curated independent Kali VM tool profiles (read-only)")
    template_commands = template_cli.add_subparsers(dest="template_action")
    template_list = template_commands.add_parser("list", help="List all white-hat and red-team templates")
    template_list.add_argument("--category", choices=("white-hat", "red-team"))
    template_show = template_commands.add_parser("show", help="Show exact packages and offline resource defaults")
    template_show.add_argument("identifier")
    template_export = template_commands.add_parser("export", help="Create a NEW private offline guest setup plan (no installation)")
    template_export.add_argument("identifier")
    template_export.add_argument("destination", type=Path)
    template_export.add_argument("--guest", help="Independent registered VM name; no VM is created")
    template_export.add_argument("--iso-sha256", help="Optional user-claimed publisher digest (NOT reverified here)")
    template_verify = template_commands.add_parser("verify", help="Check a setup plan for catalog/policy drift")
    template_verify.add_argument("plan", type=Path)
    template_compare = template_commands.add_parser("compare", help="Compare plan to manually supplied guest package inventory JSON")
    template_compare.add_argument("plan", type=Path)
    template_compare.add_argument("inventory", type=Path)
    template_lock = template_commands.add_parser("lock", help="Record guest-reported version snapshot in a NEW private file")
    template_lock.add_argument("plan", type=Path)
    template_lock.add_argument("inventory", type=Path)
    template_lock.add_argument("destination", type=Path)
    template_guest = template_commands.add_parser("guest-help", help="Show safe manual offline inventory collection steps for one Kali VM")
    template_guest.add_argument("identifier")
    template_drift = template_commands.add_parser(
        "drift", help="Read-only review of Kali guest versions against a previous private snapshot"
    )
    template_drift.add_argument("plan", type=Path)
    template_drift.add_argument("lock", type=Path)
    template_drift.add_argument("inventory", type=Path)
    template_drift.add_argument("--report", type=Path, help="Write optional NEW private JSON evidence")
    template_preflight = template_commands.add_parser(
        "preflight", help="Read-only Kali ISO, two-stage VM XML, host RAM and storage readiness"
    )
    template_preflight.add_argument("plan", type=Path, help="Existing catalog-verified Kali setup manifest")
    template_preflight.add_argument("--iso", type=Path, required=True)
    template_preflight.add_argument("--storage-dir", type=Path, required=True,
                                    help="Existing destination volume directory; nothing is created")
    template_registered = template_commands.add_parser(
        "registered", help="Read-only audit of a manually installed, powered-off Kali template VM"
    )
    template_registered.add_argument("plan", type=Path, help="Existing private Kali template setup plan")
    template_registered.add_argument("--disk", type=Path, required=True,
                                     help="Exact absolute path to its own existing qcow2 disk")
    template_registered.add_argument("--report", type=Path,
                                     help="Write optional NEW private, non-sensitive JSON evidence")
    template_baseline = template_commands.add_parser(
        "baseline", help="Read-only binding of a shut-off Kali template to verified cold backup files"
    )
    template_baseline.add_argument("plan", type=Path)
    template_baseline.add_argument("--disk", type=Path, required=True,
                                   help="Exact registered Kali qcow2 disk path")
    template_baseline.add_argument("--backup", type=Path, required=True,
                                   help="Existing Nightglass cold backup directory")
    template_baseline.add_argument("--report", type=Path,
                                   help="Optional NEW private metadata report, never overwritten")
    template_recovery = template_commands.add_parser(
        "recovery-link", help="Read-only match of original Kali cold backup to its independent offline recovery copy"
    )
    template_recovery.add_argument("plan", type=Path, help="Existing curated Kali guest setup plan")
    template_recovery.add_argument("--backup", type=Path, required=True,
                                   help="Original verified cold backup folder")
    template_recovery.add_argument("--staged", type=Path, required=True,
                                   help="Existing separately staged NEW recovered guest folder")
    template_recovery.add_argument("--report", type=Path,
                                   help="Optional NEW private metadata evidence file")
    registered_recovery = template_commands.add_parser(
        "recovery-registered",
        help="Read-only check of manually registered, shut-off Kali recovery VM against backup and stage"
    )
    registered_recovery.add_argument("plan", type=Path)
    registered_recovery.add_argument("--backup", type=Path, required=True)
    registered_recovery.add_argument("--staged", type=Path, required=True)
    registered_recovery.add_argument("--report", type=Path,
                                     help="Optional NEW private recovery handoff evidence")
    runtime_observe = template_commands.add_parser(
        "observe-running",
        help="Read-only sVirt/device observation for a manually running benign Kali recovery guest"
    )
    runtime_observe.add_argument("plan", type=Path)
    runtime_observe.add_argument("--backup", type=Path, required=True)
    runtime_observe.add_argument("--guest", required=True,
                                 help="Different manually started recovery VM guest name")
    runtime_observe.add_argument("--disk", type=Path, required=True,
                                 help="Exact selected running guest qcow2 path (NOT hashed)")
    runtime_observe.add_argument("--report", type=Path,
                                 help="Optional NEW private observation JSON report")
    wizard = sub.add_parser("provision", help="Read-only VM ISO integrity and guest XML preflight")
    wizard.add_argument("kind", choices=("pentest", "analysis"))
    wizard.add_argument("--iso", required=True)
    wizard.add_argument("--sha256", required=True, help="Checksum from the official publisher")
    wizard.add_argument("--name")
    wizard.add_argument("--ram-mib", type=int)
    wizard.add_argument("--vcpus", type=int)
    wizard.add_argument("--disk-gib", type=int)
    wizard.add_argument("--template", help="Optional curated Kali template ID, pentest guests only")
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
    recover_handoff = recover_actions.add_parser("handoff", help="Read-only comparison of a registered VM with its verified recovery staging")
    recover_handoff.add_argument("directory")
    recover_handoff.add_argument("--report", type=Path, help="Save private evidence to a NEW local JSON file")
    runtime = sub.add_parser("runtime-label", help="Observe libvirt sVirt label metadata of an ALREADY-running guest (read-only)")
    runtime.add_argument("guest", help="Exact registered VM name; never starts guest")
    runtime.add_argument("--policy", choices=("isolated", "lab"), default="isolated")
    runtime.add_argument("--report", type=Path, help="Save private evidence to a NEW local JSON file")
    accept = sub.add_parser("accept", help="Read-only inspection of an ACTUAL registered libvirt guest")
    accept.add_argument("guest", help="Exact libvirt domain name")
    accept.add_argument("--policy", choices=("isolated", "lab"), default="isolated")
    accept.add_argument("--report", type=Path, help="Save private evidence to a NEW local JSON file")
    args = parser.parse_args(argv)
    cmd = args.command or "gui"
    try:
        if cmd == "templates":
            if args.template_action == "observe-running":
                report = KaliRunningInspector().inspect(
                    args.plan, args.backup, args.guest, args.disk
                )
                print(report.describe())
                if args.report:
                    print("NEW private metadata observation:", save_kali_running_observation(report, args.report))
                return 0 if report.ok else 2
            if args.template_action == "recovery-registered":
                report = KaliRecoveryRegistrationInspector().inspect(
                    args.plan, args.backup, args.staged
                )
                print(report.describe())
                if args.report:
                    print("Private registered recovery metadata:", save_registered_recovery(report, args.report))
                return 0 if report.ok else 2
            if args.template_action == "recovery-link":
                report = KaliRecoveryLink().inspect(args.plan, args.backup, args.staged)
                print(report.describe())
                if args.report:
                    print("Private Kali recovery linkage evidence:", save_kali_recovery_link(report, args.report))
                return 0 if report.ok else 2
            if args.template_action == "baseline":
                report = KaliColdBaselineInspector().inspect(args.plan, args.disk, args.backup)
                print(report.describe())
                if args.report:
                    print("NEW private baseline evidence:", save_cold_baseline_report(report, args.report))
                return 0 if report.ok else 2
            if args.template_action == "registered":
                report = KaliRegistrationInspector().inspect(args.plan, args.disk)
                print(report.describe())
                if args.report:
                    print("Private local metadata record:", save_registration_report(report, args.report))
                return 0 if report.ok else 2
            if args.template_action == "preflight":
                report = KaliPreflight().inspect(args.plan, args.iso, args.storage_dir)
                print(report.describe())
                return 0 if report.ok else 2
            if args.template_action == "drift":
                report = compare_version_lock_files(args.plan, args.lock, args.inventory)
                print(report.describe())
                if args.report:
                    print("Private self-reported metadata report:", save_drift_review(report, args.report))
                return 0 if report.unchanged else 2
            if args.template_action == "guest-help":
                print(guest_inventory_instructions(args.identifier))
                return 0
            if args.template_action == "export":
                plan = build_setup_plan(
                    args.identifier, guest=args.guest, iso_sha256=args.iso_sha256
                )
                print("NEW private offline-only Kali setup plan:", save_setup_plan(plan, args.destination))
                print("Package versions are UNKNOWN; no guest or host software was installed.")
                return 0
            if args.template_action == "verify":
                plan = load_setup_plan(args.plan)
                print(
                    f"PLANNED ONLY — catalog and offline defaults match: "
                    f"{plan['template_id']} for {plan['guest']}. No installation verified."
                )
                return 0
            if args.template_action == "compare":
                report = compare_inventory_files(args.plan, args.inventory)
                print(report.describe())
                return 0 if report.complete else 2
            if args.template_action == "lock":
                target = save_version_lock(args.plan, args.inventory, args.destination)
                print("NEW private version snapshot (UNTRUSTED GUEST EXPORT):", target)
                print("Not a proof of installed package origin, dependencies or rollback.")
                return 0
            if args.template_action == "show":
                print(get_template(args.identifier).describe())
                return 0
            if args.template_action in (None, "list"):
                for entry in list_templates(args.category if args.template_action == "list" else None):
                    print(
                        f"{entry.identifier:16s} {entry.category:10s} "
                        f"{entry.name} ({len(entry.packages)} tools; {entry.ram_mib} MiB)"
                    )
                print("PLANS ONLY: each template uses a separate, disconnected Kali VM.")
                return 0
            parser.error("Choose templates list, show, export, verify, compare, lock, drift, preflight, registered, baseline, recovery-link, recovery-registered, observe-running or guest-help")
        if cmd == "runtime-label":
            report = RuntimeLabelInspector().inspect(args.guest, args.policy)
            print(report.describe())
            if args.report:
                print(f"Private local metadata evidence: {save_runtime_observation(report, args.report)}")
            return 0 if report.ok else 2
        if cmd == "host-security":
            posture = inspect_host_posture()
            print(posture.describe())
            return 0 if posture.complete else 2
        if cmd == "resources":
            snapshot = collect_resources(workspaces=load_workspaces())
            print(snapshot.describe())
            return 0 if snapshot.level == "NORMAL" else 2
        if cmd == "accept":
            audit = RegisteredGuestAuditor().inspect(args.guest, args.policy)
            print(audit.describe())
            if args.report:
                target = save_acceptance(audit, args.report)
                print(f"Read-only evidence saved locally: {target}")
            return 0 if audit.ok else 2
        if cmd == "recover":
            if args.recover_action == "handoff":
                handoff = RecoveryHandoff().inspect(Path(args.directory))
                print(handoff.describe())
                if args.report:
                    print(f"Private local evidence: {save_handoff(handoff, args.report)}")
                return 0 if handoff.ok else 2
            if args.recover_action == "preflight":
                print(RecoveryReadiness().check(Path(args.directory)).describe())
                return 0
            if args.recover_action == "verify":
                for line in verify_staging(Path(args.directory)):
                    print(line)
                print("Staged files and offline XML verified. VM is NOT defined or boot-tested.")
                return 0
            if args.recover_action not in {"plan", "stage"}:
                parser.error("Choose recover plan, recover stage, recover verify, recover preflight or recover handoff")
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
            if args.template and args.kind != "pentest":
                raise ToolError("Curated Kali templates are only for pentest guests, not analysis VMs")
            plan = (
                plan_template(
                    args.template, args.iso, args.sha256, name=args.name,
                    ram_mib=args.ram_mib, vcpus=args.vcpus, disk_gib=args.disk_gib,
                ) if args.template else build_plan(
                    args.kind, args.iso, args.sha256, name=args.name,
                    ram_mib=args.ram_mib, vcpus=args.vcpus, disk_gib=args.disk_gib,
                )
            )
            print(OfflineProvisioner().preview(plan).describe())
            if args.template:
                print("\n" + get_template(args.template).describe())
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
