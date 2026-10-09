#!/usr/bin/env python3
"""Deterministic dependency gates and non-destructive workflow recovery.

This module deliberately keeps the runtime policy small and file based.  The
canonical leaf is the only live ledger; dependency decisions are read-only,
Agent decisions update that ledger atomically, and recovery helpers stage new
directories before making them visible.
"""

from __future__ import annotations

from uuid import uuid4
import copy
import hashlib
import json
import os
import re
import shutil
import tempfile
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from job_paths import resolve_job_script
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "dft-contracts"))
from dft_contracts.layout import discover_workspace, route_for, workflow_paths, PROJECT_FILE


class WorkflowControlError(ValueError):
    """Raised when a workflow control operation cannot be made safely."""


# A compatibility name makes the control seam convenient for callers that use
# the canonical workflow's existing ``WorkflowError`` vocabulary.
WorkflowError = WorkflowControlError

AGENT_VERDICTS = frozenset(
    {
        "ADVANCE",
        "RETRY_IN_PLACE",
        "CREATE_RERUN",
        "REQUEST_PARAMETER_REVISION",
        "MAJOR_CONFLICT",
    }
)

_ATTEMPT_RE = re.compile(r"^attempt-(\d+)$")
_RERUN_RE = re.compile(r"^rerun_(\d+)$")
_SLURM_LOG_RE = re.compile(r"^slurm(?:[-_.].*)?\.(?:out|err)$", re.IGNORECASE)

_TECHNICAL_TOKENS = frozenset(
    {
        "ACTIVATION_FAILURE",
        "COMMAND_NOT_FOUND",
        "ENVIRONMENT_FAILURE",
        "EXECUTABLE_FAILURE",
        "FILE_NOT_FOUND",
        "IO_ERROR",
        "LAUNCH_FAILURE",
        "MPI_FAILURE",
        "MPI_INIT_FAILURE",
        "MPI_STARTUP_FAILURE",
        "MODULE_FAILURE",
        "MODULE_NOT_FOUND",
        "NODE_FAIL",
        "NODE_FAILURE",
        "OOM",
        "OUT_OF_MEMORY",
        "PARTITION_MISSING",
        "PERMISSION_DENIED",
        "PERMISSION_FAILURE",
        "PREEMPTED",
        "SCHEDULER_FAILURE",
        "SCHEDULER_REJECTED",
        "TEMPORARY_IO",
        "TIME_LIMIT",
        "TIMEOUT",
        "WALLTIME",
        "ZBRENT_FAILED",
    }
)
_TECHNICAL_CATEGORIES = frozenset(
    {"ENVIRONMENT", "ENVIRONMENT_FAILURE", "SCHEDULER", "SCHEDULER_FAILURE", "TECHNICAL"}
)

_VASP_INPUTS = frozenset({"INCAR", "KPOINTS", "POSCAR", "POTCAR"})
_OUTPUT_NAMES = frozenset(
    {
        "CHGCAR",
        "CONTCAR",
        "DOSCAR",
        "EIGENVAL",
        "ELFCAR",
        "IBZKPT",
        "OSZICAR",
        "OUTCAR",
        "PROCAR",
        "REPORT",
        "WAVECAR",
        "vasprun.xml",
    }
)
_OUTPUT_NAME_CASEFOLD = frozenset(name.casefold() for name in _OUTPUT_NAMES)


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _atomic_write_bytes(path: Path, content: bytes) -> None:
    """Replace one file atomically, leaving the old file until replace time."""

    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _atomic_write_json(path: Path, value: Any) -> None:
    _atomic_write_bytes(path, _json_bytes(value))


def _reject_symlink(path: Path, label: str) -> None:
    if path.is_symlink():
        raise WorkflowControlError(f"unsafe {label}: symlink is not allowed: {path}")


def _safe_task_root(task_root: str | Path) -> Path:
    raw = Path(task_root).expanduser()
    if not raw.exists():
        raise WorkflowControlError(f"task root does not exist: {raw}")
    _reject_symlink(raw, "task root")
    if not raw.is_dir():
        raise WorkflowControlError(f"task root is not a directory: {raw}")
    return raw.resolve()


def _relative_parts(value: str | Path, label: str) -> tuple[str, ...]:
    raw = str(value)
    candidate = Path(raw)
    if (
        candidate.is_absolute()
        or raw.startswith(("/", "\\"))
        or re.match(r"^[A-Za-z]:", raw)
    ):
        raise WorkflowControlError(f"unsafe {label}: absolute path is not allowed: {raw!r}")
    parts = candidate.parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise WorkflowControlError(f"unsafe {label}: path must not contain . or ..: {raw!r}")
    if any("\x00" in part for part in parts):
        raise WorkflowControlError(f"unsafe {label}: NUL byte in path")
    return tuple(parts)


def _safe_child(root: Path, relative: str | Path, label: str) -> Path:
    root = root.resolve()
    parts = _relative_parts(relative, label)
    candidate = root.joinpath(*parts)
    # Reject symlinks at every existing component, even when the link happens
    # to point back inside the root.  This closes the replacement/race seam for
    # the files that these helpers are about to copy or replace.
    current = root
    for part in parts:
        current = current / part
        if current.is_symlink():
            raise WorkflowControlError(f"unsafe {label}: symlink component: {current}")
    resolved = candidate.resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise WorkflowControlError(f"unsafe {label}: path escapes task root: {relative!r}") from exc
    return resolved


