import os
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
    return '<domain type="kvm"><name>safevm</name><memory unit="MiB">3072</memory><devices>' + ''.join(inside) + '</devices></domain>'


LOOPBACK_VNC = '<graphics type="vnc" listen="127.0.0.1"/>'
NO_FORWARD_LAB = "<network><name>nightglass-lab</name><bridge name='virbr-nglab'/><dns enable='no'/></network>"
FORWARDED_LAB = "<network><name>nightglass-lab</name><forward mode='nat'/><bridge name='virbr-nglab'/><dns enable='no'/></network>"


class FakeRunner:
    def __init__(self, values):
        self.values = values
        self.calls = []

    def run(self, argv, timeout=12):
        self.calls.append((argv, timeout))
        key = tuple(argv)
        value = self.values.get(key)
        if value is None and len(key) == 6 and key[:4] == virsh('dumpxml') and key[4] == '--inactive':
            value = self.values.get(virsh('dumpxml', key[5]))
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

    def test_host_channels_and_qemu_override_denied(self):
        vectors = [
            '<serial type="tcp"><source mode="bind" host="0.0.0.0" service="12345"/></serial>',
            '<parallel type="tcp"/>',
            '<console type="pty"/>',
            '<smartcard mode="passthrough"/>',
            '<tpm model="tpm-tis"><backend type="external"/></tpm>',
            '<rng model="virtio"><backend model="egd" type="tcp"/></rng>',
            '<sound model="ich6"/>',
            '<audio type="pulseaudio"/>',
        ]
        for item in vectors:
            with self.subTest(item=item):
                self.assertFalse(assess_domain(domain(item, LOOPBACK_VNC), 'isolated').ok)
                self.assertFalse(assess_domain(domain(item, LOOPBACK_VNC), 'lab').ok)
        xml = domain(LOOPBACK_VNC).replace(
            '<domain type="kvm">',
            '<domain type="kvm" xmlns:qemu="http://libvirt.org/schemas/domain/qemu/1.0">',
        ).replace('</domain>', '<qemu:commandline><qemu:arg value="-netdev"/></qemu:commandline></domain>')
        self.assertFalse(assess_domain(xml, 'isolated').ok)
        self.assertFalse(assess_domain(xml, 'lab').ok)
        self.assertFalse(assess_domain(xml.replace('commandline', 'override'), 'isolated').ok)

    def test_block_devices_in_cdrom_or_backing_chain_denied(self):
        devices = [
            '<disk device="cdrom" type="block"><source dev="/dev/sr0"/></disk>',
            '<disk device="lun" type="block"><source dev="/dev/sda"/></disk>',
            '<disk device="disk" type="volume"><source pool="vol-pool" volume="vm"/></disk>',
            '<disk device="disk" type="file"><source file="/var/lib/libvirt/images/a.qcow2"/><backingStore type="block"><source dev="/dev/sda"/></backingStore></disk>',
            '<disk device="disk" type="file"><source file="/dev/sda"/></disk>',
            '<disk device="disk" type="network"><source protocol="rbd" name="pool/volume"/></disk>',
        ]
        for item in devices:
            with self.subTest(item=item):
                self.assertFalse(assess_domain(domain(item, LOOPBACK_VNC), 'isolated').ok)
        allowed = '<disk device="cdrom" type="file"><source file="/var/lib/libvirt/images/installer.iso"/></disk>'
        self.assertTrue(assess_domain(domain(allowed, LOOPBACK_VNC), 'isolated').ok)

    def test_raw_block_device_denied(self):
        self.assertFalse(assess_domain(domain('<disk type="block" device="disk"><source dev="/dev/sda"/></disk>', LOOPBACK_VNC), 'isolated').ok)

    def test_verified_lab_no_forward(self):
        nic = '<interface type="network"><source network="nightglass-lab"/></interface>'
        self.assertTrue(assess_domain(domain(nic, LOOPBACK_VNC), 'lab', NO_FORWARD_LAB).ok)
        self.assertFalse(assess_domain(domain(nic, LOOPBACK_VNC), 'lab', FORWARDED_LAB).ok)
        self.assertFalse(assess_domain(domain(nic, LOOPBACK_VNC), 'lab', None).ok)
        self.assertFalse(assess_domain(domain('<interface type="bridge"><source bridge="br0"/></interface>', LOOPBACK_VNC), 'lab', NO_FORWARD_LAB).ok)

    def test_lab_network_with_dns_relay_denied(self):
        nic = '<interface type="network"><source network="nightglass-lab"/></interface>'
        for net in ("<network><name>nightglass-lab</name><bridge name='virbr-nglab'/></network>",
                    "<network><name>nightglass-lab</name><bridge name='virbr-nglab'/><dns><forwarder addr='8.8.8.8'/></dns></network>"):
            with self.subTest(net=net):
                check = assess_domain(domain(nic, LOOPBACK_VNC), 'lab', net)
                self.assertFalse(check.ok)
                self.assertIn('DNS', ' '.join(check.warnings))

    def test_host_input_and_memory_backends_denied(self):
        for device in ['<input type="passthrough" bus="virtio"><source evdev="/dev/input/event1"/></input>',
                       '<input type="evdev"><source dev="/dev/input/by-id/kbd"/></input>',
                       '<memory model="nvdimm"><source><path>/tmp/nvdimm</path></source></memory>',
                       '<memory model="virtio-pmem" access="shared"><source><path>/tmp/pmem</path></source></memory>']:
            with self.subTest(device=device):
                self.assertFalse(assess_domain(domain(LOOPBACK_VNC, device), 'isolated').ok)
        self.assertTrue(assess_domain(domain(LOOPBACK_VNC, '<input type="tablet" bus="usb"/>'), 'isolated').ok)

    def test_custom_emulator_and_direct_kernel_boot_denied(self):
        for emulator in ('/home/user/qemu', 'qemu-system-x86_64', '/usr/bin/../../tmp/qemu'):
            with self.subTest(emulator=emulator):
                self.assertFalse(assess_domain(domain(LOOPBACK_VNC, f'<emulator>{emulator}</emulator>'), 'isolated').ok)
        for emulator in ('/usr/bin/qemu-system-x86_64', '/usr/libexec/qemu-kvm'):
            with self.subTest(emulator=emulator):
                self.assertTrue(assess_domain(domain(LOOPBACK_VNC, f'<emulator>{emulator}</emulator>'), 'isolated').ok)
        kernel = domain(LOOPBACK_VNC).replace('<devices>', '<os><kernel>/etc/shadow</kernel></os><devices>')
        self.assertFalse(assess_domain(kernel, 'isolated').ok)

    def test_every_graphics_listen_address_must_be_loopback(self):
        for graphic in ['<graphics type="vnc"><listen type="address" address="0.0.0.0"/><listen type="address" address="127.0.0.1"/></graphics>',
                        '<graphics type="vnc" listen="0.0.0.0"><listen type="socket"/></graphics>']:
            with self.subTest(graphic=graphic):
                self.assertFalse(assess_domain(domain(graphic), 'isolated').ok)
        for graphic in ['<graphics type="vnc"><listen type="address" address="::1"/></graphics>',
                        '<graphics type="vnc"><listen type="socket"/></graphics>']:
            with self.subTest(graphic=graphic):
                self.assertTrue(assess_domain(domain(graphic), 'isolated').ok)

    def test_malformed_xml_fails_closed(self):
        self.assertFalse(assess_domain('<invalid', 'isolated').ok)
        self.assertFalse(assess_domain(domain(), 'evil-policy').ok)


