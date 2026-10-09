#!/usr/bin/env python3
"""Create and validate the lineage manifest kept with each presentation project."""

from __future__ import annotations

import json
import os
import re
import argparse
import hashlib
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence

from skill_runtime import require_current


MANIFEST_NAME = "project.json"
PROJECT_SKILL_ROOT = Path(__file__).resolve().parents[1]
SUPPORTED_FORMATS = frozenset({"pptx", "beamer"})


class ProjectManifestError(RuntimeError):
    """The manifest cannot be created or is not a valid project manifest."""


class ProjectManifestConflictError(ProjectManifestError):
    """An existing project manifest or directory would be overwritten."""


def _manifest_path(project_dir: Path) -> Path:
    root = project_dir.resolve()
    candidate = root / MANIFEST_NAME
    try:
        candidate.resolve().relative_to(root)
    except ValueError as exc:
        raise ProjectManifestError(
            f"project manifest path escapes project directory: {candidate}"
        ) from exc
    return candidate


def _project_id(value: str | None, project_dir: Path) -> str:
    raw = value if value is not None else project_dir.name
    if not isinstance(raw, str) or not raw.strip():
        raw = "presentation"
    raw = raw.strip()
    if raw in {".", ".."} or "/" in raw or "\\" in raw:
        raise ProjectManifestError(f"project_id must be a single path component: {raw!r}")
    slug = re.sub(r"[^\w.-]+", "-", raw, flags=re.UNICODE).strip(".-")
    if not slug:
        raise ProjectManifestError("project_id must contain at least one usable character")
    return slug


def _format(value: str) -> str:
    if not isinstance(value, str):
        raise ProjectManifestError("format must be a string")
    normalized = value.strip().casefold()
    if normalized not in SUPPORTED_FORMATS:
        raise ProjectManifestError(
            f"unsupported presentation format {value!r}; choose pptx or beamer"
        )
    return normalized


def _source_entries(values: Sequence[str] | None) -> list[str]:
    if values is not None and isinstance(values, (str, bytes)):
        raise ProjectManifestError("source_entries must be a list of entry IDs")
    result: list[str] = []
    for value in values or ():
        if not isinstance(value, str) or not value.strip():
            raise ProjectManifestError("source_entries must contain non-empty entry IDs")
        entry_id = value.strip()
        if entry_id in {".", ".."} or "/" in entry_id or "\\" in entry_id:
            raise ProjectManifestError(f"source_entries must contain entry IDs: {value!r}")
        if entry_id not in result:
            result.append(entry_id)
    return result


def _validate_manifest(value: Mapping[str, Any]) -> dict[str, Any]:
    required = (
        "project_id",
        "format",
        "created_from",
        "source_entries",
        "template_version",
        "status",
    )
    missing = [key for key in required if key not in value]
    if missing:
        raise ProjectManifestError(f"project manifest is missing fields: {', '.join(missing)}")
    project_id = value["project_id"]
    if not isinstance(project_id, str) or not project_id.strip():
        raise ProjectManifestError("project_id must be a non-empty string")
    if "/" in project_id or "\\" in project_id:
        raise ProjectManifestError("project_id must be a single path component")
    created_from = value["created_from"]
    if not isinstance(created_from, str) or not created_from.strip():
        raise ProjectManifestError("created_from must be a non-empty source description")
    template_version = value["template_version"]
    if not isinstance(template_version, str) or not template_version.strip():
        raise ProjectManifestError("template_version must be a non-empty string")
    status = value["status"]
    if not isinstance(status, str) or not status.strip():
        raise ProjectManifestError("status must be a non-empty string")
    return {
        "schema_version": value.get("schema_version", 1),
        "project_id": project_id.strip(),
        "format": _format(value["format"]),
        "created_from": created_from.strip(),
        "source_entries": _source_entries(value["source_entries"]),
        "template_version": template_version.strip(),
        "status": status.strip(),
    }


