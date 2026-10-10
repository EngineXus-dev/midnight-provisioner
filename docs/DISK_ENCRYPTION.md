# Linux disk encryption at startup

Nightglass plans Fedora disk encryption; **Fedora's installer performs it**. Nightglass never formats, partitions or encrypts a disk itself.

## Choices

| Choice | What happens at startup | Notes |
|---|---|---|
| `luks2` (recommended) | Fedora asks for your passphrase before any Linux data can be read | Installer: tick **Encrypt my data**, keep LUKS2 |
| `luks2-tpm2-pin` | TPM2 unlocks only with your PIN and an unchanged Secure Boot state | Same install step, then enroll TPM2 + PIN after install; passphrase stays as fallback |
| `none` | No prompt; anyone with the disk can read Linux files | Not recommended |

TPM2 without a PIN is deliberately not offered: a stolen laptop would unlock itself.

## Why /boot is not encrypted

The firmware must read `/boot` (kernel and initramfs) and the EFI partition to start Linux and display the passphrase prompt. Fedora's installer does not support encrypting `/boot`, and GRUB's limited support (LUKS1 / PBKDF2) breaks easily on updates. These partitions contain no personal files. Keep **Secure Boot enabled** so they cannot be silently replaced.

## After installing

```bash
nightglass encryption-check
```

Read-only (`lsblk`). Reports `ENCRYPTED` only when `/` and a separately mounted `/home` are inside a LUKS container; exit code 0 only in that case. Optionally back up the LUKS header to separate encrypted media:

```bash
sudo cryptsetup luksHeaderBackup <luks-partition> --header-backup-file <file>
```

For `luks2-tpm2-pin`:

```bash
mokutil --sb-state                       # Secure Boot must be enabled
sudo systemd-cryptenroll --tpm2-device=auto --tpm2-with-pin=yes --tpm2-pcrs=7 <luks-partition>
# add tpm2-device=auto to the volume's options in /etc/crypttab, then:
sudo dracut -f
```

## Dual boot with Windows

If Windows uses BitLocker, save its recovery key **before** changing partitions or boot settings; Windows may ask for it on the next startup.

A forgotten LUKS passphrase cannot be recovered.
