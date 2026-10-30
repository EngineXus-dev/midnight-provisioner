"""Owner-only permissions for files Midnight Provisioner creates."""
from __future__ import annotations

import os


def make_private(fd: int) -> None:
    """chmod 0600 on POSIX. Windows has no os.fchmod; there the new file
    inherits the parent folder's ACL (the user's own profile folders)."""
    if hasattr(os, "fchmod"):
        os.fchmod(fd, 0o600)
