"""Native-only integration smoke: real libvirt schema and qemu-img, no hypervisor.

All generated images are benign 8 MiB sparse fixtures in a disposable
TemporaryDirectory. Tests skip on ordinary developer machines missing native
tools, but are REQUIRED by the separate native-tools GitHub Actions job.
"""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from xml.etree import ElementTree as ET

from midnight_provisioner.hypervisor import assess_domain
from midnight_provisioner.readiness import inspect_image_metadata
from midnight_provisioner.runner import Runner, ToolError

HERE = Path(__file__).parent
FIXTURE = HERE / "fixtures" / "native-offline-domain.xml"
TOOLS_AVAILABLE = all(shutil.which(tool) for tool in ("virt-xml-validate", "qemu-img"))


@unittest.skipUnless(TOOLS_AVAILABLE, "native libvirt-clients/qemu-utils binaries unavailable")
class NativeToolTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="midnight-provisioner-native-")
        self.addCleanup(tmp.cleanup)
        self.directory = Path(tmp.name)
        self.runner = Runner()

    def call(self, *argv):
        return subprocess.run(argv, capture_output=True, text=True, check=True, timeout=50)

    def test_real_libvirt_schema_accepts_strict_offline_xml(self):
        result = self.call("virt-xml-validate", str(FIXTURE), "domain")
        self.assertEqual(result.returncode, 0, result.stderr)
        xml = FIXTURE.read_text(encoding="utf-8")
        self.assertTrue(assess_domain(xml, "isolated").ok)
        self.assertEqual(len(ET.fromstring(xml).findall("./devices/interface")), 0)

    def test_xml_with_added_network_is_still_schema_valid_but_policy_denied(self):
        xml = FIXTURE.read_text(encoding="utf-8").replace(
            "</devices>",
            '<interface type="network"><source network="default"/>'
            '<model type="virtio"/></interface></devices>',
        )
        file = self.directory / "networked.xml"
        file.write_text(xml, encoding="utf-8")
        # An XML schema alone never checks the intended security boundary.
        self.call("virt-xml-validate", str(file), "domain")
        result = assess_domain(xml, "isolated")
        self.assertFalse(result.ok)
        self.assertTrue(any("network interface" in problem for problem in result.warnings))

    def test_actual_qcow2_image_header_and_no_backing_chain(self):
        path = self.directory / "benign.qcow2"
        self.call("qemu-img", "create", "-f", "qcow2", str(path), "8M")
        meta = inspect_image_metadata(self.runner, path, "qcow2")
        self.assertEqual(meta["format"], "qcow2")
        self.assertGreater(meta["virtual-size"], 0)
        with self.assertRaisesRegex(ToolError, "format mismatch"):
            inspect_image_metadata(self.runner, path, "raw")

    def test_real_raw_image_header_and_filename_format_check(self):
        path = self.directory / "benign.raw"
        self.call("qemu-img", "create", "-f", "raw", str(path), "8M")
        info = inspect_image_metadata(self.runner, path, "raw")
        self.assertEqual(info["format"], "raw")
        self.assertEqual(info["virtual-size"], 8 * 1024 * 1024)

    def test_real_backing_overlay_is_rejected_without_modifying_it(self):
        base = self.directory / "base.qcow2"
        overlay = self.directory / "overlay.qcow2"
        self.call("qemu-img", "create", "-f", "qcow2", str(base), "8M")
        self.call("qemu-img", "create", "-f", "qcow2", "-F", "qcow2",
                  "-b", str(base), str(overlay))
        before = overlay.stat().st_size
        with self.assertRaisesRegex(ToolError, "Layered"):
            inspect_image_metadata(self.runner, overlay, "qcow2")
        self.assertEqual(overlay.stat().st_size, before)

    def test_malformed_native_metadata_is_fail_closed(self):
        with self.assertRaisesRegex(ToolError, "Malformed"):
            class BadRunner:
                def run(self, *args, **kwargs):
                    from midnight_provisioner.runner import Output
                    return Output("not-json")
            inspect_image_metadata(BadRunner(), self.directory / "x.qcow2", "qcow2")


if __name__ == "__main__":
    unittest.main()
