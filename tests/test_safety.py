import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from nightglass.hypervisor import Hypervisor, assess_domain
from nightglass.containers import Containers
from nightglass.models import Workspace, WorkspaceError, safe_name
from nightglass.runner import Runner, ToolError, Output
from nightglass.settings import load_workspaces, save_workspaces


def domain(*inside: str) -> str:
    return '<domain type="kvm"><name>nightglass-malware</name><memory unit="MiB">3072</memory><devices>' + ''.join(inside) + '</devices></domain>'


LOOPBACK_VNC = '<graphics type="vnc" listen="127.0.0.1"/>'
NO_FORWARD_LAB = "<network><name>nightglass-lab</name><bridge name='virbr-nglab'/></network>"
FORWARDED_LAB = "<network><name>nightglass-lab</name><forward mode='nat'/><bridge name='virbr-nglab'/></network>"


class FakeRunner:
    def __init__(self, values):
        self.values = values
        self.calls = []

    def run(self, argv, timeout=12):
        self.calls.append((argv, timeout))
        key = tuple(argv)
        value = self.values.get(key)
        if isinstance(value, Exception):
            raise value
        if value is None:
            raise AssertionError(f"Unexpected invocation: {argv}")
        return Output(value)


def virsh(*args):
    return ('virsh', '--connect', 'qemu:///system', *args)


class DomainAuditTest(unittest.TestCase):
    def test_offline_malware_vm_with_local_graphics(self):
        self.assertTrue(assess_domain(domain(LOOPBACK_VNC), 'isolated').ok)

    def test_no_network_for_malware(self):
        check = assess_domain(domain('<interface type="network"><source network="default"/></interface>', LOOPBACK_VNC), 'isolated')
        self.assertFalse(check.ok)
        self.assertIn('network interface', ' '.join(check.warnings))

    def test_host_share_or_device_is_denied(self):
        for device in ['<filesystem type="mount"/>', '<hostdev mode="subsystem"/>', '<redirdev bus="usb"/>', '<shmem name="mem"/>', '<vsock/>', '<channel type="spicevmc"/>']:
            with self.subTest(device=device):
                self.assertFalse(assess_domain(domain(LOOPBACK_VNC, device), 'isolated').ok)

    def test_spice_and_remote_vnc_denied(self):
        for graphic in ['<graphics type="spice" listen="127.0.0.1"/>', '<graphics type="vnc" listen="0.0.0.0"/>', '<graphics type="vnc"/>']:
            with self.subTest(graphic=graphic):
                self.assertFalse(assess_domain(domain(graphic), 'isolated').ok)

    def test_raw_block_device_denied(self):
        self.assertFalse(assess_domain(domain('<disk type="block" device="disk"><source dev="/dev/sda"/></disk>', LOOPBACK_VNC), 'isolated').ok)

    def test_verified_lab_no_forward(self):
        nic = '<interface type="network"><source network="nightglass-lab"/></interface>'
        self.assertTrue(assess_domain(domain(nic, LOOPBACK_VNC), 'lab', NO_FORWARD_LAB).ok)
        self.assertFalse(assess_domain(domain(nic, LOOPBACK_VNC), 'lab', FORWARDED_LAB).ok)
        self.assertFalse(assess_domain(domain(nic, LOOPBACK_VNC), 'lab', None).ok)
        self.assertFalse(assess_domain(domain('<interface type="bridge"><source bridge="br0"/></interface>', LOOPBACK_VNC), 'lab', NO_FORWARD_LAB).ok)

    def test_malformed_xml_fails_closed(self):
        self.assertFalse(assess_domain('<invalid', 'isolated').ok)
        self.assertFalse(assess_domain(domain(), 'evil-policy').ok)


