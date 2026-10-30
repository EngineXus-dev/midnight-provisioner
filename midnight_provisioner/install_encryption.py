"""Fedora disk-encryption choice for the future install, plus a read-only check.

Midnight Provisioner does not install Fedora or write to disks. Fedora's own installer
creates the encryption when "Encrypt my data" is selected; this module records
the user's choice, lists the exact installer and after-install steps, and,
once Fedora is running, verifies read-only that the root filesystem really sits
on a LUKS container.

The small /boot and EFI partitions stay unencrypted: firmware must read them to
load Linux and show the passphrase prompt, and Fedora's installer does not
support encrypting /boot. They hold no personal data; Secure Boot protects them
from tampering.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import subprocess
from typing import Any

UNDECIDED = "undecided"
NONE = "none"
LUKS2 = "luks2"
LUKS2_TPM2_PIN = "luks2-tpm2-pin"
CHOICES = (UNDECIDED, NONE, LUKS2, LUKS2_TPM2_PIN)
LABELS = {
    UNDECIDED: "Not decided",
    NONE: "No encryption (not recommended)",
    LUKS2: "Encrypt Linux with a passphrase at startup (recommended)",
    LUKS2_TPM2_PIN: "Encrypt Linux, unlock with TPM2 + PIN at startup",
}
LSBLK_QUERY = ("lsblk", "-J", "-o", "NAME,TYPE,FSTYPE,FSVER,MOUNTPOINTS")
MAX_LSBLK_BYTES = 262144

BOOT_NOTE = (
    "/boot and the EFI partition stay unencrypted: the firmware must read them to "
    "load Linux and show the passphrase prompt, and Fedora's installer does not "
    "support encrypting /boot. They contain no personal files. Keep Secure Boot "
    "enabled so they cannot be silently replaced."
)
INSTALLER_STEPS = (
    "In the installer's disk (Installation Destination / storage) step, select the target disk.",
    "Turn on 'Encrypt my data' and keep the default LUKS2 format.",
    "Choose a long passphrase you can type at every startup; write it down and keep it offline.",
    "Do not reuse your Windows, BitLocker or online-account password.",
)
AFTER_INSTALL_STEPS = (
    "Run 'midnight-provisioner encryption-check' to confirm the running root filesystem is on LUKS.",
    "Optionally back up the LUKS header to separate encrypted media: "
    "sudo cryptsetup luksHeaderBackup <luks-partition> --header-backup-file <file>",
)
TPM2_STEPS = (
    "Confirm Secure Boot is enabled in firmware settings (mokutil --sb-state).",
    "Enroll the TPM with a PIN: sudo systemd-cryptenroll --tpm2-device=auto "
    "--tpm2-with-pin=yes --tpm2-pcrs=7 <luks-partition>",
    "Add 'tpm2-device=auto' to that volume's options in /etc/crypttab, then run: sudo dracut -f",
    "Keep the original passphrase: it is the fallback after firmware, Secure Boot or TPM changes.",
)


@dataclass(frozen=True)
class EncryptionPlan:
    choice: str
    label: str
    linux_data_encrypted: bool
    passphrase_or_pin_at_startup: bool
    tpm2_pin_unlock: bool
    boot_partition_encrypted: bool
    efi_partition_encrypted: bool
    installer_steps: tuple[str, ...]
    after_install_steps: tuple[str, ...]
    warnings: tuple[str, ...]
    disk_write_authorized: bool = False

    def __post_init__(self):
        if self.choice not in CHOICES:
            raise ValueError("Unknown disk-encryption choice")


def encryption_plan(choice: str = UNDECIDED, *, coexist: bool = False) -> EncryptionPlan:
    """Advisory plan only: Fedora's installer performs the encryption."""
    if choice not in CHOICES:
        raise ValueError("Unknown disk-encryption choice")
    encrypted = choice in (LUKS2, LUKS2_TPM2_PIN)
    warnings = []
    if choice == UNDECIDED:
        warnings.append("Choose whether Fedora's Linux partitions are encrypted (recommended).")
    if choice == NONE:
        warnings.append("Linux files will NOT be encrypted: anyone with the disk or a lost "
                        "laptop can read them, including VM images and lab data.")
    if encrypted:
        warnings.append("A forgotten passphrase cannot be recovered; the encrypted data is then lost.")
        warnings.append(BOOT_NOTE)
    if choice == LUKS2_TPM2_PIN:
        warnings.append("TPM unlock is tied to firmware and Secure Boot state; updates can make "
                        "it ask for the fallback passphrase. TPM without a PIN is not offered "
                        "because a stolen laptop would unlock itself.")
    if coexist:
        warnings.append("If Windows uses BitLocker, save its recovery key BEFORE changing "
                        "partitions or boot settings; Windows may ask for it on next startup.")
    after = AFTER_INSTALL_STEPS + (TPM2_STEPS if choice == LUKS2_TPM2_PIN else ())
    return EncryptionPlan(
        choice=choice,
        label=LABELS[choice],
        linux_data_encrypted=encrypted,
        passphrase_or_pin_at_startup=encrypted,
        tpm2_pin_unlock=choice == LUKS2_TPM2_PIN,
        boot_partition_encrypted=False,
        efi_partition_encrypted=False,
        installer_steps=INSTALLER_STEPS if encrypted else (),
        after_install_steps=after if encrypted else (),
        warnings=tuple(warnings),
    )


