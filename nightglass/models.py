"""Workspace data and policy models. No commands or environment evaluation in config."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Literal
import re

WorkspaceKind = Literal["host", "vm", "distrobox"]
WorkspacePolicy = Literal["host", "trusted", "isolated", "lab"]
NAME_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,62}$")


class WorkspaceError(ValueError):
    pass


def safe_name(name: str) -> str:
    if not isinstance(name, str) or not NAME_PATTERN.fullmatch(name):
        raise WorkspaceError("Identifiers must be 1-63 characters: A-Z, a-z, 0-9, ., _ or - (starting with an alphanumeric character).")
    return name


@dataclass(frozen=True)
class Workspace:
    key: str
    name: str
    kind: WorkspaceKind
    identifier: str
    policy: WorkspacePolicy
    detail: str
    accent: str = "cyan"

    def __post_init__(self) -> None:
        safe_name(self.key)
        if self.kind not in {"host", "vm", "distrobox"}:
            raise WorkspaceError(f"Unsupported workspace kind: {self.kind}")
        if self.policy not in {"host", "trusted", "isolated", "lab"}:
            raise WorkspaceError(f"Unsupported policy: {self.policy}")
        if self.kind == "host" and self.policy != "host":
            raise WorkspaceError("Host workspaces must use host policy")
        if self.kind == "distrobox" and self.policy != "trusted":
            raise WorkspaceError("Distrobox can only be registered as trusted, never isolated")
        if self.kind == "vm" and self.policy == "host":
            raise WorkspaceError("VMs cannot use the host policy")
        if self.identifier:
            safe_name(self.identifier)

    def serialize(self) -> dict:
        return asdict(self)


DEFAULT_WORKSPACES = (
    Workspace("personal", "Personal Desktop", "host", "", "host", "Fedora KDE: personal applications, media, and browsing", "cyan"),
    Workspace("development", "Trusted Development", "distrobox", "nightglass-dev", "trusted", "Rootless Podman / Distrobox. Shares host files: trusted code ONLY", "violet"),
    Workspace("pentest", "Authorized Pentesting", "vm", "nightglass-kali", "lab", "Dedicated Kali VM. Offline or approved no-forward lab network", "amber"),
    Workspace("analysis", "Malware Analysis", "vm", "nightglass-malware", "isolated", "Disposable VM. Network, host shares and device passthrough forbidden", "red"),
)