class LifecycleTest(unittest.TestCase):
    def test_start_permitted_only_after_audit(self):
        runner = FakeRunner({
            virsh('list', '--all', '--name'): 'safevm\n',
            virsh('dumpxml', 'safevm'): domain(LOOPBACK_VNC),
            virsh('start', 'safevm'): 'Domain safevm started\n',
        })
        result = Hypervisor(runner).start('safevm', 'isolated')
        self.assertIn('started', result)
        self.assertEqual(runner.calls[-1][0], list(virsh('start', 'safevm')))

    def test_start_blocked_for_insecure_domain(self):
        runner = FakeRunner({
            virsh('list', '--all', '--name'): 'unsafevm\n',
            virsh('dumpxml', 'unsafevm'): domain('<interface type="bridge"/>'),
        })
        with self.assertRaises(ToolError):
            Hypervisor(runner).start('unsafevm', 'isolated')
        self.assertNotIn((list(virsh('start', 'unsafevm')), 120), runner.calls)

    def test_malicious_name_rejected_before_process(self):
        runner = FakeRunner({})
        with self.assertRaises(WorkspaceError):
            Hypervisor(runner).start('vm;rm -rf /', 'isolated')
        self.assertFalse(runner.calls)


class ConfigTest(unittest.TestCase):
    def test_untrusted_distrobox_cannot_claim_isolation(self):
        with self.assertRaises(WorkspaceError):
            Workspace('x', 'Unsafe', 'distrobox', 'dev', 'isolated', 'cannot')

    def test_config_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / 'settings' / 'workspaces.json'
            source = [Workspace('test', 'Test', 'vm', 'safevm', 'isolated', 'offline')]
            save_workspaces(source, target)
            self.assertEqual(load_workspaces(target), source)
            self.assertEqual(target.stat().st_mode & 0o777, 0o600)

    def test_bad_config_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / 'config.json'
            target.write_text('{"version":1,"workspaces":[{"key":"oops"}]}')
            with self.assertRaises(WorkspaceError):
                load_workspaces(target)

    def test_safe_name(self):
        for value in ['a/b', '-bad', '../etc', 'hello world', 'a\nsub', '$PWD', '']:
            with self.subTest(value=value):
                with self.assertRaises(WorkspaceError):
                    safe_name(value)


class ContainerTest(unittest.TestCase):
    def test_distrobox_uses_allowlisted_image(self):
        listing = 'ID           | NAME        | STATUS | IMAGE\nabc          | other       | Up     | Ubuntu\n'
        runner = FakeRunner({
            ('distrobox', 'list', '--no-color'): listing,
            ('distrobox', 'create', '--name', 'nightglass-dev', '--image', 'docker.io/library/ubuntu:24.04', '--yes'): 'Done',
        })
        self.assertEqual(Containers(runner).create('nightglass-dev'), 'Done')

    def test_arbitrary_image_not_accepted(self):
        with self.assertRaises(ToolError):
            Containers(FakeRunner({})).create('dev', 'malicious/image:latest')


if __name__ == '__main__':
    unittest.main()

class ProfileSeparationTest(unittest.TestCase):
    def test_duplicate_vm_bindings_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'workspaces.json'
            spaces = [
                Workspace('pentest', 'Kali', 'vm', 'sharedvm', 'lab', 'lab'),
                Workspace('analysis', 'Malware', 'vm', 'sharedvm', 'isolated', 'analysis'),
            ]
            with self.assertRaises(WorkspaceError):
                save_workspaces(spaces, path)

class MemoryGuardTest(unittest.TestCase):
    def test_low_ram_blocks_parallel_vms(self):
        runner = FakeRunner({
            virsh('list', '--all', '--name'): 'safevm\nothervm\n',
            virsh('dumpxml', 'safevm'): domain(LOOPBACK_VNC),
            virsh('domstate', 'othervm'): 'running\n',
        })
        with patch('nightglass.hypervisor.total_ram_gib', return_value=7.7):
            with self.assertRaisesRegex(ToolError, 'another VM is already active'):
                Hypervisor(runner).start('safevm', 'isolated')
        self.assertNotIn((list(virsh('start', 'safevm')), 120), runner.calls)

    def test_low_ram_blocks_oversized_guest(self):
        runner = FakeRunner({
            virsh('list', '--all', '--name'): 'safevm\n',
            virsh('dumpxml', 'safevm'): '<domain><memory unit="GiB">5</memory><devices>' + LOOPBACK_VNC + '</devices></domain>',
        })
        with patch('nightglass.hypervisor.total_ram_gib', return_value=7.7):
            with self.assertRaisesRegex(ToolError, 'Low-memory guard: VM requests'):
                Hypervisor(runner).start('safevm', 'isolated')
        self.assertNotIn((list(virsh('start', 'safevm')), 120), runner.calls)
