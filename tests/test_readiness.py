"""No-privilege tests for import-readiness checks on a staged new guest."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from nightglass.portability import budget_for
from nightglass.readiness import RecoveryReadiness
from nightglass.runner import Output, ToolError


XML_TEMPLATE = """<domain type="kvm">
<name>nightglass-recovered</name><memory unit="MiB">2048</memory>
<devices><graphics type="vnc" listen="127.0.0.1"/>
<disk type="file" device="disk"><driver name="qemu" type="qcow2"/>
<source file="__DISK__"/></disk></devices></domain>"""


class FakeHypervisor:
    def __init__(self, names=()):
        self.names = list(names)
        self.calls = 0

    def list_domains(self):
        self.calls += 1
        return list(self.names)


class FakeRunner:
    def __init__(self, **img):
        self.img = img or {"format": "qcow2", "virtual-size": 1024 * 1024}
        self.calls = []
        self.schema_error = None

    def run(self, argv, timeout=12):
        self.calls.append(tuple(argv))
        if argv[0] == "virt-xml-validate":
            if self.schema_error is not None:
                raise ToolError(self.schema_error)
            return Output("validated")
        if argv[:3] == ["qemu-img", "info", "--output=json"]:
            return Output(json.dumps(self.img))
        raise AssertionError(f"Unexpected command: {argv}")


class ReadinessTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name) / "recovered guest"
        self.dir.mkdir()
        (self.dir / "disks").mkdir()
        self.disk = self.dir / "disks" / "disk-01.qcow2"
        self.disk.write_bytes(b"synthetic test image only" * 512)
        self.xml = self.dir / "domain.xml"
        self.xml.write_text(
            XML_TEMPLATE.replace("__DISK__", str(self.disk)), encoding="utf-8"
        )
        self.manifest = self.dir / "recovery-manifest.json"
        self.reset_manifest()
        self.runner = FakeRunner()
        self.hv = FakeHypervisor()
        self.service = RecoveryReadiness(self.runner, self.hv)

    def reset_manifest(self):
        def record(path, rel, kind):
            data = path.read_bytes()
            return {
                "path": rel,
                "kind": kind,
                "bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
        self.manifest.write_text(json.dumps({
            "format": "nightglass-recovery-staging",
            "version": 1,
            "guest": "nightglass-recovered",
            "original_guest": "original-guest",
            "original_policy": "isolated",
            "network": "offline",
            "files": [
                record(self.disk, "disks/disk-01.qcow2", "disk"),
                record(self.xml, "domain.xml", "xml"),
            ],
        }), encoding="utf-8")

    def check(self):
        with patch("nightglass.readiness.platform.system", return_value="Linux"), \
             patch("nightglass.readiness.os.path.exists", return_value=True), \
             patch("nightglass.readiness.os.access", return_value=True), \
             patch("nightglass.readiness.current_budget", return_value=budget_for(8, 6)):
            return self.service.check(self.dir)

    def test_readiness_never_mutates_or_defines_guest(self):
        before = self.disk.read_bytes()
        report = self.check()
        self.assertEqual(report.disks, 1)
        self.assertEqual(report.guest, "nightglass-recovered")
        self.assertIn("NO VM WAS DEFINED", report.describe())
        self.assertEqual(self.disk.read_bytes(), before)
        verbs = [x[0] for x in self.runner.calls]
        self.assertEqual(verbs, ["virt-xml-validate", "qemu-img"])
        self.assertIn("domain", self.runner.calls[0])
        self.assertEqual(self.runner.calls[1][:3], ("qemu-img", "info", "--output=json"))

    def test_registered_name_blocks_before_any_native_tool(self):
        self.hv.names = ["nightglass-recovered"]
        with self.assertRaisesRegex(ToolError, "already registered"):
            self.check()
        self.assertEqual(self.runner.calls, [])

    def test_schema_validation_must_pass(self):
        self.runner.schema_error = "Invalid libvirt XML schema"
        with self.assertRaisesRegex(ToolError, "Invalid libvirt XML"):
            self.check()
        self.assertEqual([c[0] for c in self.runner.calls], ["virt-xml-validate"])

    def test_image_formats_must_match(self):
        self.runner.img = {"format": "raw"}
        with self.assertRaisesRegex(ToolError, "format mismatch"):
            self.check()

    def test_declared_raw_driver_on_qcow2_disk_fails_before_native_tools(self):
        # Recompute the staged manifest to model an internally consistent
        # but semantically unsafe XML definition.
        self.xml.write_text(
            self.xml.read_text(encoding="utf-8").replace(
                'type="qcow2"', 'type="raw"'
            ), encoding="utf-8"
        )
        self.reset_manifest()
        with self.assertRaisesRegex(ToolError, "driver format"):
            self.check()
        self.assertEqual(self.runner.calls, [])

    def test_backing_chain_or_embedded_snapshots_fail(self):
        for variant in (
            {"format": "qcow2", "backing-filename": "/dev/sda"},
            {"format": "qcow2", "snapshots": [{"id": "1"}]},
            {"format": "qcow2", "encrypted": True},
        ):
            with self.subTest(variant=variant):
                self.runner.img = variant
                with self.assertRaisesRegex(ToolError, "manual review"):
                    self.check()

    def test_corrupted_disk_fails_before_qemu_tools(self):
        self.disk.write_bytes(b"modified")
        with self.assertRaisesRegex(ToolError, "integrity failure"):
            self.check()
        self.assertEqual(self.runner.calls, [])

    def test_oversized_guest_fails_before_claiming_readiness(self):
        self.xml.write_text(
            self.xml.read_text().replace('unit="MiB">2048', 'unit="GiB">5'),
            encoding="utf-8",
        )
        self.reset_manifest()
        with self.assertRaisesRegex(ToolError, "exceeds"):
            self.check()

    def test_network_interface_still_fails_with_matching_manifest(self):
        self.xml.write_text(
            self.xml.read_text().replace("</devices>",
                '<interface type="network"><source network="default"/></interface></devices>'),
            encoding="utf-8",
        )
        self.reset_manifest()
        with self.assertRaisesRegex(ToolError, "offline policy"):
            self.check()
        self.assertEqual(self.runner.calls, [])

    def test_unavailable_kvm_blocks(self):
        with patch("nightglass.readiness.platform.system", return_value="Linux"), \
             patch("nightglass.readiness.os.path.exists", return_value=False):
            with self.assertRaisesRegex(ToolError, "KVM access unavailable"):
                self.service.check(self.dir)

    def test_non_linux_host_blocks(self):
        with patch("nightglass.readiness.platform.system", return_value="Windows"):
            with self.assertRaisesRegex(ToolError, "Fedora/Linux"):
                self.service.check(self.dir)

    def test_conflicting_name_appears_while_preflight_runs(self):
        hv = FakeHypervisor()
        service = RecoveryReadiness(self.runner, hv)
        def changing():
            hv.calls += 1
            return [] if hv.calls == 1 else ["nightglass-recovered"]
        hv.list_domains = changing
        with patch("nightglass.readiness.platform.system", return_value="Linux"), \
             patch("nightglass.readiness.os.path.exists", return_value=True), \
             patch("nightglass.readiness.os.access", return_value=True), \
             patch("nightglass.readiness.current_budget", return_value=budget_for(8, 6)):
            with self.assertRaisesRegex(ToolError, "registered during preflight"):
                service.check(self.dir)


if __name__ == "__main__":
    unittest.main()