def template_version_from_runtime(runtime: Mapping[str, Any]) -> str:
    """Return the stable template identifier from ``require_current`` output."""

    digest = runtime.get("project_skill_sha256")
    alias = runtime.get("skill_sha256")
    if digest is not None and alias is not None and digest != alias:
        raise ProjectManifestError(
            "skill runtime reported conflicting project_skill_sha256 and skill_sha256"
        )
    if digest is None:
        digest = alias
    if not isinstance(digest, str) or not digest:
        raise ProjectManifestError(
            "skill runtime did not report project_skill_sha256 or skill_sha256"
        )
    return f"super-simple-sci-ppt:sha256:{digest}"


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def create_project_manifest(
    project_dir: Path,
    *,
    format: str = "pptx",
    project_id: str | None = None,
    created_from: str | None = None,
    source_entries: Sequence[str] = (),
    template_version: str | None = None,
    status: str = "draft",
    runtime: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the deterministic six-field project manifest without writing it.

    Pure callers and tests may pass ``template_version`` explicitly.  When it
    is omitted, the current portable skill package is checked and its package
    hash becomes the template version.
    """

    destination = Path(project_dir).resolve()
    entries = _source_entries(source_entries)
    if created_from is None:
        created_from = entries[0] if len(entries) == 1 else "new"
    if not isinstance(created_from, str) or not created_from.strip():
        raise ProjectManifestError("created_from must be a non-empty source description")
    if template_version is None:
        runtime = runtime or require_current()
        template_version = template_version_from_runtime(runtime)
    manifest = {
        "schema_version": 1,
        "project_id": _project_id(project_id, destination),
        "format": _format(format),
        "created_from": created_from.strip(),
        "source_entries": entries,
        "template_version": template_version,
        "status": status.strip() if isinstance(status, str) else status,
    }
    return _validate_manifest(manifest)


def load_project_manifest(project_dir: Path) -> dict[str, Any]:
    """Read and validate ``project.json`` from a project directory."""

    path = _manifest_path(Path(project_dir))
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise
    except (OSError, json.JSONDecodeError) as exc:
        raise ProjectManifestError(f"cannot read project manifest: {path}") from exc
    if not isinstance(value, Mapping):
        raise ProjectManifestError(f"project manifest must be an object: {path}")
    return _validate_manifest(value)


def write_project_manifest(project_dir: Path, manifest: Mapping[str, Any]) -> bool:
    """Write a manifest atomically, refusing a different existing file."""

    normalized = _validate_manifest(manifest)
    destination = Path(project_dir).resolve()
    path = _manifest_path(destination)
    encoded = (
        json.dumps(normalized, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    if path.exists():
        if not path.is_file():
            raise ProjectManifestConflictError(f"project manifest path is not a file: {path}")
        try:
            if load_project_manifest(destination) == normalized:
                return False
        except (ProjectManifestError, OSError):
            pass
        raise ProjectManifestConflictError(f"project manifest conflict: {path}")
    destination.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{MANIFEST_NAME}.", suffix=".tmp", dir=destination)
    temp_path = Path(temporary)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
        # Linking publishes the complete file without replacing a file that
        # another process created after our check (os.replace would overwrite).
        os.link(temp_path, path)
    except FileExistsError as exc:
        try:
            if path.is_file() and load_project_manifest(destination) == normalized:
                return False
        except (ProjectManifestError, OSError):
            pass
        raise ProjectManifestConflictError(f"project manifest conflict: {path}") from exc
    except OSError as exc:
        raise ProjectManifestError(f"cannot write project manifest: {path}") from exc
    finally:
        temp_path.unlink(missing_ok=True)
    return True


def init_project(
    project_dir: Path,
    *,
    format: str | None = None,
    project_id: str | None = None,
    created_from: str | None = None,
    source_entries: Sequence[str] | None = None,
    template_version: str | None = None,
    status: str | None = None,
    runtime: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a project manifest, with idempotent same-content retries."""

    destination = Path(project_dir).resolve()
    manifest_path = _manifest_path(destination)
    existing: dict[str, Any] | None = None
    if manifest_path.exists():
        try:
            existing = load_project_manifest(destination)
        except ProjectManifestError as exc:
            raise ProjectManifestConflictError(
                f"existing project manifest is invalid: {manifest_path}"
            ) from exc
        # A routine re-run after the skill has advanced must not rewrite the
        # existing project's lineage.  ``None`` means “reuse the value already
        # recorded”; passing a different value is an explicit conflict.
        if format is None:
            format = existing["format"]
        if project_id is None:
            project_id = existing["project_id"]
        if created_from is None:
            created_from = existing["created_from"]
        if source_entries is None:
            source_entries = existing["source_entries"]
        if status is None:
            status = existing["status"]
        if template_version is None:
            template_version = existing["template_version"]
    else:
        if runtime is None and template_version is None:
            runtime = require_current()
        if format is None:
            format = "pptx"
        if source_entries is None:
            source_entries = ()
        if status is None:
            status = "draft"
    manifest = create_project_manifest(
        destination,
        format=format or "pptx",
        project_id=project_id,
        created_from=created_from,
        source_entries=source_entries or (),
        template_version=template_version,
        status=status or "draft",
        runtime=runtime,
    )
    if existing is not None:
        if existing == manifest:
            return existing
        raise ProjectManifestConflictError(f"project manifest conflict: {manifest_path}")
    if destination.exists() and not destination.is_dir():
        raise ProjectManifestConflictError(f"project path is not a directory: {destination}")
    if destination.is_dir() and any(destination.iterdir()):
        raise ProjectManifestConflictError(
            f"cannot initialize non-empty directory without a manifest: {destination}"
        )
    write_project_manifest(destination, manifest)
    return manifest


def cli_main(
    argv: Sequence[str] | None = None,
    *,
    require_runtime=None,
) -> int:
    """CLI entry point for creating a new project manifest.

    ``--existing`` follows ``select_workflow.py``: it participates in format
    selection, and the editable source must actually exist before its path is
    recorded in ``created_from``.
    """

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_dir", nargs="?", type=Path)
    parser.add_argument("--output-dir", dest="output_dir", type=Path)
    parser.add_argument("--format", choices=sorted(SUPPORTED_FORMATS))
    parser.add_argument("--beamer", action="store_true", help="select the Beamer format")
    parser.add_argument("--existing", type=Path, help="editable source being continued")
    parser.add_argument("--project-id")
    parser.add_argument(
        "--source-entry",
        "--source-entries",
        dest="source_entries",
        action="append",
        default=[],
        metavar="ENTRY_ID",
    )
    parser.add_argument("--created-from")
    parser.add_argument("--template-version")
    args = parser.parse_args(argv)
    if args.project_dir is not None and args.output_dir is not None:
        if args.project_dir.resolve() != args.output_dir.resolve():
            parser.error("use either PROJECT_DIR or --output-dir, not two different paths")
    project_dir = args.output_dir or args.project_dir
    if project_dir is None:
        parser.error("init requires PROJECT_DIR or --output-dir")
    try:
        runtime = (require_runtime or require_current)()
        existing = args.existing.resolve() if args.existing is not None else None
        if existing is not None and not existing.is_file():
            raise ProjectManifestError(f"--existing must name an existing editable file: {existing}")
        explicit_format = "beamer" if args.beamer else args.format
        existing_format = None
        from select_workflow import select_format

        manifest_path = _manifest_path(Path(project_dir))
        if existing is not None:
            # select_format validates the source even when an explicit target
            # format wins (notably, article TeX is still rejected).
            selected_format = select_format(explicit_format, str(existing))
            try:
                existing_format = select_format(None, str(existing))
            except ValueError:
                # A PDF needs explicit format and therefore cannot establish
                # an inherited-source template fingerprint by itself.
                existing_format = None
        elif explicit_format is not None:
            selected_format = select_format(explicit_format)
        elif manifest_path.exists():
            # Re-running the CLI without options reuses the project's recorded
            # format, which keeps an existing manifest idempotent.
            selected_format = load_project_manifest(Path(project_dir))["format"]
        else:
            selected_format = select_format(None)
        created_from = args.created_from
        if created_from is None and existing is not None:
            created_from = str(existing)
        template_version = args.template_version
        if template_version is None:
            if not manifest_path.exists():
                template_version = (
                    f"inherited-source:sha256:{_file_sha256(existing)}"
                    if existing is not None and selected_format == existing_format
                    else template_version_from_runtime(runtime)
                )
        manifest = init_project(
            project_dir,
            format=selected_format,
            project_id=args.project_id,
            created_from=created_from,
            source_entries=args.source_entries or None,
            template_version=template_version,
            runtime=runtime,
        )
    except (ProjectManifestError, OSError, RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(manifest, ensure_ascii=False, sort_keys=True))
    return 0


def main() -> None:
    raw_argv = list(sys.argv[1:])
    if raw_argv and raw_argv[0] == "init":
        raw_argv = raw_argv[1:]
    raise SystemExit(cli_main(raw_argv))


__all__ = [
    "MANIFEST_NAME",
    "PROJECT_SKILL_ROOT",
    "SUPPORTED_FORMATS",
    "ProjectManifestError",
    "ProjectManifestConflictError",
    "create_project_manifest",
    "cli_main",
    "init_project",
    "load_project_manifest",
    "require_current",
    "template_version_from_runtime",
    "write_project_manifest",
]


if __name__ == "__main__":
    main()
