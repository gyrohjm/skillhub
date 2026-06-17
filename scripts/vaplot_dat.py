#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


HEADER_RE = re.compile(r"^#\s*([A-Za-z0-9_./:-]+)\s*=\s*(.*?)\s*$")
COLUMN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def parse_dat(path: Path) -> tuple[dict[str, str], list[list[float]], list[str]]:
    meta: dict[str, str] = {}
    rows: list[list[float]] = []
    errors: list[str] = []
    columns: list[str] = []

    for lineno, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            match = HEADER_RE.match(stripped)
            if match:
                meta[match.group(1)] = match.group(2)
                if match.group(1) == "columns":
                    columns = match.group(2).split()
            continue

        parts = stripped.split()
        try:
            row = [float(x.replace("D", "E").replace("d", "e")) for x in parts]
        except ValueError:
            errors.append(f"line {lineno}: non-numeric data row")
            continue
        if columns and len(row) != len(columns):
            errors.append(f"line {lineno}: expected {len(columns)} columns, got {len(row)}")
        rows.append(row)

    if meta.get("vaplot_dat_version") != "1":
        errors.append("missing or unsupported '# vaplot_dat_version = 1'")
    if "source" not in meta:
        errors.append("missing '# source = ...'")
    if "units" not in meta:
        errors.append("missing '# units = ...'")
    if not columns:
        errors.append("missing '# columns = ...'")
    else:
        bad = [name for name in columns if not COLUMN_RE.match(name)]
        if bad:
            errors.append("invalid column names: " + ", ".join(bad))
    if not rows:
        errors.append("no numeric data rows")

    return meta, rows, errors


def validate(args: argparse.Namespace) -> int:
    path = args.path
    meta, rows, errors = parse_dat(path)
    result: dict[str, Any] = {
        "path": str(path),
        "ok": not errors,
        "rows": len(rows),
        "columns": meta.get("columns", "").split(),
        "errors": errors,
    }
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    elif errors:
        for error in errors:
            print(f"[error] {error}", file=sys.stderr)
    else:
        print(f"[ok] {path}: rows={len(rows)} columns={len(result['columns'])}")
    return 0 if not errors else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate vaplot .dat files.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_validate = sub.add_parser("validate")
    p_validate.add_argument("path", type=Path)
    p_validate.add_argument("--json", action="store_true")
    p_validate.set_defaults(func=validate)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
