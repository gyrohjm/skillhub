"""Machine-local environment data. Credentials remain managed by SSH."""
from __future__ import annotations

import json
import os
from pathlib import Path


def config_dir() -> Path:
    raw = Path(os.environ.get("DFT_SKILLS_CONFIG_DIR", "~/.config/dft-skills")).expanduser()
    if not raw.is_absolute():
        raise ValueError("DFT_SKILLS_CONFIG_DIR must be absolute")
    root = raw.resolve()
    for path in (raw, root):
        if any((parent / ".git").exists() for parent in (path, *path.parents)):
            raise ValueError("DFT private configuration must be outside Git worktrees")
    return root


def read_private_json(name: str, *, default=None):
    if Path(name).name != name or name in {".", ".."}:
        raise ValueError("Private JSON name must be a file name")
    root = config_dir()
    path = root / name
    if path.is_symlink():
        raise ValueError("Private configuration must not be a symlink")
    if not path.is_file():
        if path.exists():
            raise ValueError("Private configuration must be a regular file")
        return default
    if path.is_symlink() or root.stat().st_mode & 0o077 or path.stat().st_mode & 0o077:
        raise ValueError("Private configuration requires directory 0700 and file 0600 permissions")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError):
        raise ValueError("Invalid private JSON configuration") from None


def load_profile(name: str) -> dict:
    data = read_private_json("profiles.json", default={"profiles": {}})
    if not isinstance(data, dict) or set(data) != {"profiles"} or not isinstance(data["profiles"], dict):
        raise ValueError("profiles.json must contain a profiles object")
    if name == "generic" and name not in data["profiles"]:
        return {}
    if name not in data["profiles"]:
        raise ValueError("Unknown local profile; configure profiles.json or use generic with explicit parameters")
    profile = data["profiles"][name]
    if not isinstance(profile, dict) or set(profile) - {"resources", "project_root", "potcar_root"}:
        raise ValueError("Invalid local profile fields")
    for key in ("project_root", "potcar_root"):
        if key in profile and (not isinstance(profile[key], str) or not Path(profile[key]).is_absolute()):
            raise ValueError("Local profile paths must be absolute")
    resources = profile.get("resources", {})
    text_keys = {"partition", "qos", "account", "nodelist", "gres", "time", "vasp_cmd"}
    number_keys = {"nodes", "ntasks_per_node", "cpus_per_task"}
    if not isinstance(resources, dict) or set(resources) - text_keys - number_keys:
        raise ValueError("Invalid local resource fields")
    for key, value in resources.items():
        if key in number_keys:
            if type(value) is not int or value < 1:
                raise ValueError("Local resource counts must be positive integers")
        elif not isinstance(value, str):
            raise ValueError("Local resource values must be strings")
    return profile


def preserve_private_files(files: dict[str, bytes]) -> Path:
    """Copy a batch without overwriting conflicts; callers clean sources only after success."""
    root = config_dir()
    targets = []
    for name, content in files.items():
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts or not relative.parts:
            raise ValueError("Private file names must be relative")
        target = root / relative
        if any(p.is_symlink() for p in (target, *target.parents) if p != root.parent):
            raise ValueError("Private destinations must not contain symlinks")
        if target.exists() and (not target.is_file() or target.read_bytes() != content):
            raise ValueError("Private migration conflict; existing files were not overwritten")
        targets.append((target, content))
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    root.chmod(0o700)
    for target, content in targets:
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        for parent in target.parents:
            if parent == root.parent:
                break
            parent.chmod(0o700)
        if not target.exists():
            fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as handle:
                handle.write(content)
        target.chmod(0o600)
        if target.read_bytes() != content:
            raise ValueError("Private migration verification failed; keep source files")
    return root


if __name__ == "__main__":
    print(config_dir())
