#!/usr/bin/env python3
"""Create a provenance-linked request for a new computation-design revision."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="design_change_request.py")
    parser.add_argument("--case-root", type=Path, required=True)
    parser.add_argument("--task-spec", type=Path, default=None)
    parser.add_argument("--trigger", required=True)
    parser.add_argument("--proposed-change", required=True)
    parser.add_argument("--scientific-reason", required=True)
    parser.add_argument("--evidence", action="append", default=[])
    parser.add_argument("--verdict", choices=("supported", "falsified", "inconclusive"), required=True)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)

    case_root = args.case_root.expanduser().resolve()
    task_spec_path = (args.task_spec or (case_root / "task_spec.json")).expanduser().resolve()
    if not task_spec_path.is_file():
        print(f"[error] task_spec.json does not exist: {task_spec_path}", file=sys.stderr)
        return 1
    task_spec = load_json(task_spec_path)
    provenance = task_spec.get("design_provenance")
    if not isinstance(provenance, dict) or not provenance.get("scientific_design_approved"):
        print("[error] task has no approved scientific design provenance", file=sys.stderr)
        return 1

    output = args.output or (case_root / "analysis/reports/design_change_request.json")
    output = output.expanduser().resolve()
    if output.exists():
        print(f"[error] refusing to overwrite existing change request: {output}", file=sys.stderr)
        return 1
    request = {
        "schema_version": 1,
        "status": "proposed",
        "created_at": utc_now(),
        "source_design": {
            "design_id": provenance.get("design_id"),
            "revision": provenance.get("design_revision"),
            "matrix_id": provenance.get("matrix_id"),
            "design_sha256": provenance.get("design_sha256"),
            "approval_sha256": provenance.get("approval_sha256"),
        },
        "source_task_spec": str(task_spec_path),
        "verdict": args.verdict,
        "trigger": args.trigger,
        "proposed_change": args.proposed_change,
        "scientific_reason": args.scientific_reason,
        "evidence_paths": [str(Path(path).expanduser().resolve()) for path in args.evidence],
        "requested_action": "create_and_review_a_new_computation_design_revision",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(request, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"[ok] wrote design change request: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
