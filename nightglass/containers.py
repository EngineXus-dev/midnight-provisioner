"""Distrobox integration for TRUSTED development only (not a security sandbox)."""
from __future__ import annotations
from .models import safe_name
from .runner import Runner, ToolError

SAFE_DEV_IMAGES = {
    "ubuntu-24.04": "docker.io/library/ubuntu:24.04",
    "debian-12": "docker.io/library/debian:12",
    "arch": "docker.io/library/archlinux:latest",
    "fedora": "registry.fedoraproject.org/fedora:latest",
}


class Containers:
    def __init__(self, runner: Runner | None = None):
        self.runner = runner or Runner()

    def list_names(self) -> list[str]:
        # Output uses ID | NAME | STATUS | IMAGE. No dependence on status/color.
        output = self.runner.run(["distrobox", "list", "--no-color"], timeout=20).stdout
        names = []
        for line in output.splitlines()[1:]:
            columns = [c.strip() for c in line.split("|")]
            if len(columns) >= 4 and columns[1]:
                names.append(columns[1])
        return names

    def create(self, name: str, image_alias: str = "ubuntu-24.04") -> str:
        safe_name(name)
        if image_alias not in SAFE_DEV_IMAGES:
            raise ToolError("Only reviewed image aliases are supported")
        if name in self.list_names():
            raise ToolError("Distrobox name already exists")
        return self.runner.run(
            ["distrobox", "create", "--name", name, "--image", SAFE_DEV_IMAGES[image_alias], "--yes"],
            timeout=240,
        ).stdout.strip() or f"Created trusted environment {name}"
