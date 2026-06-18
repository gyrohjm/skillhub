#!/usr/bin/env python3
"""Preview or approve promotion of a validated artifact into formal_data."""

from __future__ import annotations

import argparse
import csv
import hashlib
import os
import re
import shutil
import sys
import uuid
from datetime import date
from pathlib import Path


CATEGORIES = {"plot_data", "figures", "tables", "structures", "supplementary"}
NAME_RE = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*(?:\.[a-z0-9]+)?$")
MANIFEST_FIELDS = [
    "artifact_path",
    "artifact_type",
    "source_file",
    "source_data",
    "processing_code",
    "parameters",
    "validation",
    "approved_by",
    "approved_date",
    "manuscript_usage",
    "sha256",
]


def normalize_filename(name: str) -> str:
    path = Path(name)
    if any(ord(char) > 127 for char in name):
        raise ValueError("Non-ASCII source names require an explicit English --destination-name")
    stem = re.sub(r"[^a-z0-9]+", "_", path.stem.lower()).strip("_")
    stem = re.sub(r"_+", "_", stem)
    if not stem:
        raise ValueError("Cannot derive an English lowercase_snake_case destination name")
    if stem[0].isdigit():
        stem = f"artifact_{stem}"
    suffix = path.suffix.lower()
    return stem + suffix


def validate_destination_name(name: str) -> None:
    if Path(name).name != name or not NAME_RE.fullmatch(name):
        raise ValueError(
            "destination name must be an English lowercase_snake_case filename "
            f"without directories; got {name!r}"
        )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_manifest_header(path: Path) -> list[str]:
    if not path.exists():
        raise ValueError(f"Missing formal-data manifest: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        header = next(reader, [])
    if header != MANIFEST_FIELDS:
        raise ValueError(f"Unexpected manifest columns in {path}: {header}")
    return header


def required_metadata(args: argparse.Namespace) -> dict[str, str]:
    values = {
        "source_data": args.source_data,
        "processing_code": args.processing_code,
        "parameters": args.parameters,
        "validation": args.validation,
        "approved_by": args.approved_by,
        "manuscript_usage": args.manuscript_usage,
    }
    missing = [key for key, value in values.items() if not value]
    if missing:
        raise ValueError(f"--approve requires metadata: {', '.join(missing)}")
    return values


def append_manifest(path: Path, row: dict[str, str]) -> None:
    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MANIFEST_FIELDS)
        writer.writerow(row)


def promote(args: argparse.Namespace) -> None:
    project = args.project.resolve()
    source = args.source.resolve()
    formal_root = project / "formal_data"
    manifest = formal_root / "MANIFEST.csv"

    if not source.is_file():
        raise ValueError(f"Source artifact does not exist or is not a file: {source}")
    if not (project / "raw_data").is_dir() or not (project / "code").is_dir():
        raise ValueError(f"Not an initialized research project: {project}")
    if args.category not in CATEGORIES:
        raise ValueError(f"Unsupported category: {args.category}")
    read_manifest_header(manifest)

    destination_name = args.destination_name or normalize_filename(source.name)
    validate_destination_name(destination_name)
    destination_dir = formal_root / args.category
    destination = destination_dir / destination_name
    if destination.exists():
        raise ValueError(f"Formal artifact already exists; choose a new versioned name: {destination}")

    print(f"Project          : {project}")
    print(f"Source           : {source}")
    print(f"Destination      : {destination}")
    print(f"Category         : {args.category}")
    print("Source operation : copy (source is preserved)")
    print("Overwrite        : disabled")

    if args.dry_run:
        print("\nDry run complete: no artifact or manifest row was written.")
        return

    metadata = required_metadata(args)
    destination_dir.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.tmp")
    try:
        shutil.copy2(source, temporary)
        if destination.exists():
            raise ValueError(f"Destination appeared during copy: {destination}")
        os.replace(temporary, destination)
        row = {
            "artifact_path": destination.relative_to(project).as_posix(),
            "artifact_type": args.category,
            "source_file": str(source),
            "source_data": metadata["source_data"],
            "processing_code": metadata["processing_code"],
            "parameters": metadata["parameters"],
            "validation": metadata["validation"],
            "approved_by": metadata["approved_by"],
            "approved_date": args.approved_date or date.today().isoformat(),
            "manuscript_usage": metadata["manuscript_usage"],
            "sha256": sha256(destination),
        }
        append_manifest(manifest, row)
    except Exception:
        temporary.unlink(missing_ok=True)
        if destination.exists():
            destination.unlink()
        raise

    print(f"\n[PROMOTED] {destination}")
    print(f"[MANIFEST] {manifest}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--category", required=True, choices=sorted(CATEGORIES))
    parser.add_argument("--destination-name", help="English lowercase_snake_case filename in formal_data.")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--dry-run", action="store_true")
    action.add_argument("--approve", action="store_true", help="Explicit user-approved promotion.")
    parser.add_argument("--source-data")
    parser.add_argument("--processing-code")
    parser.add_argument("--parameters")
    parser.add_argument("--validation")
    parser.add_argument("--approved-by")
    parser.add_argument("--approved-date")
    parser.add_argument("--manuscript-usage")
    return parser.parse_args()


def main() -> int:
    try:
        promote(parse_args())
        return 0
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
