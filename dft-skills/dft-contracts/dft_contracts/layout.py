from __future__ import annotations

import re
import json
import os
from pathlib import Path


PROJECT_MARKERS = ("AGENTS.md", "README.md", "README.rst", "pyproject.toml", ".git")
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
PROJECT_FILE = "dft-project.json"
STAGE_RE = re.compile(r"(?:p[0-9]+|[0-9]{2,})(?:_[a-z0-9]+)*\Z")


def project_role(root: Path) -> str | None:
    path = root / PROJECT_FILE
    role = json.loads(path.read_text()).get("storage_role") if path.is_file() else None
    if role not in {None, "local", "cluster", "preparation"}:
        raise ValueError("Unknown project storage_role")
    return role


def final_directory(root: Path) -> Path:
    return root / ("analysis" if project_role(root) == "local" else "results")


def stage_root(start: str | Path) -> Path | None:
    route = route_for(start)
    if route:
        parts = Path(start).resolve().relative_to(route[0]).parts
        if parts and STAGE_RE.fullmatch(parts[0]):
            return route[0] / parts[0]
    return None


def project_routes(root: Path) -> list[dict]:
    """Read explicit, portable route identities; never infer identity from aliases."""
    path = root / PROJECT_FILE
    if not path.exists():
        return []
    if path.is_symlink():
        raise ValueError("Project manifest must not be a symlink")
    data = json.loads(path.read_text())
    if not isinstance(data, dict) or data.get("schema_version") != 1 or not isinstance(data.get("routes"), list):
        raise ValueError("Invalid dft-project.json")
    paths = []
    for route in data["routes"]:
        if not isinstance(route, dict):
            raise ValueError("Invalid route record")
        relative = Path(route.get("path", ""))
        if (not relative.parts or relative.is_absolute() or any(not SLUG_RE.fullmatch(p) for p in relative.parts)
                or relative.parts[0] in {"results", "analysis", "archive", "docs", "code", "shared"}):
            raise ValueError("Route requires a safe relative calculation path")
        target = root / relative
        if any(p.is_symlink() for p in (target, *target.parents) if p != root and root in p.parents):
            raise ValueError("Route path must not contain symlinks")
        ensure_within(root, target)
        for other in paths:
            if relative == other or relative in other.parents or other in relative.parents:
                raise ValueError("Routes must not overlap")
        paths.append(relative)
        _validate_slug(route.get("composition"), "composition")
        _validate_slug(route.get("structure"), "structure")
    return data["routes"]


def route_for(start: str | Path, composition=None, structure=None) -> tuple[Path, dict] | None:
    root = discover_workspace(start)
    routes = project_routes(root)
    current = Path(start).resolve()
    matches = [r for r in routes if (composition is None or r["composition"] == composition)
               and (structure is None or r["structure"] == structure)]
    within = [r for r in matches if current == root / r["path"] or root / r["path"] in current.parents]
    if within:
        return root / within[0]["path"], within[0]
    if composition is None:
        return None
    if current != root and (root / PROJECT_FILE).exists():
        raise ValueError("The requested path is not inside the matching registered route")
    if len(matches) != 1:
        if (root / PROJECT_FILE).exists():
            raise ValueError("Select a registered route explicitly; scope is missing or ambiguous")
        return None
    return root / matches[0]["path"], matches[0]


def calculation_scope(start: str | Path, composition: str, structure: str) -> Path:
    route = route_for(start, composition, structure)
    if route:
        return route[0]
    return calculations_root(start) / _validate_slug(composition, "composition") / _validate_slug(structure, "structure")


def plan_readme_path(design: Path) -> Path:
    if not any((p / PROJECT_FILE).is_file() for p in design.parents):
        return design.parent / "README.md"
    route = route_for(design)
    return design.parent / ("plan.md" if route and design.parent == route[0] / "docs" else "README.md")