def _require_regular_file(path: Path, label: str) -> Path:
    _reject_symlink(path, label)
    if not path.is_file():
        raise WorkflowControlError(f"{label} is not a regular file: {path}")
    return path


def _resolve_job_script(
    task_root: Path, workflow: Mapping[str, Any], *, required: bool
) -> Path:
    try:
        return resolve_job_script(task_root, workflow, required=required)
    except ValueError as exc:
        raise WorkflowControlError(str(exc)) from exc


def _load_workflow(task_root: str | Path) -> tuple[Path, Path, dict[str, Any], bytes]:
    root = _safe_task_root(task_root)
    workflow_path = _safe_child(root, "workflow.json", "workflow record")
    _require_regular_file(workflow_path, "workflow record")
    raw = workflow_path.read_bytes()
    try:
        workflow = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WorkflowControlError(f"workflow.json is not valid UTF-8 JSON: {exc}") from exc
    if not isinstance(workflow, dict):
        raise WorkflowControlError("workflow.json must contain an object")
    return root, workflow_path, workflow, raw


def _result(verdict: str, reasons: Sequence[str], evidence: Sequence[Mapping[str, str]]) -> dict[str, Any]:
    return {
        "verdict": verdict,
        "reasons": [str(reason) for reason in reasons],
        "evidence": [dict(item) for item in evidence],
    }


def _normal_key(value: Any) -> str:
    return str(value).strip().upper().replace("-", "_").replace(" ", "_")


def _iter_failure_values(value: Any, key: str = "") -> list[tuple[str, Any]]:
    """Collect explicit failure metadata without treating arbitrary notes as errors."""

    values: list[tuple[str, Any]] = []
    if isinstance(value, Mapping):
        for name, child in value.items():
            child_key = str(name).casefold()
            if child_key in {
                "category",
                "code",
                "error_type",
                "failure_type",
                "kind",
                "status",
                "type",
            }:
                values.append((child_key, child))
            if child_key in {"failure", "error", "technical_failure", "scheduler", "environment"}:
                values.extend(_iter_failure_values(child, child_key))
    elif isinstance(value, (list, tuple)):
        for child in value:
            values.extend(_iter_failure_values(child, key))
    elif isinstance(value, (str, int, float, bool)):
        values.append((key, value))
    return values


def _technical_failure(workflow: Mapping[str, Any]) -> str | None:
    candidates: list[tuple[str, Any]] = []
    for field in ("failure", "error", "technical_failure"):
        if field in workflow:
            value = workflow[field]
            if field == "technical_failure" and value is True:
                return "technical_failure"
            candidates.extend(_iter_failure_values(value, field))
    for field in ("category", "code", "error_type", "failure_type", "kind", "type"):
        if field in workflow:
            candidates.extend(_iter_failure_values({field: workflow[field]}, "workflow"))
    submission = workflow.get("submission")
    if isinstance(submission, Mapping):
        for field in ("failure", "error", "error_type", "failure_type"):
            if field in submission:
                candidates.extend(_iter_failure_values({field: submission[field]}, "submission"))
    result = workflow.get("result")
    if isinstance(result, Mapping):
        for field in ("failure", "error", "error_type", "failure_type"):
            if field in result:
                candidates.extend(_iter_failure_values({field: result[field]}, "result"))

    category_seen = False
    for key, value in candidates:
        normalized = _normal_key(value)
        if normalized in _TECHNICAL_CATEGORIES:
            category_seen = True
        if normalized in _TECHNICAL_TOKENS:
            return str(value)
    if category_seen:
        return "technical scheduler/environment failure"
    return None


def _has_major_conflict(workflow: Mapping[str, Any]) -> bool:
    if str(workflow.get("status", "")).casefold() == "awaiting_user_decision":
        return True
    reconciliation = workflow.get("parameter_reconciliation")
    if isinstance(reconciliation, Mapping):
        status = str(reconciliation.get("status", "")).casefold()
        verdict = _normal_key(reconciliation.get("verdict", ""))
        if status in {"major_conflict", "major-conflict"} or verdict == "MAJOR_CONFLICT":
            return True
        changes = reconciliation.get("changed_parameters")
        if status == "needs_agent" and isinstance(changes, list):
            return any(
                isinstance(change, Mapping) and _normal_key(change.get("impact", "")) == "L3"
                for change in changes
            )
    return False


def _workspace_root_for(task_root: Path) -> Path | None:
    try:
        return discover_workspace(task_root)
    except ValueError:
        if any((p / PROJECT_FILE).exists() for p in (task_root, *task_root.parents)):
            raise
    for parent in (task_root, *task_root.parents):
        if parent.name.casefold() == "calculations":
            return parent.parent
    return None


