"""Explicit sVirt/SELinux bypasses must not pass restricted-domain audits."""
import unittest
from midnight_provisioner.hypervisor import assess_domain

BASE = (
    '<domain type="kvm"><name>midnight-provisioner-test</name>'
    '<memory unit="MiB">2048</memory><devices>'
    '<graphics type="vnc" listen="127.0.0.1"/>'
    '<disk type="file" device="disk"><driver name="qemu" type="qcow2"/>'
    '<source file="/var/lib/libvirt/images/test.qcow2"/>'
    '<target dev="vda" bus="virtio"/></disk></devices></domain>'
)


class SvirtPolicyTests(unittest.TestCase):
    def test_default_libvirt_label_assignment_is_not_assumed_disabled(self):
        self.assertTrue(assess_domain(BASE, "isolated").ok)
        self.assertTrue(assess_domain(BASE, "lab").ok)

    def test_explicit_domain_seclabel_none_denied(self):
        xml = BASE.replace("<devices>", '<seclabel type="none"/><devices>')
        for policy in ("isolated", "lab"):
            with self.subTest(policy=policy):
                report = assess_domain(xml, policy)
                self.assertFalse(report.ok)
                self.assertTrue(any("security labeling" in x for x in report.warnings))

    def test_explicit_domain_relabel_no_denied(self):
        xml = BASE.replace("<devices>", '<seclabel type="dynamic" model="selinux" relabel="no"/><devices>')
        self.assertFalse(assess_domain(xml, "isolated").ok)

    def test_disk_relabel_opt_out_denied(self):
        xml = BASE.replace(
            '<target dev="vda" bus="virtio"/>',
            '<target dev="vda" bus="virtio"/><seclabel model="selinux" relabel="no"/>',
        )
        report = assess_domain(xml, "isolated")
        self.assertFalse(report.ok)
        self.assertTrue(any("relabeling" in x for x in report.warnings))

    def test_normal_dynamic_selinux_label_does_not_get_rejected(self):
        xml = BASE.replace(
            "<devices>",
            '<seclabel type="dynamic" model="selinux" relabel="yes"/><devices>',
        )
        self.assertTrue(assess_domain(xml, "isolated").ok)


if __name__ == "__main__":
    unittest.main()
