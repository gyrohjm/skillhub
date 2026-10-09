#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
from pathlib import Path
from typing import Any


def task_spec_v1_to_v2(document: dict[str, Any]) -> dict[str, Any]:
    migrated = dict(document)
    migrated["schema_version"] = 2
    migrated["contract"] = "dft.task-spec.v2"
    if "POTCAR_components" in migrated and "pseudopotential_components" not in migrated:
        migrated["pseudopotential_components"] = migrated["POTCAR_components"]
    if "input_hashes" not in migrated and isinstance(migrated.get("input_sha256"), dict):
        migrated["input_hashes"] = migrated["input_sha256"]
    migrated.setdefault(
        "task_kind",
        migrated.get("stage") or migrated.get("task_class") or migrated.get("kind") or "unknown",
    )
    migrated.setdefault(
        "task_dir",
        migrated.get("taskset") or migrated.get("case_root") or ".",
    )
    migrated.setdefault("parent_fingerprints", [])
    return migrated


def archive_v2_to_v3(document: dict[str, Any]) -> dict[str, Any]:
    migrated = dict(document)
    migrated["schema"] = "dft-work-manager.archive.v3"
    migrated.setdefault("calculation_fingerprint", {"exact": "unknown", "scientific": "unknown"})
    return migrated


def _canonical_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-fA-F]{64}", value) is not None


_SUBMISSION_STATE_ALIASES = {
    "not_approved": "not_submitted",
    "not_requested": "not_submitted",
    "not_submitted": "not_submitted",
    "not_submitted_yet": "not_submitted",
    "pending": "not_submitted",
    "pending_approval": "not_submitted",
    "awaiting_approval": "not_submitted",
    "awaiting_user_decision": "not_submitted",
    "approved": "not_submitted",
    "queued": "submitted",
    "submitted": "submitted",
    "accepted": "submitted",
    "running": "running",
    "started": "running",
    "completed": "completed",
    "complete": "completed",
    "done": "completed",
    "finished": "completed",
    "succeeded": "completed",
    "success": "completed",
    "failed": "failed",
    "failure": "failed",
    "error": "failed",
    "rejected": "rejected",
    "cancelled": "cancelled",
    "canceled": "cancelled",
    "unknown": "unknown",
}


def _legacy_submission_state(submission: dict[str, Any]) -> str:
    state = submission.get("state")
    if not isinstance(state, str) or not state.strip():
        return "not_submitted"
    normalized = state.strip().lower().replace("-", "_").replace(" ", "_")
    return _SUBMISSION_STATE_ALIASES.get(normalized, "unknown")


def workflow_v1_to_v2(document: dict[str, Any]) -> dict[str, Any]:
    """Migrate a legacy workflow leaf without modifying its source document."""

    migrated = copy.deepcopy(document)
    migrated["schema_version"] = 2
    migrated["contract"] = "dft.workflow.v2"

    old_inputs = migrated.get("inputs", [])
    if isinstance(old_inputs, list):
        migrated["inputs"] = {
            "materialization": "static",
            "files": old_inputs,
        }
    elif isinstance(old_inputs, dict):
        inputs = old_inputs
        inputs.setdefault("materialization", "static")
        inputs.setdefault("files", [])
        migrated["inputs"] = inputs
    else:
        migrated["inputs"] = {
            "materialization": "static",
            "files": [],
            "legacy_value": old_inputs,
        }

    migrated.setdefault("dependencies", [])
    migrated.setdefault("input_authority", {})
    migrated.setdefault("attempts", [])
    migrated.setdefault(
        "parameter_reconciliation",
        {
            "status": "synchronized",
            "changed_parameters": [],
            "affected_tasks": [],
        },
    )
    migrated.setdefault(
        "resource_profile",
        {"ref": "workspace_root:.dft/resource-profile.json", "overrides": {}},
    )

    design = migrated.get("design")
    if not isinstance(design, dict):
        design = {}
    design.setdefault(
        "design_id",
        migrated.get("composition_slug") or migrated.get("task_slug") or "legacy-workflow",
    )
    design.setdefault("revision", 1)
    design.setdefault("approval_ref", "legacy:workflow-v1")
    baseline_hash = design.get("baseline_parameter_hash")
    if not _is_sha256(baseline_hash):
        approval_hash = design.get("approval_sha256")
        if _is_sha256(approval_hash):
            baseline_hash = approval_hash
        else:
            baseline_hash = _canonical_hash({"design": design, "inputs": migrated["inputs"]})
        design["baseline_parameter_hash"] = baseline_hash
    migrated["design"] = design

    submission = migrated.get("submission")
    if not isinstance(submission, dict):
        submission = {}
    legacy_state = submission.get("state")
    submission["state"] = _legacy_submission_state(submission)
    if legacy_state != submission["state"] and "legacy_state" not in submission:
        submission["legacy_state"] = legacy_state
    submission.setdefault("allowed", submission["state"] in {"submitted", "running", "completed"})
    submission.setdefault("job_id", None)
    migrated["submission"] = submission

    old_completion = migrated.get("completion")
    if not isinstance(old_completion, dict):
        old_completion = {}
    scheduler_complete = old_completion.get("scheduler_complete")
    if not isinstance(scheduler_complete, bool):
        scheduler_complete = submission["state"].lower() in {
            "completed",
            "complete",
            "finished",
            "succeeded",
        }
    artifact_complete = old_completion.get("artifact_complete")
    if not isinstance(artifact_complete, bool):
        artifact_complete = False
    completion = copy.deepcopy(old_completion)
    completion.update(
        {
            "scheduler_complete": scheduler_complete,
            "artifact_complete": artifact_complete,
            "scientifically_accepted": False,
        }
    )
    migrated["completion"] = completion

    migrated.setdefault("lineage", {"derived_from": None, "supersedes": None})
    migrated.setdefault("history", [])
    migrated.setdefault("status", "prepared")
    migrated.setdefault("updated_at", "1970-01-01T00:00:00+00:00")
    return migrated


MIGRATIONS = {
    "task-spec-v1-to-v2": task_spec_v1_to_v2,
    "archive-v2-to-v3": archive_v2_to_v3,
    "workflow-v1-to-v2": workflow_v1_to_v2,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="dft-contract-migrate")
    parser.add_argument("migration", choices=sorted(MIGRATIONS))
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args(argv)
    document = json.loads(args.source.read_text(encoding="utf-8"))
    migrated = MIGRATIONS[args.migration](document)
    if args.destination.exists():
        raise FileExistsError(f"refusing to overwrite: {args.destination}")
    args.destination.parent.mkdir(parents=True, exist_ok=True)
    args.destination.write_text(json.dumps(migrated, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"[ok] wrote {args.destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
