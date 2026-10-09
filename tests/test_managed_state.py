"""Managed-save is an alternate VM definition that must be audited on restore."""
import unittest
from unittest.mock import patch
from nightglass.hypervisor import Hypervisor
from nightglass.runner import ToolError, Output


def domain(*devices):
    return ('<domain type="kvm"><name>sample</name><memory unit="MiB">3072</memory><devices>'
            + ''.join(devices) + '</devices></domain>')


VNC = '<graphics type="vnc" listen="127.0.0.1"/>'
LAB_NIC = '<interface type="network"><source network="nightglass-lab"/></interface>'
LAB = '<network><name>nightglass-lab</name><bridge name="virbr-nglab"/></network>'
FORWARDED = '<network><name>nightglass-lab</name><forward mode="nat"/><bridge name="virbr-nglab"/></network>'


def virsh(*args):
    return ('virsh', '--connect', 'qemu:///system', *args)


class FakeRunner:
    def __init__(self, saved=None, info=None, lab=None):
        self.calls = []
        self.values = {
            virsh('list', '--all', '--name'): 'sample\n',
            virsh('dumpxml', 'sample'): domain(VNC),
            virsh('dominfo', 'sample'): info if info is not None else ('Managed save: yes\n' if saved is not None else 'Managed save: no\n'),
        }
        if saved is not None:
            self.values[virsh('managedsave-dumpxml', 'sample')] = saved
        if lab is not None:
            self.values[virsh('net-dumpxml', 'nightglass-lab')] = lab

    def run(self, argv, timeout=12):
        self.calls.append((argv, timeout))
        value = self.values.get(tuple(argv))
        if value is None:
            raise AssertionError(f'Unexpected invocation: {argv}')
        if isinstance(value, Exception):
            raise value
        return Output(value)


class SavedStateTest(unittest.TestCase):
    def test_saved_nic_must_not_bypass_analysis_policy(self):
        r = FakeRunner(saved=domain(VNC, LAB_NIC))
        with self.assertRaisesRegex(ToolError, 'Saved session: Offline analysis VM has a network interface'):
            Hypervisor(r).start('sample', 'isolated')
        self.assertNotIn((list(virsh('start', 'sample')), 120), r.calls)

    def test_saved_lab_nic_verifies_no_forward(self):
        self.assertFalse(Hypervisor(FakeRunner(saved=domain(VNC, LAB_NIC), lab=FORWARDED)).audit('sample', 'lab').ok)
        audit = Hypervisor(FakeRunner(saved=domain(VNC, LAB_NIC), lab=LAB)).audit('sample', 'lab')
        self.assertTrue(audit.ok)
        self.assertTrue(audit.saved_state)

    def test_valid_saved_resume_permitted(self):
        r = FakeRunner(saved=domain(VNC))
        r.values[virsh('start', 'sample')] = 'Domain sample started\n'
        with patch('nightglass.hypervisor.total_ram_gib', return_value=7.7):
            self.assertIn('started', Hypervisor(r).start('sample', 'isolated'))
        self.assertIn((list(virsh('managedsave-dumpxml', 'sample')), 12), r.calls)

    def test_invalid_dominfo_is_fail_closed(self):
        audit = Hypervisor(FakeRunner(info='Managed save: maybe\n')).audit('sample', 'isolated')
        self.assertFalse(audit.ok)
        self.assertIn('managed-save status', audit.warnings[0])

    def test_missing_saved_xml_fails_closed(self):
        r = FakeRunner(info='Managed save: yes\n')
        r.values[virsh('managedsave-dumpxml', 'sample')] = ToolError('Saved session cannot be read')
        audit = Hypervisor(r).audit('sample', 'isolated')
        self.assertFalse(audit.ok)
        self.assertIn('cannot be read', audit.warnings[0])

    def test_malformed_saved_xml_rejected(self):
        audit = Hypervisor(FakeRunner(saved='<invalid')).audit('sample', 'isolated')
        self.assertFalse(audit.ok)
        self.assertIn('Saved session', audit.warnings[0])

    def test_saved_memory_limit_applies(self):
        big = domain(VNC).replace('unit="MiB">3072', 'unit="GiB">5')
        r = FakeRunner(saved=big)
        with patch('nightglass.hypervisor.total_ram_gib', return_value=7.7):
            with self.assertRaisesRegex(ToolError, 'Low-memory guard: VM declares up to'):
                Hypervisor(r).start('sample', 'isolated')
        self.assertNotIn((list(virsh('start', 'sample')), 120), r.calls)

    def test_different_saved_domain_name_rejected(self):
        audit = Hypervisor(FakeRunner(saved=domain(VNC).replace('sample', 'other'))).audit('sample', 'isolated')
        self.assertFalse(audit.ok)
        self.assertIn('different name', ' '.join(audit.warnings))

    def test_analysis_memory_save_disallowed(self):
        r = FakeRunner()
        with self.assertRaisesRegex(ToolError, 'Analysis VMs'):
            Hypervisor(r).managed_save('sample', 'isolated')
        self.assertEqual([], r.calls)

    def test_kali_save_checks_policy(self):
        r = FakeRunner()
        r.values[virsh('managedsave', 'sample')] = 'Saved'
        self.assertEqual(Hypervisor(r).managed_save('sample', 'lab'), 'Saved')
        self.assertIn((list(virsh('dominfo', 'sample')), 12), r.calls)


if __name__ == '__main__':
    unittest.main()
