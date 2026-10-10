"""Fedora disk-encryption plan and read-only LUKS verification."""
from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import unittest
from unittest.mock import patch

from nightglass import install_encryption as enc
from nightglass.cli import main
from nightglass.install_change_review import review_from_discovery
from nightglass.install_target_preview import build_target_preview, describe_target_preview


def part(name, fstype=None, mounts=None, children=None, kind="part", fsver=None):
    node = {"name": name, "type": kind, "fstype": fstype, "fsver": fsver, "mountpoints": mounts or [None]}
    if children:
        node["children"] = children
    return node


# Fedora default with "Encrypt my data": ESP, /boot, LUKS2 -> btrfs (/ and /home subvolumes).
FEDORA_ENCRYPTED = {"blockdevices": [part("nvme0n1", kind="disk", children=[
    part("nvme0n1p1", "vfat", ["/boot/efi"]),
    part("nvme0n1p2", "ext4", ["/boot"]),
    part("nvme0n1p3", "crypto_LUKS", fsver="2", children=[
        part("luks-1234", "btrfs", ["/home", "/"], kind="crypt")]),
])]}
FEDORA_PLAIN = {"blockdevices": [part("sda", kind="disk", children=[
    part("sda1", "vfat", ["/boot/efi"]), part("sda2", "ext4", ["/boot"]),
    part("sda3", "btrfs", ["/", "/home"])])]}
ENCRYPTED_ROOT_PLAIN_HOME = {"blockdevices": [part("sda", kind="disk", children=[
    part("sda1", "crypto_LUKS", fsver="2", children=[part("luks-a", "ext4", ["/"], kind="crypt")]),
    part("sda2", "ext4", ["/home"])])]}


class EncryptionPlanTests(unittest.TestCase):
    def test_luks_plans_encrypt_data_but_never_claim_boot_or_writes(self):
        for choice in (enc.LUKS2, enc.LUKS2_TPM2_PIN):
            with self.subTest(choice=choice):
                plan = enc.encryption_plan(choice)
                self.assertTrue(plan.linux_data_encrypted and plan.passphrase_or_pin_at_startup)
                self.assertFalse(plan.boot_partition_encrypted or plan.efi_partition_encrypted)
                self.assertFalse(plan.disk_write_authorized)
                self.assertIn("Encrypt my data", " ".join(plan.installer_steps))
                self.assertIn(enc.BOOT_NOTE, plan.warnings)
        tpm = enc.encryption_plan(enc.LUKS2_TPM2_PIN)
        self.assertIn("--tpm2-with-pin=yes", " ".join(tpm.after_install_steps))
        self.assertNotIn("--tpm2-with-pin", " ".join(enc.encryption_plan(enc.LUKS2).after_install_steps))

    def test_none_and_undecided_warn_and_have_no_steps(self):
        for choice in (enc.NONE, enc.UNDECIDED):
            plan = enc.encryption_plan(choice)
            self.assertFalse(plan.linux_data_encrypted)
            self.assertEqual(plan.installer_steps, ())
            self.assertTrue(plan.warnings)
        with self.assertRaises(ValueError):
            enc.encryption_plan("luks1")

    def test_coexist_warns_about_bitlocker_recovery_key(self):
        self.assertIn("BitLocker", " ".join(enc.encryption_plan(enc.LUKS2, coexist=True).warnings))
        self.assertNotIn("BitLocker", " ".join(enc.encryption_plan(enc.LUKS2).warnings))

    def test_preview_and_change_review_carry_the_choice(self):
        preview = build_target_preview(None, encryption=enc.LUKS2)
        self.assertEqual(preview.disk_encryption, enc.LUKS2)
        self.assertFalse(preview.disk_write_authorized)
        self.assertIn("LINUX DISK ENCRYPTION", describe_target_preview(preview))
        undecided = build_target_preview(None)
        self.assertTrue(any("encrypted" in item for item in undecided.unresolved))
        review = review_from_discovery(None, encryption=enc.LUKS2_TPM2_PIN)
        row = next(i for i in review.impacts if i.component == "LINUX_DISK_ENCRYPTION")
        self.assertIn("TPM2", row.description)
        self.assertFalse(review.disk_write_authorized)

    def test_cli_install_preview_accepts_encryption(self):
        out = StringIO()
        with patch("nightglass.system_discovery.collect_system", return_value=None), redirect_stdout(out):
            self.assertEqual(main(["install-preview", "--encryption", "luks2"]), 0)
        self.assertIn("Encrypt my data", out.getvalue())


class EncryptionCheckTests(unittest.TestCase):
    def test_fedora_encrypted_layout(self):
        report = enc.inspect_encryption(FEDORA_ENCRYPTED)
        self.assertEqual(report["status"], "ENCRYPTED")
        self.assertEqual(report["mounts"]["/"], "ENCRYPTED_LUKS2")
        self.assertEqual(report["mounts"]["/boot"], "NOT_ENCRYPTED")

    def test_plain_or_partly_encrypted_is_not_encrypted(self):
        self.assertEqual(enc.inspect_encryption(FEDORA_PLAIN)["status"], "NOT_ENCRYPTED")
        self.assertEqual(enc.inspect_encryption(ENCRYPTED_ROOT_PLAIN_HOME)["status"], "NOT_ENCRYPTED")

    def test_missing_or_hostile_data_is_unknown(self):
        for data in (None, {}, {"blockdevices": "x"}, {"blockdevices": [part("sda", kind="disk")]}):
            with self.subTest(data=data):
                self.assertEqual(enc.inspect_encryption(data)["status"], "UNKNOWN")
        deep = part("leaf", "ext4", ["/"])
        for _ in range(100):
            deep = part("n", children=[deep])
        self.assertEqual(enc.inspect_encryption({"blockdevices": [deep]})["status"], "UNKNOWN")

    def test_cli_exit_codes(self):
        for data, code in ((FEDORA_ENCRYPTED, 0), (FEDORA_PLAIN, 2)):
            out = StringIO()
            with patch("nightglass.install_encryption.collect_encryption",
                       return_value=enc.inspect_encryption(data)), redirect_stdout(out):
                self.assertEqual(main(["encryption-check"]), code)


if __name__ == "__main__":
    unittest.main()