def _resolve_dependency(task_root: Path, dependency: Mapping[str, Any]) -> tuple[Path | None, str]:
    raw_ref = dependency.get("task_ref", dependency.get("task_id", dependency.get("path")))
    if not isinstance(raw_ref, str) or not raw_ref.strip():
        raise WorkflowControlError("dependency task_ref must be a non-empty string")
    reference = raw_ref.strip()
    workspace = _workspace_root_for(task_root)
    route = route_for(task_root) if workspace and (workspace / PROJECT_FILE).exists() else None
    scope = route[0] if route else task_root.parent
    if reference.startswith("workspace_root:"):
        workspace = _workspace_root_for(task_root)
        if workspace is None:
            raise WorkflowControlError("unsafe workspace dependency reference without calculations root")
        relative = reference.split(":", 1)[1]
        candidate = _safe_child(workspace, relative, "dependency reference")
    elif reference.startswith("structure_root:"):
        relative = reference.split(":", 1)[1]
        candidate = _safe_child(scope, relative, "dependency reference")
    elif reference.startswith("task_root:"):
        relative = reference.split(":", 1)[1]
        candidate = _safe_child(task_root.parent, relative, "dependency reference")
    else:
        candidate = _safe_child(scope, reference, "dependency reference")
        if route and not (candidate / "workflow.json").is_file():
            matches = []
            for path in workflow_paths(workspace):
                if scope not in path.parents:
                    continue
                data = json.loads(path.read_text())
                if data.get("task_slug") == reference:
                    matches.append(path.parent)
            if len(matches) > 1:
                raise WorkflowControlError("Ambiguous dependency after rerun; pin a workspace_root task reference")
            if matches:
                candidate = matches[0]
    if not candidate.is_dir():
        return None, reference
    # A dependency may be a sibling, a structure-root reference, or a scoped
    # workspace reference; after resolution it must not become a symlinked leaf.
    _reject_symlink(candidate, "dependency task")
    return candidate, reference


def _as_artifact_specs(value: Any) -> list[tuple[str, str | None]]:
    if value is None:
        return []
    raw_items = [value] if isinstance(value, str) or isinstance(value, Mapping) else value
    if not isinstance(raw_items, (list, tuple)):
        return []
    result: list[tuple[str, str | None]] = []
    for item in raw_items:
        if isinstance(item, str):
            result.append((item, None))
        elif isinstance(item, Mapping):
            name = item.get("name", item.get("artifact", item.get("path")))
            if isinstance(name, str) and name.strip():
                digest = item.get("sha256", item.get("hash"))
                result.append((name, str(digest) if digest is not None else None))
    return result


def _artifact_records(workflow: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}

    def add(name: Any, raw: Any) -> None:
        if isinstance(raw, Mapping):
            record = dict(raw)
            record.setdefault("name", name)
        elif isinstance(raw, str) and re.fullmatch(r"[0-9a-fA-F]{64}", raw):
            record = {"name": name, "sha256": raw, "status": "complete"}
        else:
            record = {"name": name, "status": raw}
        record_name = record.get("name", record.get("artifact", record.get("path")))
        if isinstance(record_name, str) and record_name.strip():
            records[record_name.casefold()] = record

    for field in ("artifacts", "outputs"):
        value = workflow.get(field)
        if isinstance(value, Mapping):
            for name, raw in value.items():
                add(name, raw)
        elif isinstance(value, list):
            for raw in value:
                if isinstance(raw, Mapping):
                    add(raw.get("name", raw.get("artifact", raw.get("path"))), raw)
    result = workflow.get("result")
    if isinstance(result, Mapping):
        value = result.get("artifacts", result.get("outputs"))
        if isinstance(value, Mapping):
            for name, raw in value.items():
                add(name, raw)
        elif isinstance(value, list):
            for raw in value:
                if isinstance(raw, Mapping):
                    add(raw.get("name", raw.get("artifact", raw.get("path"))), raw)
    completion = workflow.get("completion")
    if isinstance(completion, Mapping):
        value = completion.get("artifacts", completion.get("outputs"))
        if isinstance(value, Mapping):
            for name, raw in value.items():
                add(name, raw)
        elif isinstance(value, list):
            for raw in value:
                if isinstance(raw, Mapping):
                    add(raw.get("name", raw.get("artifact", raw.get("path"))), raw)
    return records