class LifecycleTest(unittest.TestCase):
    def test_start_permitted_only_after_audit(self):
        runner = FakeRunner({
            virsh('list', '--all', '--name'): 'safevm\n',
            virsh('dominfo', 'safevm'): 'Managed save: no\n',
            virsh('dumpxml', 'safevm'): domain(LOOPBACK_VNC),
            virsh('start', 'safevm'): 'Domain safevm started\n',
        })
        # This is a synthetic policy-path test, not a Docker host RAM test.
        # A 2 GiB test container must not make its nominal 3 GiB guest fail.
        # Dedicated low-memory tests separately verify fail-closed limits.
        with patch("nightglass.hypervisor.total_ram_gib", return_value=16), \
             patch("nightglass.hypervisor.os.cpu_count", return_value=6):
            result = Hypervisor(runner).start('safevm', 'isolated')
        self.assertIn('started', result)
        self.assertEqual(runner.calls[-1][0], list(virsh('start', 'safevm')))

    def test_start_blocked_for_insecure_domain(self):
        runner = FakeRunner({
            virsh('list', '--all', '--name'): 'unsafevm\n',
            virsh('dominfo', 'unsafevm'): 'Managed save: no\n',
            virsh('dumpxml', 'unsafevm'): domain('<interface type="bridge"/>').replace('<name>safevm</name>', '<name>unsafevm</name>'),
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
            if os.name == "nt":
                with patch("nightglass.settings.os.fchmod", create=True):
                    save_workspaces(source, target)
            else:
                save_workspaces(source, target)
            self.assertEqual(load_workspaces(target), source)
            if os.name != "nt":
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



class RunnerTest(unittest.TestCase):
    def test_invalid_utf8_output_is_replaced_not_raised(self):
        out = Runner().run(['python3', '-c', 'import sys; sys.stdout.buffer.write(b"vm-\\xff\\n")'])
        self.assertEqual(out.stdout, 'vm-�\n')

    def test_os_errors_become_tool_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ToolError):
                Runner().run([tmp])  # a directory: PermissionError/IsADirectoryError
            with self.assertRaises(ToolError):
                Runner().run([os.path.join(tmp, 'missing-tool')])

    def test_rejects_non_string_or_nul_arguments(self):
        for argv in ([], ['virsh', 3], ['virsh', 'a\x00b']):
            with self.subTest(argv=argv), self.assertRaises(ToolError):
                Runner().run(argv)


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
            virsh('dominfo', 'safevm'): 'Managed save: no\n',
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
            virsh('dominfo', 'safevm'): 'Managed save: no\n',
            virsh('dumpxml', 'safevm'): '<domain><name>safevm</name><memory unit="GiB">5</memory><devices>' + LOOPBACK_VNC + '</devices></domain>',
        })
        with patch('nightglass.hypervisor.total_ram_gib', return_value=7.7):
            with self.assertRaisesRegex(ToolError, 'Low-memory guard: VM declares up to'):
                Hypervisor(runner).start('safevm', 'isolated')
        self.assertNotIn((list(virsh('start', 'safevm')), 120), runner.calls)

class HotplugMemoryGuardTest(unittest.TestCase):
    def test_low_ram_guard_checks_maximum_hotplug_memory(self):
        xml = domain(LOOPBACK_VNC).replace('<devices>', '<maxMemory unit="GiB" slots="8">8</maxMemory><devices>')
        runner = FakeRunner({
            virsh('list', '--all', '--name'): 'safevm\n',
            virsh('dominfo', 'safevm'): 'Managed save: no\n',
            virsh('dumpxml', 'safevm'): xml,
        })
        with patch('nightglass.hypervisor.total_ram_gib', return_value=7.7):
            with self.assertRaisesRegex(ToolError, 'Low-memory guard: VM declares up to'):
                Hypervisor(runner).start('safevm', 'isolated')
        self.assertNotIn((list(virsh('start', 'safevm')), 120), runner.calls)
