#!/usr/bin/env python3
"""Bootstrap, validate, approve, and verify computational experiment designs."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SKILL_ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = SKILL_ROOT / "assets"
DESIGN_REL = Path("docs/plans/calculation_design.json")
PLAN_REL = Path("docs/plans/computation_plan.md")
REVIEWS_REL = Path("docs/records/design_reviews")
SLUG_RE = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")
STATUSES = {"draft", "ready_for_review", "superseded"}
TASK_CLASSES = {"exploratory", "convergence", "validation", "production"}
EVIDENCE_STATUSES = {"verified", "pending"}

TOP_LEVEL_FIELDS = {
    "schema_version": int,
    "design_id": str,
    "revision": int,
    "status": str,
    "project_slug": str,
    "title": str,
    "research_questions": list,
    "hypotheses": list,
    "systems": list,
    "observables": list,
    "controls": list,
    "convergence_studies": list,
    "validation_checks": list,
    "calculation_matrix": list,
    "vasp_stage_envelopes": list,
    "evidence": list,
    "uncertainty_budget": list,
    "resource_budget": dict,
    "stop_conditions": list,
    "pending_decisions": list,
}


class DesignError(ValueError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise DesignError(f"file does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise DesignError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise DesignError(f"JSON root must be an object: {path}")
    return value


def has_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def is_placeholder(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    normalized = value.strip().upper()
    return (
        normalized in {"TBD", "TODO", "UNKNOWN", "PENDING", "待补充", "待定", "未知"}
        or normalized.startswith("TBD ")
        or normalized.startswith("待补充")
    )


def placeholder_paths(value: Any, prefix: str = "") -> list[str]:
    found: list[str] = []
    if is_placeholder(value):
        found.append(prefix or "<root>")
    elif isinstance(value, dict):
        for key, item in value.items():
            found.extend(placeholder_paths(item, f"{prefix}.{key}" if prefix else str(key)))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(placeholder_paths(item, f"{prefix}[{index}]"))
    return found


def require_fields(item: Any, fields: tuple[str, ...], path: str, errors: list[str]) -> None:
    if not isinstance(item, dict):
        errors.append(f"{path} must be an object")
        return
    for field in fields:
        if field not in item:
            errors.append(f"{path}.{field} is required")
        elif isinstance(item[field], str) and not item[field].strip():
            errors.append(f"{path}.{field} must not be empty")


def collect_ids(items: Any, path: str, errors: list[str]) -> set[str]:
    result: set[str] = set()
    if not isinstance(items, list):
        return result
    for index, item in enumerate(items):
        if not isinstance(item, dict) or not has_text(item.get("id")):
            continue
        item_id = item["id"]
        if item_id in result:
            errors.append(f"{path}[{index}].id duplicates {item_id!r}")
        result.add(item_id)
    return result


def validate_design(design: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for field, expected_type in TOP_LEVEL_FIELDS.items():
        if field not in design:
            errors.append(f"{field} is required")
        elif not isinstance(design[field], expected_type) or (
            expected_type is int and isinstance(design[field], bool)
        ):
            errors.append(f"{field} must be {expected_type.__name__}")

    if errors:
        return errors
    if design["schema_version"] != 1:
        errors.append("schema_version must be 1")
    if not SLUG_RE.fullmatch(design["design_id"]):
        errors.append("design_id must use lowercase_snake_case")
    if not SLUG_RE.fullmatch(design["project_slug"]):
        errors.append("project_slug must use lowercase_snake_case")
    if design["revision"] < 1:
        errors.append("revision must be a positive integer")
    if design["status"] not in STATUSES:
        errors.append(f"status must be one of {sorted(STATUSES)}")
    if not design["title"].strip():
        errors.append("title must not be empty")

    nonempty_lists = (
        "research_questions",
        "hypotheses",
        "systems",
        "observables",
        "controls",
        "convergence_studies",
        "validation_checks",
        "calculation_matrix",
        "vasp_stage_envelopes",
        "evidence",
        "stop_conditions",
    )
    for field in nonempty_lists:
        if not design[field]:
            errors.append(f"{field} must not be empty")

    for index, item in enumerate(design["research_questions"]):
        require_fields(item, ("id", "question"), f"research_questions[{index}]", errors)
    for index, item in enumerate(design["hypotheses"]):
        require_fields(item, ("id", "statement", "falsification"), f"hypotheses[{index}]", errors)
    for index, item in enumerate(design["systems"]):
        require_fields(
            item,
            ("system_slug", "model", "structure_provenance", "assumptions"),
            f"systems[{index}]",
            errors,
        )
        if isinstance(item, dict) and has_text(item.get("system_slug")) and not SLUG_RE.fullmatch(item["system_slug"]):
            errors.append(f"systems[{index}].system_slug must use lowercase_snake_case")
        if isinstance(item, dict) and not isinstance(item.get("assumptions"), list):
            errors.append(f"systems[{index}].assumptions must be a list")
    for index, item in enumerate(design["observables"]):
        require_fields(
            item,
            ("id", "hypothesis_ids", "quantity", "decision_rule", "uncertainty_target"),
            f"observables[{index}]",
            errors,
        )
    for index, item in enumerate(design["controls"]):
        require_fields(item, ("id", "type", "purpose", "fixed_or_varied"), f"controls[{index}]", errors)
    for index, item in enumerate(design["convergence_studies"]):
        require_fields(
            item,
            (
                "id",
                "parameter",
                "candidate_values",
                "fixed_conditions",
                "target_observable_ids",
                "acceptance_rule",
                "selected_value",
            ),
            f"convergence_studies[{index}]",
            errors,
        )
    for index, item in enumerate(design["validation_checks"]):
        require_fields(item, ("id", "type", "reference", "acceptance_rule"), f"validation_checks[{index}]", errors)

    hypothesis_ids = collect_ids(design["hypotheses"], "hypotheses", errors)
    observable_ids = collect_ids(design["observables"], "observables", errors)
    collect_ids(design["research_questions"], "research_questions", errors)
    collect_ids(design["controls"], "controls", errors)
    collect_ids(design["convergence_studies"], "convergence_studies", errors)
    collect_ids(design["validation_checks"], "validation_checks", errors)
    matrix_ids = collect_ids(design["calculation_matrix"], "calculation_matrix", errors)
    collect_ids(design["evidence"], "evidence", errors)
    system_ids = {
        item.get("system_slug") for item in design["systems"] if isinstance(item, dict) and has_text(item.get("system_slug"))
    }

    for index, item in enumerate(design["observables"]):
        if not isinstance(item, dict):
            continue
        refs = item.get("hypothesis_ids")
        if not isinstance(refs, list) or not refs:
            errors.append(f"observables[{index}].hypothesis_ids must be a non-empty list")
        elif not set(refs).issubset(hypothesis_ids):
            errors.append(f"observables[{index}].hypothesis_ids contains unknown IDs")

    for index, item in enumerate(design["calculation_matrix"]):
        require_fields(
            item,
            (
                "id",
                "class",
                "system_slug",
                "case_slug",
                "hypothesis_ids",
                "purpose",
                "variables",
                "fixed_parameters",
                "stages",
                "observable_ids",
                "completion_gate",
            ),
            f"calculation_matrix[{index}]",
            errors,
        )
        if not isinstance(item, dict):
            continue
        if item.get("class") not in TASK_CLASSES:
            errors.append(f"calculation_matrix[{index}].class must be one of {sorted(TASK_CLASSES)}")
        if item.get("system_slug") not in system_ids:
            errors.append(f"calculation_matrix[{index}].system_slug is unknown")
        if has_text(item.get("case_slug")) and not SLUG_RE.fullmatch(item["case_slug"]):
            errors.append(f"calculation_matrix[{index}].case_slug must use lowercase_snake_case")
        if not isinstance(item.get("stages"), list) or not item.get("stages"):
            errors.append(f"calculation_matrix[{index}].stages must be a non-empty list")
        if not isinstance(item.get("hypothesis_ids"), list) or not set(item.get("hypothesis_ids", [])).issubset(hypothesis_ids):
            errors.append(f"calculation_matrix[{index}].hypothesis_ids contains unknown IDs")
        if not isinstance(item.get("observable_ids"), list) or not set(item.get("observable_ids", [])).issubset(observable_ids):
            errors.append(f"calculation_matrix[{index}].observable_ids contains unknown IDs")

    envelope_ids: set[str] = set()
    for index, item in enumerate(design["vasp_stage_envelopes"]):
        require_fields(
            item,
            (
                "matrix_id",
                "structure_source",
                "incar_policy",
                "kpoints_policy",
                "potcar_labels",
                "resource_profile",
                "completion_gates",
            ),
            f"vasp_stage_envelopes[{index}]",
            errors,
        )
        if not isinstance(item, dict):
            continue
        matrix_id = item.get("matrix_id")
        if matrix_id not in matrix_ids:
            errors.append(f"vasp_stage_envelopes[{index}].matrix_id is unknown")
        elif matrix_id in envelope_ids:
            errors.append(f"vasp_stage_envelopes[{index}].matrix_id duplicates {matrix_id!r}")
        else:
            envelope_ids.add(matrix_id)
    if matrix_ids - envelope_ids:
        errors.append(f"missing VASP envelopes for matrix IDs: {sorted(matrix_ids - envelope_ids)}")

    for index, item in enumerate(design["evidence"]):
        require_fields(item, ("id", "claim", "source", "kind", "status", "supports"), f"evidence[{index}]", errors)
        if isinstance(item, dict) and item.get("status") not in EVIDENCE_STATUSES:
            errors.append(f"evidence[{index}].status must be one of {sorted(EVIDENCE_STATUSES)}")

    return errors


def matrix_by_id(design: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {item["id"]: item for item in design["calculation_matrix"] if isinstance(item, dict) and has_text(item.get("id"))}


def envelope_by_matrix(design: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        item["matrix_id"]: item
        for item in design["vasp_stage_envelopes"]
        if isinstance(item, dict) and has_text(item.get("matrix_id"))
    }


def approval_errors(design: dict[str, Any], scope: list[str]) -> list[str]:
    errors = validate_design(design)
    if errors:
        return errors
    if design["status"] != "ready_for_review":
        errors.append("design status must be ready_for_review before approval")
    if design["pending_decisions"]:
        errors.append("pending_decisions must be empty before approval")
    matrices = matrix_by_id(design)
    envelopes = envelope_by_matrix(design)
    for matrix_id in scope:
        if matrix_id not in matrices:
            errors.append(f"approval scope contains unknown matrix ID: {matrix_id}")
            continue
        for path in placeholder_paths(matrices[matrix_id], f"calculation_matrix.{matrix_id}"):
            errors.append(f"approval scope contains placeholder: {path}")
        envelope = envelopes.get(matrix_id)
        if envelope:
            for path in placeholder_paths(envelope, f"vasp_stage_envelopes.{matrix_id}"):
                errors.append(f"approval scope contains placeholder: {path}")
        if matrices[matrix_id].get("class") == "production":
            pending = [item.get("id", "unknown") for item in design["evidence"] if item.get("status") != "verified"]
            if pending:
                errors.append(f"production scope requires verified evidence; pending: {pending}")
            unresolved = [
                item.get("id", "unknown")
                for item in design["convergence_studies"]
                if item.get("selected_value") is None or is_placeholder(item.get("selected_value"))
            ]
            if unresolved:
                errors.append(f"production scope requires selected convergence values; unresolved: {unresolved}")
            for index, item in enumerate(design["validation_checks"]):
                for path in placeholder_paths(item, f"validation_checks[{index}]"):
                    errors.append(f"production scope contains placeholder: {path}")
    return errors


def normalize_scope(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        for item in value.split(","):
            item = item.strip()
            if item and item not in result:
                result.append(item)
    if not result:
        raise DesignError("at least one --scope matrix ID is required")
    return result


def project_slug(project: Path, explicit: str | None) -> str:
    if explicit:
        if not SLUG_RE.fullmatch(explicit):
            raise DesignError("--project-slug must use lowercase_snake_case")
        return explicit
    spec_path = project / "docs/project_spec.json"
    if spec_path.exists():
        spec = load_json(spec_path)
        value = spec.get("project_slug")
        if has_text(value) and SLUG_RE.fullmatch(value):
            return value
    if SLUG_RE.fullmatch(project.name):
        return project.name
    raise DesignError("cannot infer project_slug; pass --project-slug")


def cmd_bootstrap(args: argparse.Namespace) -> int:
    project = args.project.expanduser().resolve()
    if not project.is_dir():
        raise DesignError(f"project directory does not exist: {project}")
    slug = project_slug(project, args.project_slug)
    directories = [project / "docs/plans", project / REVIEWS_REL]
    files = [
        (project / DESIGN_REL, ASSET_DIR / "calculation_design.template.json"),
        (project / PLAN_REL, ASSET_DIR / "computation_plan.template.md"),
    ]
    for directory in directories:
        state = "exists" if directory.exists() else "create"
        print(f"[{state}] directory {directory}")
    for destination, _ in files:
        state = "keep" if destination.exists() else "create"
        print(f"[{state}] file {destination}")
    if args.dry_run:
        return 0
    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)
    for destination, source in files:
        if destination.exists():
            continue
        if destination == project / DESIGN_REL:
            design = load_json(source)
            design["project_slug"] = slug
            design["design_id"] = f"{slug}_computation"
            design["title"] = f"{slug} 计算实验设计"
            destination.write_text(json.dumps(design, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        else:
            shutil.copyfile(source, destination)
    return 0


def print_errors(errors: list[str]) -> None:
    for error in errors:
        print(f"[error] {error}", file=sys.stderr)


def cmd_validate(args: argparse.Namespace) -> int:
    design = load_json(args.design.expanduser().resolve())
    errors = validate_design(design)
    if errors:
        print_errors(errors)
        return 1
    print(f"[ok] valid calculation design: {args.design}")
    return 0


def cmd_approve(args: argparse.Namespace) -> int:
    project = args.project.expanduser().resolve()
    design_path = project / DESIGN_REL
    plan_path = project / PLAN_REL
    design = load_json(design_path)
    if not has_text(args.reviewer):
        raise DesignError("--reviewer must not be empty")
    scope = normalize_scope(args.scope)
    errors = approval_errors(design, scope)
    if errors:
        print_errors(errors)
        return 1
    if not plan_path.is_file() or not plan_path.read_text(encoding="utf-8").strip():
        raise DesignError(f"computation plan is missing or empty: {plan_path}")
    review_dir = project / REVIEWS_REL / design["design_id"] / f"r{design['revision']:04d}"
    if review_dir.exists():
        raise DesignError(f"review bundle already exists and cannot be overwritten: {review_dir}")
    review_dir.mkdir(parents=True)
    design_snapshot = review_dir / "calculation_design.json"
    plan_snapshot = review_dir / "computation_plan.md"
    shutil.copyfile(design_path, design_snapshot)
    shutil.copyfile(plan_path, plan_snapshot)
    approval = {
        "schema_version": 1,
        "approval_type": "scientific_design",
        "status": "approved",
        "design_id": design["design_id"],
        "revision": design["revision"],
        "scope": scope,
        "reviewer": args.reviewer,
        "approved_at": utc_now(),
        "design_file": design_snapshot.name,
        "design_sha256": sha256_file(design_snapshot),
        "computation_plan_file": plan_snapshot.name,
        "computation_plan_sha256": sha256_file(plan_snapshot),
    }
    approval_path = review_dir / "approval.json"
    approval_path.write_text(json.dumps(approval, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"[ok] approved scientific design scope {scope}: {approval_path}")
    return 0


def verify_approval(approval_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    approval_path = approval_path.expanduser().resolve()
    approval = load_json(approval_path)
    required = {
        "schema_version",
        "approval_type",
        "status",
        "design_id",
        "revision",
        "scope",
        "reviewer",
        "approved_at",
        "design_file",
        "design_sha256",
        "computation_plan_file",
        "computation_plan_sha256",
    }
    missing = sorted(required - set(approval))
    if missing:
        raise DesignError(f"approval is missing fields: {missing}")
    if approval["schema_version"] != 1 or approval["approval_type"] != "scientific_design" or approval["status"] != "approved":
        raise DesignError("approval header is invalid")
    design_name = Path(str(approval["design_file"]))
    plan_name = Path(str(approval["computation_plan_file"]))
    if design_name.name != str(design_name) or plan_name.name != str(plan_name):
        raise DesignError("approval snapshot file names must not contain directories")
    design_path = approval_path.parent / design_name
    plan_path = approval_path.parent / plan_name
    if sha256_file(design_path) != approval["design_sha256"]:
        raise DesignError("calculation design hash does not match approval")
    if sha256_file(plan_path) != approval["computation_plan_sha256"]:
        raise DesignError("computation plan hash does not match approval")
    design = load_json(design_path)
    errors = validate_design(design)
    if errors:
        raise DesignError("approved design is invalid: " + "; ".join(errors))
    if design["design_id"] != approval["design_id"] or design["revision"] != approval["revision"]:
        raise DesignError("approval design ID or revision does not match snapshot")
    scope = approval["scope"]
    if not isinstance(scope, list) or not scope:
        raise DesignError("approval scope must be a non-empty list")
    unknown = sorted(set(scope) - set(matrix_by_id(design)))
    if unknown:
        raise DesignError(f"approval scope contains unknown matrix IDs: {unknown}")
    semantic_errors = approval_errors(design, list(scope))
    if semantic_errors:
        raise DesignError("approved design no longer satisfies approval rules: " + "; ".join(semantic_errors))
    return approval, design


def cmd_verify(args: argparse.Namespace) -> int:
    approval, _ = verify_approval(args.approval)
    print(
        f"[ok] verified scientific design approval: {approval['design_id']} "
        f"revision {approval['revision']} scope {approval['scope']}"
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="computation_design.py")
    sub = parser.add_subparsers(dest="command", required=True)

    bootstrap = sub.add_parser("bootstrap", help="Create missing design files without overwriting existing work.")
    bootstrap.add_argument("--project", type=Path, required=True)
    bootstrap.add_argument("--project-slug")
    mode = bootstrap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    bootstrap.set_defaults(func=cmd_bootstrap)

    validate = sub.add_parser("validate", help="Validate a calculation_design.json contract.")
    validate.add_argument("--design", type=Path, required=True)
    validate.set_defaults(func=cmd_validate)

    approve = sub.add_parser("approve", help="Create an immutable scientific design review bundle.")
    approve.add_argument("--project", type=Path, required=True)
    approve.add_argument("--reviewer", required=True)
    approve.add_argument("--scope", action="append", required=True, help="Approved matrix ID; repeat or comma-separate.")
    approve.set_defaults(func=cmd_approve)

    verify = sub.add_parser("verify", help="Verify a scientific design approval and both snapshot hashes.")
    verify.add_argument("--approval", type=Path, required=True)
    verify.set_defaults(func=cmd_verify)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        return args.func(args)
    except (DesignError, OSError) as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
