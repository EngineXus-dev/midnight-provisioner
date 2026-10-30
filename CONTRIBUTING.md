# Contributing to Midnight Provisioner

Thank you for your interest in contributing to **Midnight Provisioner**!

Midnight Provisioner is a open-source workstation setup tool and local workspace launcher for Fedora KDE. Contributions—from bug fixes and documentation enhancements to code refactoring—are always appreciated.

---

## Getting Started

1. **Fork the Repository:** Create a fork on GitHub and clone it locally.
2. **Environment Setup:** On Fedora Linux (39+), run:
   ```bash
   bash scripts/install/setup-midnight-provisioner.sh
   ```
3. **Run Unit Tests:** Before making changes, verify that all unit tests pass:
   ```bash
   python3 -m unittest discover tests
   ```

---

## Guidelines for Contributions

- **Keep It Simple & Realistic:** Midnight Provisioner is designed as a productivity tool and launcher. Avoid adding bloated or unnecessary third-party dependencies.
- **Maintain Security Expectations:** Do not make exaggerated security claims. Security isolation relies on standard Linux KVM/libvirt, Podman, and Fedora SELinux policies.
- **Code Style:** Follow standard PEP 8 naming and formatting conventions for Python code.
- **Test Coverage:** Ensure any new CLI or UI features include corresponding unit tests in the `tests/` directory.

---

## Submitting Pull Requests

1. Create a descriptive branch (`git checkout -b feature/my-feature` or `fix/my-bugfix`).
2. Commit your changes with clear, concise commit messages.
3. Push your branch to your fork and submit a Pull Request to the `main` branch.
4. Briefly describe the motivation and test results in your PR.

Thank you for helping improve Midnight Provisioner!
