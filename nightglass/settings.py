"""Persist only safe workspace metadata, never VM images, secrets or host modifications."""

from __future__ import annotations
import json
import os
from pathlib import Path
from .models import DEFAULT_WORKSPACES, Workspace, WorkspaceError
from .privatefiles import make_private


def config_file() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config"))
    return base / "nightglass" / "workspaces.json"


def load_workspaces(path: Path | None = None) -> list[Workspace]:
    path = path or config_file()
    if not path.exists():
        return list(DEFAULT_WORKSPACES)
    try:
        root = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(root, dict) or root.get("version") != 1 or not isinstance(root.get("workspaces"), list):
            raise WorkspaceError("Unsupported workspace settings version or structure")
        spaces = [Workspace(**entry) for entry in root["workspaces"]]
        if len(spaces) > 32 or len({s.key for s in spaces}) != len(spaces):
            raise WorkspaceError("Too many workspaces or duplicate workspace keys")
        vm_names = [s.identifier for s in spaces if s.kind == "vm" and s.identifier]
        if len(vm_names) != len(set(vm_names)):
            raise WorkspaceError("One VM cannot be bound to multiple security profiles")
        return spaces
    except (OSError, ValueError, TypeError) as exc:
        raise WorkspaceError(f"Could not load workspace configuration {path}: {exc}") from exc


def save_workspaces(spaces: list[Workspace], path: Path | None = None) -> None:
    path = path or config_file()
    if len(spaces) > 32 or len({w.key for w in spaces}) != len(spaces):
        raise WorkspaceError("Duplicate keys or too many workspaces")
    vm_names = [w.identifier for w in spaces if w.kind == "vm" and w.identifier]
    if len(vm_names) != len(set(vm_names)):
        raise WorkspaceError("One VM cannot be bound to multiple security profiles")
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.is_symlink():
        raise WorkspaceError("Refusing to replace symlinked workspace configuration")
    content = json.dumps({"version": 1, "workspaces": [w.serialize() for w in spaces]}, indent=2) + "\n"
    tmp = path.parent / f".{path.name}.{os.getpid()}.tmp"
    try:
        with tmp.open("x", encoding="utf-8") as fh:
            make_private(fh.fileno())
            fh.write(content)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
