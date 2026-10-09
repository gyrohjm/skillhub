#!/usr/bin/env python3
"""Maintain a private metadata-only pseudopotential registry."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

CONTRACTS_ROOT = Path(__file__).resolve().parents[2] / "dft-contracts"
if str(CONTRACTS_ROOT) not in sys.path:
    sys.path.insert(0, str(CONTRACTS_ROOT))
from dft_contracts import sha256_file, validate_document  # noqa: E402


def load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema_version": 1, "datasets": []}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("registry must be a JSON object")
    return value


def validate(registry: dict[str, Any]) -> list[str]:
    errors = validate_document("pseudopotential-registry-v1", registry)
    ids: set[str] = set()
    for index, item in enumerate(registry.get("datasets", [])):
        dataset_id = item.get("id") if isinstance(item, dict) else None
        if dataset_id in ids:
            errors.append(f"datasets/{index}/id: duplicate id {dataset_id!r}")
        if dataset_id:
            ids.add(dataset_id)
    return errors


def write(path: Path, registry: dict[str, Any]) -> None:
    errors = validate(registry)
    if errors:
        raise ValueError("invalid pseudopotential registry: " + "; ".join(errors))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(registry, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def register_dataset(registry: dict[str, Any], record: dict[str, Any], replace: bool = False) -> None:
    datasets = registry.setdefault("datasets", [])
    matches = [index for index, item in enumerate(datasets) if item.get("id") == record["id"]]
    if matches and not replace:
        raise ValueError(f"dataset id already exists: {record['id']}; pass --replace")
    if matches:
        datasets[matches[0]] = record
    else:
        datasets.append(record)


def resolve(
    registry: dict[str, Any], *, element: str, engine: str, label: str | None = None,
    xc_functional: str | None = None,
) -> list[dict[str, Any]]:
    return [
        item for item in registry.get("datasets", [])
        if item.get("element") == element
        and engine in item.get("compatible_engines", [])
        and (label is None or item.get("label") == label)
        and (xc_functional is None or item.get("xc_functional") == xc_functional)
    ]


def verify_local_files(registry: dict[str, Any]) -> list[dict[str, Any]]:
    report: list[dict[str, Any]] = []
    for item in registry.get("datasets", []):
        local_path = item.get("local_path")
        if not local_path:
            report.append({"id": item.get("id"), "status": "metadata_only"})
            continue
        path = Path(local_path).expanduser()
        if not path.is_file():
            report.append({"id": item.get("id"), "status": "missing", "path": str(path)})
            continue
        actual = sha256_file(path)
        report.append({
            "id": item.get("id"),
            "status": "verified" if actual == item.get("sha256") else "hash_mismatch",
            "expected": item.get("sha256"),
            "actual": actual,
            "path": str(path),
        })
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pseudopotential_registry.py")
    parser.add_argument("--registry", type=Path, required=True)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init")
    sub.add_parser("validate")
    sub.add_parser("verify")
    add = sub.add_parser("register")
    add.add_argument("--id", required=True)
    add.add_argument("--file", type=Path, required=True)
    add.add_argument("--family", required=True)
    add.add_argument("--version", required=True)
    add.add_argument("--xc", required=True)
    add.add_argument("--element", required=True)
    add.add_argument("--label", required=True)
    add.add_argument("--license", required=True)
    add.add_argument("--archive-allowed", action="store_true")
    add.add_argument("--engine", action="append", required=True)
    add.add_argument("--citation")
    add.add_argument("--replace", action="store_true")
    find = sub.add_parser("resolve")
    find.add_argument("--element", required=True)
    find.add_argument("--engine", required=True)
    find.add_argument("--label")
    find.add_argument("--xc")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    registry = load(args.registry)
    if args.command == "init":
        if args.registry.exists():
            raise FileExistsError(f"refusing to overwrite: {args.registry}")
        write(args.registry, registry)
        print(f"[ok] initialized {args.registry}")
        return 0
    if args.command == "validate":
        errors = validate(registry)
        print(json.dumps({"valid": not errors, "errors": errors}, indent=2))
        return 0 if not errors else 1
    if args.command == "verify":
        report = verify_local_files(registry)
        print(json.dumps(report, indent=2))
        return 1 if any(item["status"] in {"missing", "hash_mismatch"} for item in report) else 0
    if args.command == "register":
        source = args.file.expanduser().resolve()
        if not source.is_file():
            raise FileNotFoundError(source)
        record = {
            "id": args.id,
            "family": args.family,
            "version": args.version,
            "xc_functional": args.xc,
            "element": args.element,
            "label": args.label,
            "sha256": sha256_file(source),
            "license": args.license,
            "archive_allowed": args.archive_allowed,
            "compatible_engines": sorted(set(args.engine)),
            "recommended_cutoff": None,
            "validated_cutoff": None,
            "relativistic": None,
            "valence_configuration": None,
            "citation": args.citation,
            "local_path": str(source),
        }
        register_dataset(registry, record, args.replace)
        write(args.registry, registry)
        print(json.dumps(record, indent=2, ensure_ascii=False))
        return 0
    matches = resolve(
        registry, element=args.element, engine=args.engine, label=args.label, xc_functional=args.xc
    )
    print(json.dumps(matches, indent=2, ensure_ascii=False))
    return 0 if matches else 2


if __name__ == "__main__":
    raise SystemExit(main())
