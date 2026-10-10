"""Synthetic /proc QEMU SELinux observations: no live guests, sudo or root."""
from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from nightglass.cli import main
from nightglass.kali_process_label import (
    KaliProcessLabelInspector, save_kali_process_label,
)
from nightglass.kali_setup import build_setup_plan, save_setup_plan
from nightglass.runner import ToolError

OLD = "nightglass-kali-recon"
RECOVERED = "nightglass-kali-recon-rehearsal"
UUID = "12345678-1234-5678-90ab-abcdefabcdef"
MCS = "c101,c209"
LABEL = f"system_u:system_r:svirt_t:s0:{MCS}"
PROCESS_XML = (
    '<seclabel type="dynamic" model="selinux" relabel="yes">'
    f"<label>{LABEL}</label>"
    f"<imagelabel>system_u:object_r:svirt_image_t:s0:{MCS}</imagelabel>"
    "</seclabel>"
)


def guest_xml(*, name=RECOVERED, uuid=UUID, label=PROCESS_XML):
    return (
        f'<domain type="kvm"><name>{name}</name><uuid>{uuid}</uuid>'
        f"{label}<memory unit='MiB'>2048</memory>"
        "<devices><graphics type='vnc' listen='127.0.0.1'/></devices></domain>"
    )


class FakeHypervisor:
    def __init__(self):
        self.current = guest_xml()
        self.state_value = "running"
        self.calls = []

    def _virsh(self, *argv):
        self.calls.append(argv)
        if argv == ("dumpxml", RECOVERED):
            return self.current
        raise AssertionError("Unapproved/mutating virsh operation: " + repr(argv))

    def state(self, guest):
        self.calls.append(("state", guest))
        return self.state_value


class FakeRuntime:
    def __init__(self):
        self.ok = True
        self.state = "running"
        self.calls = []

    def inspect(self, guest, policy):
        self.calls.append((guest, policy))
        return type("Result", (), {
            "ok": self.ok,
            "state": self.state,
            "errors": () if self.ok else ("SELinux metadata unverified",),
        })()


class ProcessLabelTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.plan = self.root / "new-setup-plan.json"
        if os.name == "nt":
            # Windows lacks fchmod. Mock only this POSIX operation in
            # synthetic fixture setup; production permissions remain intact.
            with patch("nightglass.kali_setup.os.fchmod", create=True):
                save_setup_plan(build_setup_plan("recon"), self.plan)
        else:
            save_setup_plan(build_setup_plan("recon"), self.plan)
        self.proc = self.root / "mock-proc"
        self.proc.mkdir()
        self.hv = FakeHypervisor()
        self.runtime = FakeRuntime()
        self.pid_dir = self.make_process(1573)

    def make_process(
        self, pid=1573, name=RECOVERED, uuid=UUID, context=LABEL,
        program="/usr/bin/qemu-system-x86_64", start="97123",
    ):
        parent = self.proc / str(pid)
        (parent / "attr").mkdir(parents=True, exist_ok=True)
        args = [program, "-name", f"guest={name},debug-threads=on", "-uuid", uuid]
        (parent / "cmdline").write_bytes(
            b"\0".join(arg.encode("utf-8") for arg in args) + b"\0"
        )
        # field 3 is S (index 0); field 22 is index 19 after ") ".
        # Exactly 18 filler values between S and starttime.
        (parent / "stat").write_text(
            str(pid) + " (qemu-system-x86_64) S " + " ".join(["0"] * 18 + [start])
        )
        (parent / "attr/current").write_bytes(context.encode() + b"\0")  # real kernel format
        return parent

    def inspect(self):
        return KaliProcessLabelInspector(
            hypervisor=self.hv, runtime=self.runtime, proc_root=self.proc
        ).inspect(self.plan, RECOVERED)

    def test_linux_proc_stat_starttime_field_22_fixture_is_exact(self):
        from nightglass.kali_process_label import _start_time
        self.assertEqual(_start_time(self.pid_dir), "97123")
        fields = (self.pid_dir / "stat").read_text().split(") ", 1)[1].split()
        self.assertEqual(len(fields), 20)
        self.assertEqual(fields[0], "S")   # Field 3
        self.assertEqual(fields[19], "97123")  # Field 22

    def test_one_unique_qemu_and_actual_label_produce_non_attestation_pass(self):
        report = self.inspect()
        self.assertTrue(report.ok, report.describe())
        self.assertEqual(report.inspected_matching_processes, 1)
        self.assertEqual(self.runtime.calls, [(RECOVERED, "isolated")])
        self.assertIn("MATCHED (READ-ONLY /PROC OBSERVATION)", report.describe())
        self.assertIn("not cryptographic authentication", report.describe())
        evidence = report.evidence()
        self.assertTrue(evidence["read_only_process_label_observed"])
        for key in (
            "guest_os_boot_verified",
            "packet_level_network_denial_verified",
            "recovery_restoration_verified",
            "authenticated_qemu_executable_verified",
        ):
            self.assertIs(evidence[key], False)
        self.assertEqual(self.hv.calls, [
            ("dumpxml", RECOVERED), ("dumpxml", RECOVERED), ("state", RECOVERED),
        ])

    def test_different_guest_uuid_or_name_never_matches(self):
        for patchvalue in (
            {"uuid": "11111111-2222-3333-4444-555555555555"},
            {"name": "someone-else"},
            {"program": "/usr/bin/python3"},
        ):
            with self.subTest(patchvalue=patchvalue):
                self.make_process(1573, **patchvalue)
                result = self.inspect()
                self.assertFalse(result.ok)
                self.assertEqual(result.inspected_matching_processes, 0)
                self.assertIn("exactly one readable QEMU process", result.describe())
        self.make_process(1573)

    def test_duplicate_matching_process_is_ambiguous_and_refused(self):
        self.make_process(2789)
        result = self.inspect()
        self.assertFalse(result.ok)
        self.assertEqual(result.inspected_matching_processes, 2)
        self.assertIn("exactly one readable", result.describe())

    def test_wrong_actual_selinux_label_is_blocked(self):
        for context in ("unconfined_u:unconfined_r:unconfined_t:s0",
                        "system_u:system_r:svirt_t:s0:c11,c22", ""):
            with self.subTest(context=context):
                self.make_process(context=context)
                result = self.inspect()
                self.assertFalse(result.ok)
                self.assertIn("process context", result.describe())
        self.make_process()

    def test_user_cannot_read_matching_process_label(self):
        (self.pid_dir / "attr/current").unlink()
        report = self.inspect()
        self.assertFalse(report.ok)
        self.assertIn("cannot be read without privileges", report.describe())

    def test_missing_process_and_unreadable_other_process(self):
        (self.pid_dir / "cmdline").unlink()
        result = self.inspect()
        self.assertFalse(result.ok)
        self.assertIn("exactly one readable", result.describe())

    def test_runtime_failure_prevents_proc_enumeration(self):
        self.runtime.ok = False
        result = self.inspect()
        self.assertFalse(result.ok)
        self.assertEqual(result.inspected_matching_processes, 0)
        self.assertEqual(self.hv.calls, [])
        self.assertIn("not verified already running", result.describe())

    def test_different_original_vm_name_is_rejected_before_proc_reads(self):
        with self.assertRaisesRegex(ToolError, "NEW recovery VM"):
            KaliProcessLabelInspector(
                hypervisor=self.hv, runtime=self.runtime, proc_root=self.proc
            ).inspect(self.plan, OLD)
        self.assertFalse(self.runtime.calls)

    def test_invalid_or_changed_libvirt_xml_blocks(self):
        self.hv.current = guest_xml(uuid="NOT_A_UUID")
        self.assertIn("UUID and expected", self.inspect().describe())
        self.hv.current = guest_xml(label="")
        self.assertFalse(self.inspect().ok)
        self.hv.current = "<bad"
        self.assertFalse(self.inspect().ok)

    def test_qemu_process_start_time_change_fails_closed(self):
        from nightglass import kali_process_label as mod
        real_start = mod._start_time
        count = [0]
        def changing(path):
            count[0] += 1
            return "97234" if count[0] > 1 else real_start(path)
        with patch.object(mod, "_start_time", side_effect=changing):
            result = self.inspect()
        self.assertFalse(result.ok)
        self.assertIn("identity or effective SELinux label changed", result.describe())

    def test_process_disappears_during_recheck(self):
        from nightglass import kali_process_label as mod
        real_start = mod._start_time
        count = [0]
        def disappearing(path):
            count[0] += 1
            if count[0] == 2:
                raise ToolError("Process exited")
            return real_start(path)
        with patch.object(mod, "_start_time", side_effect=disappearing):
            result = self.inspect()
        self.assertFalse(result.ok)
        self.assertIn("exited or became unreadable", result.describe())

    def test_running_vm_stops_during_recheck(self):
        self.hv.state_value = "shut off"
        self.assertIn("no longer in libvirt running state", self.inspect().describe())

    def test_provenance_report_leaks_no_pid_mcs_raw_cmdline_or_host_paths(self):
        result = self.inspect()
        dest = self.root / "new-private-label.json"
        if os.name == "nt":
            with patch("nightglass.acceptance.os.fchmod", create=True):
                self.assertEqual(save_kali_process_label(result, dest), dest)
        else:
            self.assertEqual(save_kali_process_label(result, dest), dest)
        if os.name != "nt":
            self.assertEqual(dest.stat().st_mode & 0o777, 0o600)
        raw = dest.read_text(encoding="utf-8")
        for sensitive in ("1573", MCS, "system_u:system_r", str(self.root),
                          "/usr/bin/qemu-system", UUID):
            self.assertNotIn(sensitive, raw)
        self.assertIn('"guest_os_boot_verified": false', raw)
        data = dest.read_bytes()
        with self.assertRaisesRegex(ToolError, "already exists"):
            save_kali_process_label(result, dest)
        self.assertEqual(data, dest.read_bytes())

    def test_cli_observer_never_autostarts_vm_or_requests_root(self):
        arguments = [
            "templates", "process-label", str(self.plan),
            "--guest", RECOVERED,
        ]
        report = self.inspect()
        buffer = StringIO()
        with patch("nightglass.cli.KaliProcessLabelInspector") as checker, redirect_stdout(buffer):
            checker.return_value.inspect.return_value = report
            self.assertEqual(main(arguments), 0)
            checker.return_value.inspect.assert_called_once_with(self.plan, RECOVERED)
            checker.return_value.inspect.return_value = type(
                "Blocked", (), {"ok": False, "describe": lambda self: "BLOCKED"}
            )()
            self.assertEqual(main(arguments), 2)
        self.assertIn("READ-ONLY /PROC", buffer.getvalue())


if __name__ == "__main__":
    unittest.main()
