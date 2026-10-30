"""Kali toolkit templates plan SEPARATE disconnected guests; never install tools."""
from __future__ import annotations

import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from midnight_provisioner.cli import main
from midnight_provisioner.kali_templates import (
    CATALOG, KaliTemplate, get_template, list_templates, plan_template,
)
from midnight_provisioner.portability import budget_for
from midnight_provisioner.runner import ToolError

VALID_SHA = "a" * 64


class KaliTemplateTests(unittest.TestCase):
    def setUp(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        self.iso = Path(td.name) / "kali-installer.iso"
        # Synthetic file for path/size checks only; native tools aren't called.
        with self.iso.open("wb") as stream:
            stream.truncate(16 * 1024 * 1024)
        self.low = budget_for(8.0, 6)
        self.tiny = budget_for(5.0, 2)

    def test_catalog_has_distinct_separate_guests_for_red_and_white_hat(self):
        self.assertGreaterEqual(len(CATALOG), 6)
        self.assertEqual(len({t.identifier for t in CATALOG}), len(CATALOG))
        self.assertEqual(len({t.default_name for t in CATALOG}), len(CATALOG))
        self.assertEqual({t.category for t in CATALOG}, {"white-hat", "red-team"})
        self.assertTrue(all(t.default_name.startswith("midnight-provisioner-kali-") for t in CATALOG))
        self.assertTrue(all(1 <= len(t.packages) <= 7 for t in CATALOG))

    def test_no_everything_or_large_metapackage_and_no_default_network(self):
        for template in CATALOG:
            with self.subTest(template=template.identifier):
                self.assertFalse(any(pkg.startswith(("kali-linux-", "kali-tools-"))
                                     for pkg in template.packages))
                self.assertNotIn("apt full-upgrade", template.install_preview())
                self.assertNotIn("curl |", template.install_preview())
                self.assertIn("no-install-recommends", template.install_preview())
                self.assertIn("Connectivity: NONE", template.describe())
                self.assertIn("separate", template.describe().lower())

    def test_authorized_templates_have_conservative_low_ram_defaults(self):
        for template in CATALOG:
            with self.subTest(template=template.identifier):
                plan = plan_template(
                    template.identifier, self.iso, VALID_SHA, budget=self.low,
                )
                self.assertEqual(plan.kind, "pentest")
                self.assertEqual(plan.policy, "lab")
                self.assertEqual(plan.name, template.default_name)
                self.assertLessEqual(plan.ram_mib, int(self.low.guest_ram_cap_gib * 1024))
                self.assertLessEqual(plan.vcpus, self.low.vcpu_cap)
                self.assertEqual(plan.disk_gib, template.disk_gib)
                cmd = plan.command()
                self.assertEqual(cmd[cmd.index("--network") + 1], "none")
                self.assertEqual(cmd[cmd.index("--graphics") + 1], "vnc,listen=127.0.0.1")
                self.assertNotIn("apt", " ".join(cmd))
                self.assertNotIn("define", " ".join(cmd))
                self.assertNotIn("start", " ".join(cmd))

    def test_5_gb_budget_clamps_kali_and_single_cpu(self):
        for template in CATALOG:
            p = plan_template(template.identifier, self.iso, VALID_SHA, budget=self.tiny)
            self.assertLessEqual(p.ram_mib, 1024)
            self.assertEqual(p.vcpus, 1)
            self.assertEqual(p.disk_gib, template.disk_gib)

    def test_per_template_renaming_possible_but_original_never_reused_by_default(self):
        a = plan_template("recon", self.iso, VALID_SHA, budget=self.low)
        b = plan_template("web-audit", self.iso, VALID_SHA, budget=self.low)
        self.assertNotEqual(a.name, b.name)
        custom = plan_template("recon", self.iso, VALID_SHA, name="approved-recon-b", budget=self.low)
        self.assertEqual(custom.name, "approved-recon-b")

    def test_iso_must_exist_checksum_must_validate_and_disk_budget_enforced(self):
        with self.assertRaisesRegex(ToolError, "64-character"):
            plan_template("recon", self.iso, "invalid", budget=self.low)
        with self.assertRaisesRegex(ToolError, "Cannot access"):
            plan_template("recon", self.iso.parent / "missing.iso", VALID_SHA, budget=self.low)
        with self.assertRaisesRegex(ToolError, "disk"):
            plan_template("recon", self.iso, VALID_SHA, disk_gib=400, budget=self.low)

    def test_dangerous_or_broad_template_definitions_fail_validation(self):
        base = dict(
            identifier="example", name="Example", category="white-hat",
            purpose="test", packages=("nmap",), ram_mib=1024,
            disk_gib=24, vcpus=1, caution="Restricted",
        )
        for pkg in ("kali-linux-everything", "kali-tools-web", "nmap;evil", "--force"):
            with self.subTest(package=pkg), self.assertRaises(ValueError):
                KaliTemplate(**{**base, "packages": (pkg,)})
        with self.assertRaises(ValueError):
            KaliTemplate(**{**base, "packages": ("nmap",) * 8})

    def test_unknown_profile_rejected_without_disk_or_host_ops(self):
        with self.assertRaisesRegex(ToolError, "Unknown Kali template"):
            get_template("does-not-exist")
        with self.assertRaisesRegex(ToolError, "white-hat or red-team"):
            list_templates("untrusted")

    def test_cli_catalog_and_detail_do_not_call_installer_or_libvirt(self):
        from contextlib import redirect_stdout
        from io import StringIO
        out = StringIO()
        with patch("midnight_provisioner.cli.OfflineProvisioner") as provision, \
             redirect_stdout(out):
            self.assertEqual(main(["templates", "list", "--category", "red-team"]), 0)
            self.assertIn("red-team", out.getvalue())
            self.assertNotIn("defense", out.getvalue())
            provision.assert_not_called()
        out = StringIO()
        with redirect_stdout(out):
            self.assertEqual(main(["templates", "show", "web-audit"]), 0)
            self.assertIn("sudo apt install", out.getvalue())
            self.assertIn("TEMPLATE PLAN", out.getvalue())

    def test_cli_rejects_attaching_kali_template_to_malware_analysis_guest(self):
        from contextlib import redirect_stderr
        from io import StringIO
        err = StringIO()
        with patch("midnight_provisioner.cli.OfflineProvisioner") as provision, \
             redirect_stderr(err):
            self.assertEqual(main([
                "provision", "analysis", "--template", "recon",
                "--iso", str(self.iso), "--sha256", VALID_SHA,
            ]), 2)
            provision.assert_not_called()
            self.assertIn("not analysis VMs", err.getvalue())


if __name__ == "__main__":
    unittest.main()
