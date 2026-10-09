from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Mapping


class JobPathError(ValueError):
    """Raised when a workflow job script cannot be resolved safely."""


_MISSING = object()
_TASK_ROOT_PREFIX = "task_root:"


def _safe_task_root(task_root: str | Path) -> Path:
    raw = Path(task_root).expanduser()
    if raw.is_symlink():
        raise JobPathError(f"unsafe task root: symlink is not allowed: {raw}")
    if not raw.exists() or not raw.is_dir():
        raise JobPathError(f"task root does not exist or is not a directory: {raw}")
    return raw.resolve()


def _relative_parts(value: str | Path, label: str) -> tuple[str, ...]:
    raw = str(value)
    if not raw or not raw.strip():
        raise JobPathError(f"unsafe {label}: path must be non-empty")
    if "\x00" in raw:
        raise JobPathError(f"unsafe {label}: NUL byte in path")

    # Validate both separators explicitly.  This keeps a Windows-style
    # ``..\\outside`` escape unsafe even when the helper is inspected on POSIX.
    normalized = raw.replace("\\", "/")
    if (
        normalized.startswith("/")
        or re.match(r"^[A-Za-z]:", normalized)
    ):
        raise JobPathError(f"unsafe {label}: absolute path is not allowed: {raw!r}")
    parts = tuple(normalized.split("/"))
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise JobPathError(f"unsafe {label}: path must not contain . or ..: {raw!r}")
    if any(":" in part for part in parts):
        raise JobPathError(f"unsafe {label}: invalid path component: {raw!r}")
    return parts


def _resolve_inside(root: Path, relative: str | Path, label: str) -> Path:
    parts = _relative_parts(relative, label)
    candidate = root.joinpath(*parts)
    current = root
    for part in parts:
        current = current / part
        if current.is_symlink():
            raise JobPathError(f"unsafe {label}: symlink component: {current}")
    try:
        resolved = candidate.resolve(strict=False)
    except (OSError, RuntimeError) as exc:
        raise JobPathError(f"unsafe {label}: cannot resolve path: {candidate}") from exc
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise JobPathError(f"unsafe {label}: path escapes task root: {relative!r}") from exc
    return resolved


def _input_references(workflow: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    inputs = workflow.get("inputs")
    if isinstance(inputs, Mapping):
        references = inputs.get("files", [])
    else:
        references = inputs
    if not isinstance(references, list):
        return []
    return [item for item in references if isinstance(item, Mapping)]


def _same_path(left: Path, right: Path) -> bool:
    return os.path.normcase(os.fspath(left)) == os.path.normcase(os.fspath(right))


def _check_collisions(root: Path, script_path: Path, workflow: Mapping[str, Any]) -> None:
    if script_path.name.casefold() == "workflow.json":
        raise JobPathError(f"reserved workflow path cannot be a job script: {script_path}")

    for reference in _input_references(workflow):
        if reference.get("base", "task_root") != "task_root":
            continue
        raw_path = reference.get("path", reference.get("name"))
        if not isinstance(raw_path, str) or not raw_path.strip():
            continue
        input_path = _resolve_inside(root, raw_path, "declared input")
        if _same_path(input_path, script_path):
            raise JobPathError(f"job script collides with declared input: {raw_path}")


def _require_regular_file(path: Path, *, required: bool, explicit: bool) -> Path:
    if path.is_symlink():
        raise JobPathError(f"unsafe job script: symlink is not allowed: {path}")
    if path.exists():
        if not path.is_file():
            raise JobPathError(f"job script is not a regular file: {path}")
        return path
    # An explicitly declared script is a required contract even when a caller
    # is otherwise allowed to handle legacy leaves without any script.
    if required or explicit:
        raise JobPathError(f"missing job script: {path}")
    return path


def resolve_job_script(
    task_root: str | Path, workflow: Mapping[str, Any], *, required: bool = True
) -> Path:
    """Resolve the safe executable script recorded by a workflow leaf.

    ``job.script`` may be either ``task_root:relative/path`` or a plain path
    relative to the task root.  A legacy ``job.sh`` is considered only when the
    ``job.script`` field is absent; ``required=False`` permits that legacy path
    to be absent while still rejecting a missing explicitly declared script.
    The returned path is resolved, remains inside ``task_root``, and is a
    regular non-symlink file when it exists.
    """

    if not isinstance(workflow, Mapping):
        raise JobPathError("workflow must be a mapping")
    root = _safe_task_root(task_root)
    job = workflow.get("job", _MISSING)
    explicit = False
    if job is _MISSING:
        raw_script: Any = "job.sh"
    else:
        if not isinstance(job, Mapping):
            raise JobPathError("workflow job must be a mapping")
        if "script" not in job:
            raw_script = "job.sh"
        else:
            raw_script = job["script"]
            explicit = True
            if not isinstance(raw_script, str):
                raise JobPathError("workflow job.script must be a string")
            if raw_script.startswith(_TASK_ROOT_PREFIX):
                raw_script = raw_script[len(_TASK_ROOT_PREFIX) :]

    if not isinstance(raw_script, str):
        raise JobPathError("workflow job.script must be a string")
    script_path = _resolve_inside(root, raw_script, "job script")
    _check_collisions(root, script_path, workflow)
    return _require_regular_file(script_path, required=required, explicit=explicit)
