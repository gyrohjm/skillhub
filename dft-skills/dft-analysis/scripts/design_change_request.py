#!/usr/bin/env python3
"""Create a provenance-linked request for a new dft-design revision."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CONTRACTS_ROOT = Path(__file__).resolve().parents[2] / "dft-contracts"
if str(CONTRACTS_ROOT) not in sys.path:
    sys.path.insert(0, str(CONTRACTS_ROOT))
from dft_contracts import ensure_within, validate_document


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def analysis_root(case_root: Path) -> Path:
    canonical = case_root / "analysis"
    legacy_roots = (case_root / "9analysis", case_root / "6analysis")
    for candidate in (canonical, *legacy_roots):
        if candidate.is_dir() and any(
            item.is_file() or item.is_symlink() for item in candidate.rglob("*")
        ):
            return candidate
    if canonical.exists():
        return canonical
    for candidate in legacy_roots:
        if candidate.exists():
            return candidate
    return canonical


def structure_reference(structure_root: Path, path: Path) -> str:
    resolved = ensure_within(structure_root, path)
    return f"structure_root:{resolved.relative_to(structure_root).as_posix()}"


def parse_parameter_change(value: str) -> dict[str, str]:
    if "=" not in value:
        raise ValueError("parameter change must use NAME=PROPOSED_VALUE")
    name, proposed = value.split("=", 1)
    name = name.strip()
    proposed = proposed.strip()
    if not name or not proposed:
        raise ValueError("parameter change must include both name and proposed value")
    return {"name": name, "proposed": proposed}


def _is_workflow_v2(record: dict[str, Any]) -> bool:
    return record.get("contract") == "dft.workflow.v2" or record.get("schema_version") == 2


def _approved_design(provenance: Any, *, workflow_v2: bool) -> bool:
    if not isinstance(provenance, dict):
        return False
    if workflow_v2:
        return bool(provenance.get("approval_ref") or provenance.get("scientific_design_approved"))
    return bool(provenance.get("scientific_design_approved"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="design_change_request.py")
    parser.add_argument("--case-root", type=Path, required=True)
    parser.add_argument("--workflow", type=Path, default=None)
    parser.add_argument("--task-spec", type=Path, default=None)
    parser.add_argument("--trigger", required=True)
    parser.add_argument("--proposed-change", required=True)
    parser.add_argument("--scientific-reason", required=True)
    parser.add_argument("--evidence", action="append", default=[])
    parser.add_argument(
        "--failure-class",
        choices=(
            "input_preparation",
            "scheduler_resource",
            "runtime_environment",
            "numerical_convergence",
            "postprocess",
            "unknown",
        ),
    )
    parser.add_argument("--diagnostic-summary")
    parser.add_argument("--parameter-change", action="append", default=[])
    parser.add_argument("--acceptance-rule")
    parser.add_argument("--verdict", choices=("supported", "falsified", "inconclusive"), required=True)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)

    case_root = args.case_root.expanduser().resolve()
    if args.workflow is not None and args.task_spec is not None:
        print("[error] pass either --workflow or --task-spec, not both", file=sys.stderr)
        return 1

    if args.workflow is not None:
        record_path = args.workflow.expanduser().resolve()
        record_kind = "workflow"
    else:
        record_path = (args.task_spec or (case_root / "task_spec.json")).expanduser().resolve()
        record_kind = "task_spec"
    if not record_path.is_file():
        hint = "pass --workflow <task-leaf>/workflow.json" if record_kind == "task_spec" else ""
        print(f"[error] {record_path.name} does not exist: {record_path}; {hint}", file=sys.stderr)
        return 1
    try:
        structure_reference(case_root, record_path)
    except ValueError as exc:
        print(f"[error] source record must stay under the structure root: {exc}", file=sys.stderr)
        return 1

    task_record = load_json(record_path)
    if record_kind == "workflow":
        workflow_v2 = _is_workflow_v2(task_record)
        workflow_errors = validate_document(
            "workflow-v2" if workflow_v2 else "workflow-v1",
            task_record,
        )
        if workflow_errors:
            print(
                "[error] workflow.json violates shared contract: " + "; ".join(workflow_errors),
                file=sys.stderr,
            )
            return 1
        provenance = task_record.get("design")
    else:
        workflow_v2 = False
        provenance = task_record.get("design_provenance")
    if not _approved_design(provenance, workflow_v2=workflow_v2):
        print("[error] task has no approved scientific design provenance", file=sys.stderr)
        return 1

    evidence_paths: list[str] = []
    try:
        for path in args.evidence:
            evidence_paths.append(
                structure_reference(case_root, Path(path).expanduser().resolve())
            )
    except ValueError as exc:
        print(f"[error] evidence path must stay under the structure root: {exc}", file=sys.stderr)
        return 1

    output = args.output or (analysis_root(case_root) / "reports/design_change_request.json")
    output = output.expanduser().resolve()
    if output.exists():
        print(f"[error] refusing to overwrite existing change request: {output}", file=sys.stderr)
        return 1
    try:
        parameter_changes = [parse_parameter_change(value) for value in args.parameter_change]
    except ValueError as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 1

    source_design = {
        "design_id": provenance.get("design_id"),
        "revision": provenance.get("revision", provenance.get("design_revision")),
        "matrix_id": provenance.get("matrix_id"),
        "design_sha256": provenance.get("design_sha256"),
        "approval_sha256": provenance.get("approval_sha256"),
    }
    if workflow_v2:
        source_design.update(
            {
                "approval_ref": provenance.get("approval_ref"),
                "baseline_parameter_hash": provenance.get("baseline_parameter_hash"),
            }
        )
    lineage = task_record.get("lineage") if isinstance(task_record.get("lineage"), dict) else {}
    source_workflow = structure_reference(case_root, record_path)
    derived_from = lineage.get("derived_from") or source_workflow
    recovery_mode = "create_rerun_branch" if parameter_changes or args.verdict == "falsified" else "none"
    request = {
        "schema_version": 1,
        "status": "proposed",
        "created_at": utc_now(),
        "source_design": source_design,
        f"source_{record_kind}": source_workflow,
        "source_workflow_contract": task_record.get("contract") if record_kind == "workflow" else None,
        "source_workflow_schema_version": task_record.get("schema_version") if record_kind == "workflow" else None,
        "engine": task_record.get("engine") or provenance.get("engine") or "unknown",
        "backend": task_record.get("backend") or "unknown",
        "verdict": args.verdict,
        "trigger": args.trigger,
        "proposed_change": args.proposed_change,
        "scientific_reason": args.scientific_reason,
        "evidence_paths": evidence_paths,
        "requested_action": "create_and_review_a_new_computation_design_revision",
        "handoff": ["dft-design", "dft-workflow"],
        "submission_authorized": False,
        "submission_review_required": False,
        "requires_submission_review": False,
        "recovery_mode": recovery_mode,
        "derived_from": derived_from,
        "lineage": {
            "derived_from": derived_from,
            "supersedes": lineage.get("supersedes"),
        },
    }
    if args.failure_class or args.diagnostic_summary:
        if not args.failure_class or not args.diagnostic_summary:
            print(
                "[error] --failure-class and --diagnostic-summary must be provided together",
                file=sys.stderr,
            )
            return 1
    if (args.failure_class or args.parameter_change) and not args.acceptance_rule:
        print(
            "[error] --acceptance-rule is required for a failure or parameter change",
            file=sys.stderr,
        )
        return 1
    if args.acceptance_rule:
        request["acceptance_rule"] = args.acceptance_rule
    if args.failure_class or args.diagnostic_summary:
        request["failure"] = {
            "class": args.failure_class,
            "diagnostic_summary": args.diagnostic_summary,
        }
    if parameter_changes:
        request["parameter_changes"] = parameter_changes
    contract_errors = validate_document("design-change-request-v1", request)
    if contract_errors:
        print(
            "[error] change request violates shared contract: " + "; ".join(contract_errors),
            file=sys.stderr,
        )
        return 1
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(request, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"[ok] wrote design change request: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