def _recorded_hashes(dependency: Mapping[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for field in ("artifact_hashes", "required_artifact_hashes", "hashes"):
        value = dependency.get(field)
        if isinstance(value, Mapping):
            for name, digest in value.items():
                if digest is not None:
                    result[str(name).casefold()] = str(digest)
    return result


def _artifact_path(upstream: Path, name: str, record: Mapping[str, Any] | None) -> Path:
    raw_path = record.get("path", record.get("file", name)) if record else name
    if not isinstance(raw_path, str) or not raw_path.strip():
        raw_path = name
    return _safe_child(upstream, raw_path, "upstream artifact")


def _artifact_is_parseable(path: Path, record: Mapping[str, Any] | None) -> bool:
    if record is not None:
        if record.get("parseable") is False:
            return False
        parse_status = str(record.get("parse_status", record.get("parser_status", ""))).casefold()
        if parse_status in {"failed", "incomplete", "missing", "pending", "unparseable", "false"}:
            return False
        status = str(record.get("status", "")).casefold()
        if status in {"failed", "incomplete", "missing", "pending", "unparseable"}:
            return False
    if path.suffix.casefold() == ".json":
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return False
    return True


def evaluate_dependencies(task_root: Path) -> dict[str, Any]:
    """Return the deterministic upstream verdict without modifying the leaf."""

    root, _, workflow, _ = _load_workflow(task_root)
    if _has_major_conflict(workflow):
        return _result(
            "MAJOR_CONFLICT",
            ["unresolved L3 parameter reconciliation requires a user decision"],
            [
                {
                    "task_ref": str(workflow.get("task_slug", root.name)),
                    "artifact": "parameter_reconciliation",
                    "status": "major_conflict",
                }
            ],
        )

    technical = _technical_failure(workflow)
    if technical is not None:
        return _result(
            "RETRY_IN_PLACE",
            [f"recognized technical failure {technical}; retry in place"],
            [
                {
                    "task_ref": str(workflow.get("task_slug", root.name)),
                    "artifact": "scheduler/environment",
                    "status": "technical_failure",
                }
            ],
        )

    dependencies = workflow.get("dependencies", [])
    if dependencies is None:
        dependencies = []
    if not isinstance(dependencies, list):
        return _result("NEEDS_AGENT", ["dependency records are not a list"], [])
    if not dependencies:
        return _result("ADVANCE", [], [])

    reasons: list[str] = []
    evidence: list[dict[str, str]] = []
    major_conflict = False
    for dependency in dependencies:
        if not isinstance(dependency, Mapping):
            reasons.append("dependency record is not an object")
            continue
        upstream, task_ref = _resolve_dependency(root, dependency)
        if upstream is None:
            reasons.append(f"upstream task is missing: {task_ref}")
            evidence.append({"task_ref": task_ref, "artifact": "workflow.json", "status": "upstream_missing"})
            continue
        upstream_workflow_path = _safe_child(upstream, "workflow.json", "upstream workflow record")
        if not upstream_workflow_path.is_file():
            reasons.append(f"upstream workflow record is missing: {task_ref}")
            evidence.append({"task_ref": task_ref, "artifact": "workflow.json", "status": "upstream_missing"})
            continue
        try:
            upstream_workflow = json.loads(upstream_workflow_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            reasons.append(f"upstream workflow record is not parseable: {task_ref} ({exc})")
            evidence.append({"task_ref": task_ref, "artifact": "workflow.json", "status": "unparseable"})
            continue
        if not isinstance(upstream_workflow, Mapping):
            reasons.append(f"upstream workflow record is not an object: {task_ref}")
            evidence.append({"task_ref": task_ref, "artifact": "workflow.json", "status": "unparseable"})
            continue
        if _has_major_conflict(upstream_workflow):
            major_conflict = True
            reasons.append(f"upstream has unresolved L3 reconciliation: {task_ref}")
            evidence.append(
                {"task_ref": task_ref, "artifact": "parameter_reconciliation", "status": "major_conflict"}
            )
            continue
        completion = upstream_workflow.get("completion")
        if not isinstance(completion, Mapping) or completion.get("artifact_complete") is not True:
            reasons.append(f"upstream artifact completion is not recorded: {task_ref}")
            for artifact_name, _ in _as_artifact_specs(dependency.get("required_artifacts")):
                evidence.append(
                    {"task_ref": task_ref, "artifact": artifact_name, "status": "upstream_artifact_incomplete"}
                )
            continue

        records = _artifact_records(upstream_workflow)
        expected_hashes = _recorded_hashes(dependency)
        specs = _as_artifact_specs(dependency.get("required_artifacts"))
        if not specs:
            # The dependency contract is allowed to express ordering without
            # transferring a file.  Once the upstream ledger explicitly says
            # its artifacts are complete, the empty requirement is vacuously
            # satisfied.
            continue
        for artifact_name, inline_hash in specs:
            _relative_parts(artifact_name, "artifact name")
            record = records.get(artifact_name.casefold())
            if record is None:
                # A record may use a full relative path while the dependency
                # names the leaf artifact.  Match by basename only after exact
                # matching to keep the decision deterministic.
                record = next(
                    (
                        value
                        for key, value in records.items()
                        if Path(str(value.get("path", value.get("name", key)))).name.casefold()
                        == Path(artifact_name).name.casefold()
                    ),
                    None,
                )
            artifact_path = _artifact_path(upstream, artifact_name, record)
            if not artifact_path.exists():
                reasons.append(f"required upstream artifact is missing: {task_ref}/{artifact_name}")
                evidence.append({"task_ref": task_ref, "artifact": artifact_name, "status": "missing"})
                continue
            _require_regular_file(artifact_path, "upstream artifact")
            if artifact_path.stat().st_size == 0:
                reasons.append(f"required upstream artifact is empty: {task_ref}/{artifact_name}")
                evidence.append({"task_ref": task_ref, "artifact": artifact_name, "status": "empty"})
                continue
            actual_hash = _sha256(artifact_path)
            expected_hash = inline_hash or expected_hashes.get(artifact_name.casefold())
            if expected_hash is None and record is not None:
                raw_hash = record.get("sha256", record.get("hash"))
                expected_hash = str(raw_hash) if raw_hash is not None else None
            if expected_hash is not None and actual_hash.casefold() != str(expected_hash).casefold():
                reasons.append(f"recorded hash does not match upstream artifact: {task_ref}/{artifact_name}")
                evidence.append({"task_ref": task_ref, "artifact": artifact_name, "status": "hash_mismatch"})
                continue
            if not _artifact_is_parseable(artifact_path, record):
                reasons.append(f"required upstream artifact is not parseable: {task_ref}/{artifact_name}")
                evidence.append({"task_ref": task_ref, "artifact": artifact_name, "status": "unparseable"})
                continue
            evidence.append({"task_ref": task_ref, "artifact": artifact_name, "status": "complete"})

    if major_conflict:
        return _result("MAJOR_CONFLICT", reasons, evidence)
    if reasons:
        return _result("NEEDS_AGENT", reasons, evidence)
    return _result("ADVANCE", [], evidence)


def _validate_agent_decision(decision: Mapping[str, Any]) -> tuple[str, str, Any]:
    if not isinstance(decision, Mapping):
        raise WorkflowControlError("Agent decision must be an object")
    verdict = decision.get("verdict")
    if not isinstance(verdict, str) or verdict not in AGENT_VERDICTS:
        raise WorkflowControlError(
            "Agent decision verdict must be one of the five exact values: "
            + ", ".join(sorted(AGENT_VERDICTS))
        )
    reason = decision.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        raise WorkflowControlError("Agent decision requires a non-empty reason")
    if "evidence" not in decision:
        raise WorkflowControlError("Agent decision requires evidence")
    evidence = decision.get("evidence")
    if not isinstance(evidence, (Mapping, list, tuple)) or not evidence:
        raise WorkflowControlError("Agent decision evidence must be non-empty")
    return verdict, reason.strip(), evidence


def record_agent_decision(task_root: Path, decision: Mapping[str, Any]) -> dict[str, Any]:
    """Record one exact Agent verdict and apply only its state transition."""

    root, workflow_path, workflow, _ = _load_workflow(task_root)
    verdict, reason, evidence = _validate_agent_decision(decision)
    if _has_major_conflict(workflow) and verdict not in {"REQUEST_PARAMETER_REVISION", "MAJOR_CONFLICT"}:
        raise WorkflowControlError(
            "Agent decision cannot bypass an unresolved major conflict; request a parameter revision"
        )
    timestamp = _now()
    record: dict[str, Any] = {
        "verdict": verdict,
        "reason": reason,
        "evidence": copy.deepcopy(evidence),
        "recorded_at": timestamp,
    }
    for key, value in decision.items():
        if key not in record and key not in {"verdict", "reason", "evidence"}:
            record[str(key)] = copy.deepcopy(value)

    updated = copy.deepcopy(workflow)
    updated["agent_decision"] = record
    decisions = updated.setdefault("agent_decisions", [])
    if not isinstance(decisions, list):
        raise WorkflowControlError("workflow agent_decisions must be a list")
    decisions.append(copy.deepcopy(record))
    history = updated.setdefault("history", [])
    if not isinstance(history, list):
        raise WorkflowControlError("workflow history must be a list")
    history.append(
        {
            "at": timestamp,
            "status": f"agent_{verdict.casefold()}",
            "note": reason,
            "agent_verdict": verdict,
            "evidence": copy.deepcopy(evidence),
        }
    )

    if verdict in {"REQUEST_PARAMETER_REVISION", "MAJOR_CONFLICT"}:
        updated["status"] = "awaiting_user_decision"
        submission = updated.setdefault("submission", {})
        if not isinstance(submission, dict):
            raise WorkflowControlError("workflow submission must be an object")
        submission["allowed"] = False
        blockers = submission.setdefault("blockers", [])
        if isinstance(blockers, list) and reason not in blockers:
            blockers.append(reason)
        updated["recovery_mode"] = "awaiting_user_decision"
    elif verdict == "ADVANCE":
        if updated.get("status") == "awaiting_upstream":
            updated["status"] = "prepared"
        updated["recovery_mode"] = "none"
    elif verdict == "RETRY_IN_PLACE":
        updated["recovery_mode"] = "retry_in_place"
    elif verdict == "CREATE_RERUN":
        updated["recovery_mode"] = "create_rerun_branch"
    updated["updated_at"] = timestamp
    _atomic_write_json(workflow_path, updated)

    returned = copy.deepcopy(record)
    returned["workflow_status"] = updated.get("status")
    returned["task_root"] = str(root)
    return returned


def _used_numbered_directories(parent: Path, pattern: re.Pattern[str], label: str) -> set[int]:
    used: set[int] = set()
    if not parent.exists():
        parent.mkdir(parents=True, exist_ok=True)
    _reject_symlink(parent, label)
    if not parent.is_dir():
        raise WorkflowControlError(f"{label} is not a directory: {parent}")
    for child in parent.iterdir():
        match = pattern.fullmatch(child.name)
        if not match:
            continue
        _reject_symlink(child, label)
        try:
            used.add(int(match.group(1)))
        except ValueError as exc:  # pragma: no cover - regex only admits digits
            raise WorkflowControlError(f"invalid {label} index: {child.name}") from exc
    return used


def _next_number(used: set[int]) -> int:
    return max(used, default=0) + 1


def _input_references(workflow: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    inputs = workflow.get("inputs")
    if isinstance(inputs, Mapping):
        files = inputs.get("files", [])
        if isinstance(files, list):
            return [item for item in files if isinstance(item, Mapping)]
        return []
    if isinstance(inputs, list):
        return [item for item in inputs if isinstance(item, Mapping)]
    return []


def _output_like(path: Path) -> bool:
    name = path.name.casefold()
    return (
        name in _OUTPUT_NAME_CASEFOLD
        or name.startswith("slurm-")
        or name == "vasp.out"
        or name.endswith(".err")
        or (name.endswith(".out") and not name.endswith(".in.out"))
    )


def _declared_current_files(root: Path, workflow: Mapping[str, Any]) -> list[tuple[str, Path, str]]:
    result: list[tuple[str, Path, str]] = []
    seen: set[str] = set()
    has_declared_task_root_input = False
    for reference in _input_references(workflow):
        base = reference.get("base", "task_root")
        if base != "task_root":
            continue
        raw_path = reference.get("path", reference.get("name"))
        if not isinstance(raw_path, str) or not raw_path.strip():
            continue
        has_declared_task_root_input = True
        path = _safe_child(root, raw_path, "declared engine input")
        role = str(reference.get("role", "engine_input"))
        if "output" in role.casefold() or "artifact" in role.casefold():
            continue
        if not path.exists():
            raise WorkflowControlError(f"missing declared current input: {path}")
        if _output_like(path):
            continue
        key = path.relative_to(root).as_posix()
        if key not in seen:
            _require_regular_file(path, "declared engine input")
            seen.add(key)
            result.append((key, path, role))

    if result or has_declared_task_root_input:
        return result
    engine = str(workflow.get("engine", "")).casefold()
    fallback_names: list[str] = sorted(_VASP_INPUTS) if engine == "vasp" else []
    if engine in {"quantum-espresso", "qe"}:
        fallback_names = sorted(
            path.name for path in root.iterdir() if path.is_file() and path.suffix.casefold() == ".in"
        )
    for name in fallback_names:
        path = _safe_child(root, name, "engine input")
        if path.exists() and not _output_like(path):
            _require_regular_file(path, "engine input")
            result.append((name, path, "engine_input"))
    return result


def _slurm_log_files(root: Path, workflow: Mapping[str, Any]) -> list[tuple[str, Path, str]]:
    result: list[tuple[str, Path, str]] = []
    seen: set[str] = set()
    for candidate in root.iterdir():
        if candidate.is_file() and _SLURM_LOG_RE.fullmatch(candidate.name):
            _require_regular_file(candidate, "Slurm log")
            result.append((candidate.name, candidate, "slurm_log"))
            seen.add(candidate.name)
    for container_name in ("submission", "scheduler", "job"):
        container = workflow.get(container_name)
        if not isinstance(container, Mapping):
            continue
        for field in ("stdout", "stderr", "output", "error"):
            raw_path = container.get(field)
            if not isinstance(raw_path, str) or not raw_path.strip():
                continue
            path = _safe_child(root, raw_path, "Slurm log reference")
            if path.name in seen or not path.exists():
                continue
            _require_regular_file(path, "Slurm log")
            result.append((path.relative_to(root).as_posix(), path, "slurm_log"))
            seen.add(path.name)
    return result


def _copy_snapshot_file(source: Path, stage_root: Path, relative: str, kind: str) -> dict[str, Any]:
    parts = _relative_parts(relative, "snapshot file")
    destination = stage_root.joinpath(*parts)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() or destination.is_symlink():
        raise WorkflowControlError(f"snapshot destination collision: {destination}")
    shutil.copy2(source, destination)
    return {
        "source": Path(*parts).as_posix(),
        "path": Path(*parts).as_posix(),
        "archive_path": Path(*parts).as_posix(),
        "kind": kind,
        "sha256": _sha256(source),
        "size": source.stat().st_size,
    }


def _remove_owned_directory(path: Path) -> None:
    if path.exists() and not path.is_symlink():
        shutil.rmtree(path)


def archive_attempt(task_root: Path, reason: str) -> Path:
    """Snapshot replaceable evidence under the same leaf and record the attempt."""

    root, workflow_path, workflow, workflow_bytes = _load_workflow(task_root)
    if not isinstance(reason, str) or not reason.strip():
        raise WorkflowControlError("archive reason must be non-empty")
    attempts_root = root / "attempts"
    attempts_was_present = attempts_root.exists()
    if attempts_root.is_symlink():
        raise WorkflowControlError(f"unsafe attempt archive: symlink is not allowed: {attempts_root}")
    # Validate all source references before creating the archive directory.  A
    # rejected unsafe record should not leave even an empty recovery directory.
    used = (
        _used_numbered_directories(attempts_root, _ATTEMPT_RE, "attempt archive")
        if attempts_root.exists()
        else set()
    )
    recorded_attempts = workflow.get("attempts", [])
    if not isinstance(recorded_attempts, list):
        raise WorkflowControlError("workflow attempts must be a list")
    for record in recorded_attempts:
        if not isinstance(record, Mapping):
            raise WorkflowControlError("workflow attempt records must be objects")
        raw_attempt_id = record.get("attempt_id")
        if raw_attempt_id is None:
            continue
        if not isinstance(raw_attempt_id, str):
            raise WorkflowControlError("workflow attempt_id must be a string")
        match = _ATTEMPT_RE.fullmatch(raw_attempt_id)
        if match is not None:
            used.add(int(match.group(1)))
    attempt_number = _next_number(used)
    attempt_id = f"attempt-{attempt_number:03d}"
    final = _safe_child(attempts_root, attempt_id, "attempt archive")
    if final.exists() or final.is_symlink():
        raise WorkflowControlError(f"attempt archive already exists: {final}")

    sources: list[tuple[str, Path, str]] = []
    sources.extend(_declared_current_files(root, workflow))
    job_path = _resolve_job_script(root, workflow, required=False)
    if job_path.exists():
        _require_regular_file(job_path, "job script")
        sources.append((job_path.relative_to(root).as_posix(), job_path, "job_template"))
    sources.extend(_slurm_log_files(root, workflow))
    sources.append(("workflow.json", workflow_path, "workflow_record"))

    deduplicated: list[tuple[str, Path, str]] = []
    seen_paths: set[str] = set()
    for relative, source, kind in sources:
        if relative in seen_paths:
            continue
        _require_regular_file(source, "snapshot source")
        seen_paths.add(relative)
        deduplicated.append((relative, source, kind))

    if attempts_root.is_symlink():
        raise WorkflowControlError(f"unsafe attempt archive: symlink is not allowed: {attempts_root}")
    if not attempts_root.exists():
        attempts_root.mkdir(parents=True, exist_ok=False)
    _reject_symlink(attempts_root, "attempt archive")
    if not attempts_root.is_dir():
        raise WorkflowControlError(f"attempt archive is not a directory: {attempts_root}")
    # Re-read after reserving the parent so a concurrent archive cannot make
    # this operation overwrite or reuse an attempt selected by the first scan.
    used = _used_numbered_directories(attempts_root, _ATTEMPT_RE, "attempt archive") | used
    attempt_number = _next_number(used)
    attempt_id = f"attempt-{attempt_number:03d}"
    final = _safe_child(attempts_root, attempt_id, "attempt archive")
    if final.exists() or final.is_symlink():
        raise WorkflowControlError(f"attempt archive already exists: {final}")
    stage = Path(tempfile.mkdtemp(prefix=f".{attempt_id}.", dir=str(attempts_root)))
    try:
        manifest_files: list[dict[str, Any]] = []
        for relative, source, kind in deduplicated:
            manifest_files.append(_copy_snapshot_file(source, stage, relative, kind))
        manifest = {
            "schema_version": 1,
            "attempt_id": attempt_id,
            "reason": reason.strip(),
            "created_at": _now(),
            "task_slug": workflow.get("task_slug"),
            "files": manifest_files,
            "replaced_files": [item["path"] for item in manifest_files],
        }
        _atomic_write_json(stage / "manifest.json", manifest)
        if final.exists() or final.is_symlink():
            raise WorkflowControlError(f"attempt archive appeared during creation: {final}")
        os.rename(stage, final)
        stage = Path()

        updated = copy.deepcopy(workflow)
        attempts = updated.setdefault("attempts", [])
        if not isinstance(attempts, list):
            raise WorkflowControlError("workflow attempts must be a list")
        snapshot_files = {
            item["path"]: {
                "sha256": item["sha256"],
                "size": item["size"],
                "kind": item["kind"],
            }
            for item in manifest_files
        }
        attempts.append(
            {
                "attempt_id": attempt_id,
                "reason": reason.strip(),
                "snapshot": {
                    "archive": f"task_root:attempts/{attempt_id}",
                    "files": snapshot_files,
                    "workflow_sha256": _sha256(final / "workflow.json"),
                },
                "archived_at": manifest["created_at"],
            }
        )
        updated["last_attempt_id"] = attempt_id
        updated["recovery_mode"] = "retry_in_place"
        updated["updated_at"] = manifest["created_at"]
        history = updated.setdefault("history", [])
        if not isinstance(history, list):
            raise WorkflowControlError("workflow history must be a list")
        history.append(
            {
                "at": manifest["created_at"],
                "status": "retry_in_place",
                "note": reason.strip(),
                "attempt_id": attempt_id,
            }
        )
        try:
            _atomic_write_json(workflow_path, updated)
        except Exception:
            _remove_owned_directory(final)
            raise
        return final
    except Exception:
        if stage and str(stage) not in {".", ""}:
            _remove_owned_directory(stage)
        if not attempts_was_present and attempts_root.exists() and not attempts_root.is_symlink():
            try:
                attempts_root.rmdir()
            except OSError:
                pass
        raise


def _lineage_reference(task_root: Path) -> str:
    workspace = _workspace_root_for(task_root)
    if workspace is not None:
        relative = task_root.relative_to(workspace).as_posix()
        return f"workspace_root:{relative}"
    return f"task_root:{task_root.name}"


def _validate_parameter_changes(parameter_changes: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if isinstance(parameter_changes, (str, bytes)) or not isinstance(parameter_changes, Sequence):
        raise WorkflowControlError("parameter_changes must be a sequence of objects")
    result: list[dict[str, Any]] = []
    for index, change in enumerate(parameter_changes):
        if not isinstance(change, Mapping):
            raise WorkflowControlError(f"parameter_changes[{index}] must be an object")
        result.append(copy.deepcopy(dict(change)))
    return result


def _update_rerun_input_hashes(
    workflow: dict[str, Any],
    stage: Path,
    copied: Mapping[str, Path],
    job_relative: str | None = None,
) -> None:
    inputs = workflow.get("inputs")
    if isinstance(inputs, Mapping):
        files = inputs.get("files")
        if isinstance(files, list):
            for reference in files:
                if not isinstance(reference, dict):
                    continue
                raw_path = reference.get("path", reference.get("name"))
                if not isinstance(raw_path, str):
                    continue
                key = Path(raw_path).as_posix()
                if key in copied:
                    reference["base"] = "task_root"
                    reference["sha256"] = _sha256(copied[key])
    job = workflow.get("job")
    if isinstance(job, dict) and job_relative is not None and job_relative in copied:
        job["script"] = f"task_root:{job_relative}"
        job["sha256"] = _sha256(copied[job_relative])


def create_rerun_branch(
    task_root: Path,
    reason: str,
    parameter_changes: Sequence[Mapping[str, Any]],
) -> Path:
    """Create a scientific candidate, nested for routes, preserving all source evidence."""

    root, _, workflow, _ = _load_workflow(task_root)
    if not isinstance(reason, str) or not reason.strip():
        raise WorkflowControlError("rerun reason must be non-empty")
    state = str(workflow.get("status", "")).casefold()
    if state not in {"completed", "inconclusive", "failed"}:
        raise WorkflowControlError("rerun source must be completed, inconclusive or failed")
    changes = _validate_parameter_changes(parameter_changes)
    current_files = _declared_current_files(root, workflow)

    workspace = _workspace_root_for(root)
    route = route_for(root) if workspace and (workspace / PROJECT_FILE).exists() else None
    parent = (root.parent if root.parent.name == "revisions" else root / "revisions") if route else root.parent.resolve()
    if route:
        parent.mkdir(exist_ok=True)
    _reject_symlink(parent, "rerun parent")
    used = _used_numbered_directories(parent, _RERUN_RE, "rerun branch")
    number = _next_number(used)
    rerun_id = f"rerun_{number:03d}"
    final = _safe_child(parent, rerun_id, "rerun branch")
    if final.exists() or final.is_symlink():
        raise WorkflowControlError(f"rerun branch already exists: {final}")

    job_path = _resolve_job_script(root, workflow, required=False)
    job_relative = job_path.relative_to(root).as_posix() if job_path.exists() else None
    if job_path.exists():
        _require_regular_file(job_path, "job script")
    stage = Path(tempfile.mkdtemp(prefix=f".{rerun_id}.", dir=str(parent)))
    try:
        copied: dict[str, Path] = {}
        for relative, source, _ in current_files:
            destination = stage.joinpath(*_relative_parts(relative, "rerun input"))
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists() or destination.is_symlink():
                raise WorkflowControlError(f"rerun input destination collision: {destination}")
            shutil.copy2(source, destination)
            copied[Path(relative).as_posix()] = destination
        if job_path.exists():
            destination = stage.joinpath(*_relative_parts(job_relative, "rerun job script"))
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists() or destination.is_symlink():
                raise WorkflowControlError(f"rerun job script destination collision: {destination}")
            shutil.copy2(job_path, destination)
            copied[job_relative] = destination

        updated = copy.deepcopy(workflow)
        updated.pop("management", None)
        updated["status"] = "awaiting_upstream" if updated.get("dependencies") else "prepared"
        updated["variant_slug"] = rerun_id
        updated["task_uuid"] = str(uuid4())
        submission = updated.setdefault("submission", {})
        if not isinstance(submission, dict):
            raise WorkflowControlError("workflow submission must be an object")
        submission["state"] = "not_submitted"
        submission["allowed"] = False
        submission["job_id"] = None
        completion_record = updated.setdefault("completion", {})
        if not isinstance(completion_record, dict):
            raise WorkflowControlError("workflow completion must be an object")
        completion_record["scheduler_complete"] = False
        completion_record["artifact_complete"] = False
        completion_record["scientifically_accepted"] = False
        updated["attempts"] = []
        updated["result"] = {"status": "not_started", "summary": None}
        updated["lineage"] = copy.deepcopy(updated.get("lineage", {}))
        if not isinstance(updated["lineage"], dict):
            updated["lineage"] = {}
        source_reference = _lineage_reference(root)
        updated["lineage"].update(
            {
                "derived_from": source_reference,
                "derived_from_uuid": workflow.get("task_uuid"),
                "supersedes": None,
                "reason": reason.strip(),
                "parameter_changes": copy.deepcopy(changes),
            }
        )
        updated["rerun"] = {
            "verify_parameter_changes": bool(route),
            "branch": rerun_id,
            "derived_from": source_reference,
            "reason": reason.strip(),
            "parameter_changes": copy.deepcopy(changes),
        }
        _update_rerun_input_hashes(updated, stage, copied, job_relative)
        updated["updated_at"] = _now()
        history = updated.setdefault("history", [])
        if not isinstance(history, list):
            raise WorkflowControlError("workflow history must be a list")
        history.append(
            {
                "at": updated["updated_at"],
                "status": updated["status"],
                "note": f"created {rerun_id} from {source_reference}: {reason.strip()}",
                "lineage": source_reference,
            }
        )
        _atomic_write_json(stage / "workflow.json", updated)
        if not route:
            _atomic_write_bytes(
                stage / "README.md",
                (
                    f"# {updated.get('task_slug', root.name)} / {rerun_id}\n\n"
                    f"- Status: `{updated['status']}`\n"
                    f"- Derived from: `{source_reference}`\n"
                    f"- Reason: {reason.strip()}\n"
                ).encode("utf-8"),
            )
        if final.exists() or final.is_symlink():
            raise WorkflowControlError(f"rerun branch appeared during creation: {final}")
        os.rename(stage, final)
        stage = Path()
        if route:
            from dft_contracts.project import explain_directories
            explain_directories(workspace, parent)
            from dft_contracts.readmes import after_operation
            after_operation(final)
        return final
    except Exception:
        if stage and str(stage) not in {".", ""}:
            _remove_owned_directory(stage)
        raise
