# Security Policy

Midnight Provisioner is an open-source workstation setup utility and workspace controller for Fedora KDE.

---

## Realistic Security Model & Scope

> [!IMPORTANT]
> **No Magic Sandbox Disclaimer:**
> Midnight Provisioner is a local desktop application and CLI wrapper around standard Linux virtualization tools (`qemu:///system`, `libvirt`, `podman`, `distrobox`).
> - **Designed for Lower-Spec Hardware:** Midnight Provisioner was intentionally designed to run efficiently on modest/lower-spec laptops (e.g. 8 GB RAM). It uses automatic RAM caps (max 3.5 GiB per VM) and single active VM restrictions on devices under 11 GiB RAM to keep the host system stable and responsive.
- **Hypervisor Security:** Isolation relies entirely on standard Linux kernel capabilities, KVM/QEMU hypervisor boundaries, and Fedora SELinux policies.
> - **Not a Qubes OS Replacement:** Midnight Provisioner does not provide custom kernel isolation, microVMs, or hardware-enforced isolation.
> - **Malware Analysis Warning:** Restricted workspace profiles (`isolated` and `lab`) check libvirt XML definitions before launch, but are intended for controlled research—NOT for running high-risk or untrusted live malware without dedicated hardware isolation.

---

## Reporting Vulnerabilities

If you identify a security issue, logic bug, or policy check flaw in Midnight Provisioner:

1. **GitHub Issues:** Open an issue describing the vulnerability and steps to reproduce.
2. **Pull Requests:** If you have a fix for a security or policy validation flaw, PRs are welcome!

Please include:
- Affected component (CLI, PySide6 GUI, ISO kickstart, or libvirt policy check).
- Operating System & Fedora version.
- Exact steps to reproduce.

Thank you for helping keep Midnight Provisioner reliable and secure!
