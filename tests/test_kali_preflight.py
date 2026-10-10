"""Read-only Kali installer, existing VM and host pressure readiness tests."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from nightglass.kali_preflight import GIB, KaliPreflight
from nightglass.kali_setup import build_setup_plan, save_setup_plan
from nightglass.portability import budget_for
from nightglass.provisioning import OfflineProvisioner, MIN_ISO_BYTES
from nightglass.resources import MemoryPressure, ResourceSnapshot
from nightglass.runner import Output, ToolError


def domain(name, extra=""):
    return (
        '<domain type="kvm"><name>' + name + '</name>'
        '<memory unit="MiB">2048</memory><devices>'
        '<graphics type="vnc" listen="127.0.0.1"/>' + extra
        + '</devices></domain>'
    )


# Native Windows cannot perform POSIX fchmod. Isolate this capability only
# while running synthetic module tests; production Linux enforcement is intact.
_fixture_mode_patch = None


def setUpModule():
    global _fixture_mode_patch
    if os.name == "nt":
        _fixture_mode_patch = patch("nightglass.kali_setup.os.fchmod", create=True)
        _fixture_mode_patch.start()


def tearDownModule():
    global _fixture_mode_patch
    if _fixture_mode_patch is not None:
        _fixture_mode_patch.stop()
        _fixture_mode_patch = None


class FakeRunner:
    def __init__(self, *, unsafe_second=False):
        self.calls = []
        self.unsafe_second = unsafe_second

    def run(self, argv, timeout=120):
        self.calls.append(tuple(argv))
        if argv[0] != "virt-install":
            raise AssertionError("Unexpected native command")
        if "--dry-run" not in argv or "--print-xml" not in argv:
            raise AssertionError("Unsafe virt-install invocation")
        name = argv[argv.index("--name") + 1]
        stage = int(argv[-1])
        extra = '<interface type="bridge"/>' if stage == 2 and self.unsafe_second else ""
        return Output(domain(name, extra))


class FakeHV:
    def __init__(self, existing=False):
        self.existing = existing
        self.calls = []

    def list_domains(self):
        self.calls.append("list")
        return ["nightglass-kali-recon"] if self.existing else []


class KaliPreflightTests(unittest.TestCase):
    def setUp(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        self.folder = Path(td.name)
        self.iso = self.folder / "official-local-test.iso"
        with self.iso.open("wb") as fh:
            fh.truncate(MIN_ISO_BYTES)
        sha = hashlib.sha256(self.iso.read_bytes()).hexdigest()
        self.plan_path = self.folder / "new-private-plan.json"
        self.plan = build_setup_plan("recon", iso_sha256=sha)
        save_setup_plan(self.plan, self.plan_path)
        self.budget = budget_for(8, 6)
        self.runner = FakeRunner()
        self.hv = FakeHV()
        self.preview = OfflineProvisioner(self.runner, self.hv)
        self.snapshot = self.resources()

    def resources(self, *, available=5.5, states=(), level="NORMAL",
                  libvirt=True, budget=None):
        budget = budget or self.budget
        return ResourceSnapshot(
            memory=MemoryPressure(8.0, available, 2.0, 0.0),
            budget=budget, active_vms=tuple(states), unbound_vms=(),
            libvirt_available=libvirt, level=level, warnings=(),
        )

    def audit(self, *, snapshot=None, disk_free=30 * GIB, storage=None):
        return KaliPreflight(
            provisioner=self.preview, budget=self.budget,
            snapshot=snapshot if snapshot is not None else self.snapshot,
            disk_usage=lambda directory: SimpleNamespace(free=disk_free),
        ).inspect(self.plan_path, self.iso, storage or self.folder)

    def test_complete_healthy_preview_is_read_only_and_explicitly_not_a_boot_pass(self):
        report = self.audit()
        self.assertTrue(report.ok, report.describe())
        self.assertEqual(report.dry_run_stages, 2)
        self.assertEqual(report.verified_iso_digest, self.plan["claimed_installer_iso_sha256"])
        self.assertEqual(len(self.runner.calls), 2)
        self.assertIn("MANUAL REVIEW ONLY", report.describe())
        self.assertIn("not reserve space", report.describe())
        self.assertIn("No host/guest access", report.describe())
        self.assertFalse(any(
            "--start" in call or "--autostart" in call or "--install" in call
            for command in self.runner.calls for call in command
        ))
        for command in self.runner.calls:
            self.assertEqual(command[command.index("--network") + 1], "none")
            self.assertEqual(command[command.index("--graphics") + 1], "vnc,listen=127.0.0.1")

    def test_missing_official_digest_blocks_before_iso_or_native_processes(self):
        missing = self.folder / "missing-digest.json"
        save_setup_plan(build_setup_plan("recon"), missing)
        self.plan_path = missing
        report = self.audit()
        self.assertFalse(report.ok)
        self.assertIn("--iso-sha256", report.describe())
        self.assertEqual(self.runner.calls, [])
        self.assertEqual(self.hv.calls, [])

    def test_storage_headroom_heuristic_and_sparse_expansion_caution(self):
        report = self.audit(disk_free=5 * GIB)
        self.assertFalse(report.ok)
        self.assertIn("headroom heuristic", report.describe())
        self.assertEqual(self.runner.calls, [])
        report = self.audit(disk_free=10 * GIB)
        self.assertTrue(report.ok)
        self.assertIn("smaller than possible full qcow2 expansion", report.describe())

    def test_storage_directory_symlink_or_nonexistent_path_rejected(self):
        alias = self.folder / "linked-storage"
        try:
            alias.symlink_to(self.folder, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("OS denies creation of synthetic symlinks")
        self.assertIn("symlink", self.audit(storage=alias).describe())
        self.assertFalse(self.audit(storage=alias).ok)
        self.assertFalse(self.audit(storage=self.folder / "missing").ok)
        self.assertEqual(self.runner.calls, [])

    def test_unknown_memory_prevents_green(self):
        report = self.audit(snapshot=self.resources(available=None, level="UNKNOWN"))
        self.assertFalse(report.ok)
        self.assertIn("MemAvailable", report.describe())
        self.assertEqual(self.runner.calls, [])

    def test_guest_ram_allocation_needs_host_breathing_room(self):
        result = self.audit(snapshot=self.resources(available=2.5, level="CAUTION"))
        self.assertFalse(result.ok)
        self.assertIn("breathing room", result.describe())
        self.assertEqual(self.runner.calls, [])

    def test_existing_active_vm_consumes_one_vm_budget(self):
        result = self.audit(snapshot=self.resources(states=("another-guest",), level="CAUTION"))
        self.assertFalse(result.ok)
        self.assertIn("concurrency limit", result.describe())
        self.assertEqual(self.runner.calls, [])

    def test_uninspectable_libvirt_or_mixed_budget_is_blocked(self):
        self.assertFalse(self.audit(snapshot=self.resources(libvirt=False, level="UNKNOWN")).ok)
        other = budget_for(24, 12)
        report = self.audit(snapshot=self.resources(budget=other))
        self.assertFalse(report.ok)
        self.assertIn("budget disagree", report.describe())
        self.assertEqual(self.runner.calls, [])

    def test_reject_incorrect_iso_digest_after_health_checks(self):
        from nightglass.kali_setup import build_setup_plan
        bad_plan = self.folder / "wrong-sha.json"
        save_setup_plan(build_setup_plan("recon", iso_sha256="a" * 64), bad_plan)
        self.plan_path = bad_plan
        report = self.audit()
        self.assertFalse(report.ok)
        self.assertIn("SHA-256 mismatch", report.describe())
        self.assertEqual(self.runner.calls, [])

    def test_existing_domain_cannot_be_replaced(self):
        self.hv.existing = True
        report = self.audit()
        self.assertFalse(report.ok)
        self.assertIn("already exists", report.describe())
        self.assertEqual(self.runner.calls, [])

    def test_unsafe_xml_second_stage_fails_closed(self):
        self.runner.unsafe_second = True
        report = self.audit()
        self.assertFalse(report.ok)
        self.assertIn("stage 2", report.describe())
        self.assertEqual(len(self.runner.calls), 2)

    def test_cli_preflight_returns_nonzero_when_blocked_without_vm_creation(self):
        from contextlib import redirect_stdout
        from io import StringIO
        from nightglass.cli import main
        from types import SimpleNamespace
        argv = [
            "templates", "preflight", str(self.plan_path),
            "--iso", str(self.iso), "--storage-dir", str(self.folder),
        ]
        healthy = SimpleNamespace(ok=True, describe=lambda: "DRY-RUN PASSED — MANUAL REVIEW ONLY")
        blocked = SimpleNamespace(ok=False, describe=lambda: "BLOCKED / UNVERIFIED")
        output = StringIO()
        with patch("nightglass.cli.KaliPreflight") as checker, redirect_stdout(output):
            checker.return_value.inspect.return_value = healthy
            self.assertEqual(main(argv), 0)
            checker.return_value.inspect.assert_called_once_with(
                self.plan_path, self.iso, self.folder
            )
            checker.return_value.inspect.return_value = blocked
            self.assertEqual(main(argv), 2)
        self.assertIn("MANUAL REVIEW", output.getvalue())
        self.assertIn("BLOCKED", output.getvalue())
        self.assertEqual(self.runner.calls, [])
        self.assertEqual(self.hv.calls, [])

    def test_invalid_manifests_refused_before_native_queries(self):
        self.plan_path.write_text('{"format":"nightglass-kali-setup-plan","version":1}')
        with self.assertRaises(ToolError):
            self.audit()
        self.assertEqual(self.runner.calls, [])


if __name__ == "__main__":
    unittest.main()