def workflow_paths(root: Path):
    """Prune scratch, software and attempt snapshots before traversing task trees."""
    bases = [root / r["path"] for r in project_routes(root)]
    if (root / "calculations").is_dir() and not any(root / "calculations" == p or root / "calculations" in p.parents for p in bases):
        bases.append(root / "calculations")
    excluded = {"attempts", "analysis", "shared", "refs", "scripts", "code", "docs", "software", "tmp", "archive"}
    for base in bases:
        for folder, dirs, files in os.walk(base, followlinks=False):
            dirs[:] = sorted(d for d in dirs if d not in excluded and not d.startswith(".")
                             and not d.endswith(".save") and not d.startswith("tmp_")
                             and not (Path(folder) / d).is_symlink())
            if "workflow.json" in files:
                yield Path(folder) / "workflow.json"


def discover_workspace(start: str | Path) -> Path:
    """Return the nearest project root that owns a calculations directory.

    A directory is accepted only when it contains both ``calculations/`` and a
    project marker. This prevents DFT helpers from guessing a machine-specific
    root or treating an unrelated parent directory as the workspace.
    """

    resolved = Path(start).expanduser().resolve()
    current = resolved.parent if resolved.is_file() else resolved
    for candidate in (current, *current.parents):
        if (candidate / PROJECT_FILE).is_file():
            project_routes(candidate)
            return candidate
        if not (candidate / "calculations").is_dir():
            continue
        if any((candidate / marker).exists() for marker in PROJECT_MARKERS):
            return candidate
    raise ValueError(
        f"cannot discover workspace root from {resolved}: expected a parent "
        "containing calculations/ and AGENTS.md, README, pyproject.toml, or .git"
    )


def calculations_root(start: str | Path) -> Path:
    """Resolve the canonical calculations root for a path in a workspace."""

    return (discover_workspace(start) / "calculations").resolve()


def plans_root(start: str | Path) -> Path:
    """Resolve the root for composition/structure-scoped design plans."""

    return (discover_workspace(start) / "plans").resolve()


def logs_root(start: str | Path) -> Path:
    """Resolve the root for human-readable derived task timelines."""

    return (discover_workspace(start) / "logs").resolve()


def code_root(start: str | Path) -> Path:
    """Resolve the project-level root for reusable programs and templates."""

    return (discover_workspace(start) / "code").resolve()


def _validate_slug(value: str, label: str) -> str:
    if not isinstance(value, str) or not SLUG_RE.fullmatch(value):
        raise ValueError(
            f"{label} slug must use lowercase ASCII letters, digits, '-' or '_': {value!r}"
        )
    return value


def design_plan_root(
    start: str | Path, composition_slug: str, structure_slug: str
) -> Path:
    """Resolve ``plans/<composition>/<structure>`` inside the workspace."""

    route = route_for(start, composition_slug, structure_slug)
    if route:
        return route[0] / "docs"
    root = plans_root(start)
    candidate = root / _validate_slug(composition_slug, "composition") / _validate_slug(
        structure_slug, "structure"
    )
    return ensure_within(root, candidate)


def structure_log_path(
    start: str | Path, composition_slug: str, structure_slug: str
) -> Path:
    """Resolve ``logs/<composition>/<structure>.md`` inside the workspace."""

    route = route_for(start, composition_slug, structure_slug)
    if route:
        return route[0] / "docs/log.md"
    root = logs_root(start)
    candidate = root / _validate_slug(composition_slug, "composition") / (
        f"{_validate_slug(structure_slug, 'structure')}.md"
    )
    return ensure_within(root, candidate)


def ensure_within(root: str | Path, candidate: str | Path) -> Path:
    """Resolve ``candidate`` and reject paths that escape ``root``."""

    resolved_root = Path(root).expanduser().resolve()
    resolved_candidate = Path(candidate).expanduser().resolve()
    try:
        resolved_candidate.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError(
            f"path is outside allowed root: {resolved_candidate} is not under {resolved_root}"
        ) from exc
    return resolved_candidate