def describe_encryption_plan(plan: EncryptionPlan) -> str:
    lines = [f"LINUX DISK ENCRYPTION: {plan.label}"]
    if plan.installer_steps:
        lines.append("In Fedora's installer:")
        lines.extend(f"  {n}. {step}" for n, step in enumerate(plan.installer_steps, 1))
    if plan.after_install_steps:
        lines.append("After installation:")
        lines.extend(f"  {n}. {step}" for n, step in enumerate(plan.after_install_steps, 1))
    lines.extend("! " + warning for warning in plan.warnings)
    return "\n".join(lines)


def _walk(node: Any, ancestors: tuple[dict, ...], found: dict[str, tuple[dict, ...]], depth: int = 0) -> None:
    if not isinstance(node, dict) or depth > 16:
        return
    chain = ancestors + (node,)
    mounts = node.get("mountpoints")
    if isinstance(mounts, list):
        for mount in mounts:
            if mount in ("/", "/home", "/boot", "/boot/efi") and mount not in found:
                found[mount] = chain
    children = node.get("children")
    if isinstance(children, list):
        for child in children[:256]:
            _walk(child, chain, found, depth + 1)


def _encrypted(chain: tuple[dict, ...]) -> bool:
    return any(item.get("type") == "crypt" for item in chain) and any(
        item.get("fstype") == "crypto_LUKS" for item in chain)


def inspect_encryption(lsblk: dict | None) -> dict:
    """Classify the running mounts from `lsblk -J` data; never writes."""
    found: dict[str, tuple[dict, ...]] = {}
    devices = lsblk.get("blockdevices") if isinstance(lsblk, dict) else None
    if isinstance(devices, list):
        for device in devices[:256]:
            _walk(device, (), found)
    mounts = {}
    for mount in ("/", "/home", "/boot", "/boot/efi"):
        chain = found.get(mount)
        if chain is None:
            mounts[mount] = "NOT_SEPARATELY_MOUNTED" if mount != "/" else "UNKNOWN"
            continue
        luks = next((item for item in chain if item.get("fstype") == "crypto_LUKS"), None)
        if _encrypted(chain):
            version = luks.get("fsver") if luks else None
            mounts[mount] = "ENCRYPTED_LUKS" + (str(version) if version in ("1", "2") else "")
        else:
            mounts[mount] = "NOT_ENCRYPTED"
    root = mounts["/"]
    home = mounts["/home"]
    if root == "UNKNOWN":
        status = "UNKNOWN"
    elif root.startswith("ENCRYPTED") and (
            home == "NOT_SEPARATELY_MOUNTED" or home.startswith("ENCRYPTED")):
        status = "ENCRYPTED"
    else:
        status = "NOT_ENCRYPTED"
    return {"status": status, "mounts": mounts, "read_only": True}


def collect_encryption() -> dict:
    """Run the fixed read-only lsblk query; failures become UNKNOWN."""
    try:
        done = subprocess.run(LSBLK_QUERY, shell=False, capture_output=True,
                              stdin=subprocess.DEVNULL, timeout=7, check=False)
        if done.returncode != 0 or not done.stdout or len(done.stdout) > MAX_LSBLK_BYTES:
            return inspect_encryption(None)
        return inspect_encryption(json.loads(done.stdout.decode("utf-8")))
    except (OSError, subprocess.TimeoutExpired, ValueError, RecursionError):
        return inspect_encryption(None)


def describe_encryption_status(report: dict) -> str:
    lines = [f"Linux disk encryption: {report['status']}"]
    lines.extend(f"  {mount}: {state}" for mount, state in report["mounts"].items())
    if report["status"] == "ENCRYPTED":
        lines.append("Root (and /home if separate) is on LUKS: a passphrase is needed at startup.")
    elif report["status"] == "NOT_ENCRYPTED":
        lines.append("Linux data is NOT on an encrypted volume. Encrypting an installed system "
                     "in place is risky; reinstalling with 'Encrypt my data' is the reliable way.")
    else:
        lines.append("Could not read the block-device layout; nothing is assumed.")
    if report["mounts"].get("/boot") == "NOT_ENCRYPTED":
        lines.append("/boot unencrypted is expected on Fedora; keep Secure Boot enabled.")
    return "\n".join(lines)
