"""Read-only resource snapshots with fake /proc data and fake libvirt.

No VM is started, no proc settings changed, and no root required.
"""
from __future__ import annotations

from types import SimpleNamespace
import tempfile
import unittest
from pathlib import Path

from nightglass.portability import budget_for
from nightglass.resources import (
    ACTIVE_STATES, MemoryPressure, collect_resources, host_memory, parse_meminfo,
)
from nightglass.runner import ToolError


class FakeHV:
    def __init__(self, states=None, failure=None):
        self.states = states or {}
        self.failure = failure
        self.calls = []

    def list_domains(self):
        self.calls.append("list")
        if self.failure:
            raise ToolError(self.failure)
        return list(self.states)

    def state(self, name):
        self.calls.append("state:" + name)
        return self.states[name]


class ResourceMonitorTests(unittest.TestCase):
    def setUp(self):
        self.budget = budget_for(8.0, 6)
        self.good = MemoryPressure(8.0, 4.25, 2.0, 0.25)
        self.bound = [SimpleNamespace(kind="vm", identifier="nightglass-kali")]

    def snapshot(self, states=None, memory=None, bound=None, failure=None):
        fake = FakeHV(states, failure)
        result = collect_resources(
            hypervisor=fake, budget=self.budget,
            memory=memory if memory is not None else self.good,
            workspaces=self.bound if bound is None else bound,
        )
        return result, fake

    def test_parses_memavailable_and_swap_instead_of_memfree(self):
        text = (
            "MemTotal:        8388608 kB\n"
            "MemFree:          131072 kB\n"
            "MemAvailable:    4194304 kB\n"
            "SwapTotal:       2097152 kB\n"
            "SwapFree:        1048576 kB\n"
        )
        m = parse_meminfo(text)
        self.assertEqual((m.total_gib, m.available_gib), (8.0, 4.0))
        self.assertEqual((m.swap_total_gib, m.swap_used_gib), (2.0, 1.0))
        self.assertEqual(m.available_percent, 50.0)

    def test_invalid_missing_or_inconsistent_memory_is_unknown(self):
        for data in ("", "MemTotal: bad kB", "MemTotal: 1 kB\nMemAvailable: 2 kB"):
            with self.subTest(data=data):
                self.assertIsNone(parse_meminfo(data).available_gib)
        result, _ = self.snapshot(memory=MemoryPressure(None, None, None, None))
        self.assertEqual(result.level, "UNKNOWN")
        self.assertIn("unknown", result.describe())

    def test_missing_meminfo_does_not_raise(self):
        with tempfile.TemporaryDirectory() as tmp:
            absent = Path(tmp) / "no-such-meminfo"
            self.assertIsNone(host_memory(absent).available_gib)

    def test_idle_no_active_vm_is_normal(self):
        result, hv = self.snapshot({"nightglass-kali": "shut off"})
        self.assertEqual(result.level, "NORMAL")
        self.assertTrue(result.libvirt_available)
        self.assertEqual(result.active_vms, ())
        self.assertEqual(result.unbound_vms, ())
        self.assertEqual(hv.calls, ["list", "state:nightglass-kali"])

    def test_active_bound_vm_reports_budget_consumed(self):
        result, hv = self.snapshot({"nightglass-kali": "running"})
        self.assertEqual(result.level, "CAUTION")
        self.assertEqual(result.active_vms, ("nightglass-kali",))
        self.assertEqual(result.unbound_vms, ())
        self.assertTrue(any("concurrency budget" in s for s in result.warnings))

    def test_external_vm_is_reported_without_stopping(self):
        result, hv = self.snapshot({
            "nightglass-kali": "shut off",
            "unregistered-by-nightglass": "running",
        })
        self.assertEqual(result.level, "CAUTION")
        self.assertEqual(result.unbound_vms, ("unregistered-by-nightglass",))
        self.assertFalse(any("destroy" in call or "shutdown" in call for call in hv.calls))

    def test_paused_guest_is_active_and_over_limit_is_critical(self):
        result, _ = self.snapshot({
            "nightglass-kali": "paused",
            "other-vm": "running",
        })
        self.assertEqual(result.level, "CRITICAL")
        self.assertEqual(len(result.active_vms), 2)
        self.assertEqual(result.unbound_vms, ("other-vm",))

    def test_low_available_ram_is_critical(self):
        result, _ = self.snapshot(memory=MemoryPressure(8.0, 0.49, 2.0, 0.1))
        self.assertEqual(result.level, "CRITICAL")
        self.assertTrue(any("little available RAM" in s for s in result.warnings))

    def test_moderate_ram_pressure_is_caution(self):
        result, _ = self.snapshot(memory=MemoryPressure(8.0, 1.2, 0.0, 0.0))
        self.assertEqual(result.level, "CAUTION")
        self.assertTrue(any("pressure is elevated" in s for s in result.warnings))

    def test_swap_occupancy_is_only_advisory(self):
        result, _ = self.snapshot(memory=MemoryPressure(8, 5, 1, 0.9))
        self.assertEqual(result.level, "CAUTION")
        self.assertIn("not itself a measure of current", result.describe())

    def test_libvirt_unavailable_never_claims_normal(self):
        result, _ = self.snapshot(failure="no polkit permission")
        self.assertEqual(result.level, "UNKNOWN")
        self.assertFalse(result.libvirt_available)
        self.assertIn("libvirt unavailable", result.describe())
        self.assertTrue(any("no polkit permission" in s for s in result.warnings))

    def test_unknown_state_never_claims_normal(self):
        result, _ = self.snapshot({"guest": "migrating"})
        self.assertEqual(result.level, "UNKNOWN")
        self.assertFalse(result.libvirt_available)
        self.assertIn("Unknown state", result.describe())

    def test_no_automation_or_write_ops_in_resource_monitor(self):
        self.assertEqual(ACTIVE_STATES[0], "running")
        snap, hv = self.snapshot({"other": "pmsuspended"})
        self.assertEqual(snap.active_vms, ("other",))
        self.assertTrue(all(c.startswith(("list", "state:")) for c in hv.calls))


if __name__ == "__main__":
    unittest.main()
