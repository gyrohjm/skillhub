#!/usr/bin/env python3
"""Prepare and execute canonical DFT task leaves through one submission adapter.

The helper is intentionally conservative: it verifies one immutable
``dft-design`` approval event (or prepares unapproved drafts), preserves current
engine inputs, uses selected dft-submit script/profile data, and writes live
machine state to the leaf's single ``workflow.json``.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

if __name__ == "__main__":
    # Helper modules must share this module's error class and state on CLI execution.
    sys.modules["canonical_workflow"] = sys.modules[__name__]

SKILL_ROOT = Path(__file__).resolve().parents[1]
DESIGN_SCRIPTS = SKILL_ROOT.parent / "dft-design" / "scripts"
CONTRACTS_ROOT = SKILL_ROOT.parent / "dft-contracts"
if str(CONTRACTS_ROOT) not in sys.path:
    sys.path.insert(0, str(CONTRACTS_ROOT))
from dft_contracts import validate_document
from dft_contracts.project import init_project
from dft_contracts.layout import (PROJECT_FILE, discover_workspace, route_for, calculation_scope,
                                  design_plan_root, STAGE_RE)
from uuid import uuid4
from input_reconciliation import parse_current_inputs, snapshot_primary_input, reconcile_task as _reconcile_task
from workflow_control import (
    archive_attempt as _archive_attempt,
    create_rerun_branch as _create_rerun_branch,
    evaluate_dependencies as _evaluate_dependencies,
    record_agent_decision as _record_agent_decision,
)

SLUG_RE = re.compile(r"[a-z0-9]+(?:_[a-z0-9]+)*")
TASK_RE = STAGE_RE
RESOURCE_START = "<!-- dft-workflow:profiles:start -->"
RESOURCE_END = "<!-- dft-workflow:profiles:end -->"
FORBIDDEN_MACHINE_FILES = {
    "task_spec.json",
    "state.json",
    "submission.json",
    "submission_approval.json",
    "preflight.json",
    "parse.json",
}


class WorkflowError(RuntimeError):
    """A preparation gate failed before a runnable task was created."""


def reconcile_before_readiness(
    task_root: str | Path, design_path: str | Path, *, write: bool = True
) -> dict[str, Any]:
    """Run input reconciliation at the canonical readiness seam."""

    return _reconcile_task(Path(task_root), Path(design_path), write=write)


def reconcile_task(
    task_root: str | Path, design_path: str | Path, *, write: bool = True
) -> dict[str, Any]:
    """Public compatibility alias for the readiness reconciliation hook."""

    return reconcile_before_readiness(task_root, design_path, write=write)


def evaluate_dependencies(task_root: str | Path) -> dict[str, Any]:
    """Expose the deterministic Task 4 dependency gate on the canonical path."""

    return _evaluate_dependencies(Path(task_root))


def record_agent_decision(
    task_root: str | Path, decision: Mapping[str, Any]
) -> dict[str, Any]:
    """Record a bounded professional-Agent decision for one canonical leaf."""

    return _record_agent_decision(Path(task_root), decision)


def archive_attempt(task_root: str | Path, reason: str) -> Path:
    """Archive replaceable evidence without changing the task leaf identity."""

    return _archive_attempt(Path(task_root), reason)


def create_rerun_branch(
    task_root: str | Path,
    reason: str,
    parameter_changes: Sequence[Mapping[str, Any]],
) -> Path:
    """Create an immutable scientific rerun through the canonical seam."""

    return _create_rerun_branch(Path(task_root), reason, parameter_changes)


_SUBMISSION_ATTEMPT_RE = re.compile(r"^attempt-(\d+)$")


def _submission_task_root(task_root: str | Path) -> Path:
    raw = Path(task_root).expanduser()
    if raw.is_symlink():
        raise WorkflowError(f"unsafe task root: symlink is not allowed: {raw}")
    if not raw.exists() or not raw.is_dir():
        raise WorkflowError(f"task root does not exist: {raw}")
    return raw.resolve()


def _submission_relative_parts(value: str | Path, label: str) -> tuple[str, ...]:
    raw = str(value)
    candidate = Path(raw)
    if (
        candidate.is_absolute()
        or raw.startswith(("/", "\\"))
        or re.match(r"^[A-Za-z]:", raw)
    ):
        raise WorkflowError(f"unsafe {label}: absolute path is not allowed: {raw!r}")
    parts = candidate.parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise WorkflowError(f"unsafe {label}: path must not contain . or ..: {raw!r}")
    if any("\x00" in part for part in parts):
        raise WorkflowError(f"unsafe {label}: NUL byte in path")
    return tuple(parts)


def _submission_child(root: Path, relative: str | Path, label: str) -> Path:
    root = root.resolve()
    parts = _submission_relative_parts(relative, label)
    candidate = root.joinpath(*parts)
    current = root
    for part in parts:
        current = current / part
        if current.is_symlink():
            raise WorkflowError(f"unsafe {label}: symlink component: {current}")
    resolved = candidate.resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise WorkflowError(f"unsafe {label}: path escapes task root: {relative!r}") from exc
    return resolved


def _submission_project_root(task_root: Path) -> Path:
    try:
        return discover_workspace(task_root)
    except ValueError:
        if any((p / PROJECT_FILE).exists() for p in (task_root, *task_root.parents)):
            raise
    for parent in (task_root, *task_root.parents):
        if parent.name.casefold() == "calculations":
            return parent.parent
    for parent in (task_root, *task_root.parents):
        if (parent / ".dft").is_dir() or (parent / "plans").is_dir():
            return parent
    return task_root.parent


def _load_submission_workflow(task_root: str | Path) -> tuple[Path, Path, dict[str, Any]]:
    root = _submission_task_root(task_root)
    workflow_path = _submission_child(root, "workflow.json", "workflow record")
    if not workflow_path.is_file():
        raise WorkflowError(f"workflow.json does not exist: {workflow_path}")
    try:
        workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WorkflowError(f"workflow.json is not parseable: {exc}") from exc
    if not isinstance(workflow, dict):
        raise WorkflowError("workflow.json must contain an object")
    if workflow.get("schema_version") != 2 or workflow.get("contract") != "dft.workflow.v2":
        raise WorkflowError("submit requires a workflow-v2 task leaf")
    for reference in _submission_input_references(workflow):
        if reference.get("base", "task_root") != "task_root":
            continue
        raw_path = reference.get("path", reference.get("name"))
        if isinstance(raw_path, str) and raw_path.strip():
            _submission_relative_parts(raw_path, "declared input")
    errors = validate_document("workflow-v2", workflow)
    if errors:
        raise WorkflowError("workflow-v2 is invalid: " + "; ".join(errors))
    return root, workflow_path, workflow


def _submission_design_path(project_root: Path, workflow: Mapping[str, Any]) -> Path:
    design = workflow.get("design")
    explicit = design.get("path") if isinstance(design, Mapping) else None
    if isinstance(explicit, str) and explicit.strip():
        candidate = Path(explicit)
        if candidate.is_absolute():
            candidate = candidate.resolve()
        else:
            candidate = (project_root / candidate).resolve()
        try:
            candidate.relative_to(project_root.resolve())
        except ValueError as exc:
            raise WorkflowError(f"calculation design must stay inside the workspace: {candidate}") from exc
        return candidate
    composition = workflow.get("composition_slug")
    structure = workflow.get("structure_slug")
    if not isinstance(composition, str) or not isinstance(structure, str):
        raise WorkflowError("workflow identity is missing composition or structure")
    return design_plan_root(project_root, composition, structure) / "calculation_design.json"


def _submission_input_references(workflow: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    inputs = workflow.get("inputs")
    if isinstance(inputs, Mapping):
        files = inputs.get("files", [])
    else:
        files = inputs
    if not isinstance(files, list):
        raise WorkflowError("workflow inputs.files must be a list")
    return [item for item in files if isinstance(item, Mapping)]


def _declared_submission_files(
    task_root: Path, workflow: Mapping[str, Any]
) -> list[tuple[str, Path]]:
    files: list[tuple[str, Path]] = []
    seen: set[str] = set()
    for reference in _submission_input_references(workflow):
        base = reference.get("base", "task_root")
        if base != "task_root":
            continue
        raw_path = reference.get("path", reference.get("name"))
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise WorkflowError("declared input must have a non-empty path")
        path = _submission_child(task_root, raw_path, "declared input")
        if path.name == "workflow.json":
            raise WorkflowError(f"declared input uses a reserved path: {raw_path}")
        if not path.is_file():
            raise WorkflowError(f"missing declared input: {path}")
        relative = Path(raw_path).as_posix()
        if relative in seen:
            continue
        seen.add(relative)
        files.append((relative, path))
    if not files:
        raise WorkflowError("workflow declares no task-root inputs")
    return files


def _submission_profile(workflow: Mapping[str, Any]) -> dict[str, Any]:
    for key in ("resources", "approved_profile"):
        value = workflow.get(key)
        if isinstance(value, Mapping):
            return copy.deepcopy(dict(value))
    resource_profile = workflow.get("resource_profile")
    if isinstance(resource_profile, Mapping):
        value = resource_profile.get("profile")
        if isinstance(value, Mapping):
            return copy.deepcopy(dict(value))
    raise WorkflowError("workflow does not contain an approved resource profile")


def _submission_attempt_id(task_root: Path, workflow: Mapping[str, Any]) -> str:
    attempts_root = task_root / "attempts"
    if attempts_root.is_symlink():
        raise WorkflowError(f"unsafe attempts path: symlink is not allowed: {attempts_root}")
    if attempts_root.exists() and not attempts_root.is_dir():
        raise WorkflowError(f"attempts path is not a directory: {attempts_root}")
    used: set[int] = set()
    if attempts_root.exists():
        for child in attempts_root.iterdir():
            if child.is_symlink():
                raise WorkflowError(f"unsafe attempts path: symlink is not allowed: {child}")
            match = _SUBMISSION_ATTEMPT_RE.fullmatch(child.name)
            if match:
                used.add(int(match.group(1)))
    attempts = workflow.get("attempts", [])
    if not isinstance(attempts, list):
        raise WorkflowError("workflow attempts must be a list")
    for record in attempts:
        if not isinstance(record, Mapping):
            raise WorkflowError("workflow attempt records must be objects")
        value = record.get("attempt_id")
        if isinstance(value, str):
            match = _SUBMISSION_ATTEMPT_RE.fullmatch(value)
            if match:
                used.add(int(match.group(1)))
    return f"attempt-{max(used, default=0) + 1:03d}"


def _stage_submission_snapshot(
    task_root: Path,
    workflow: Mapping[str, Any],
    declared_files: Sequence[tuple[str, Path]],
    job_path: Path,
    attempt_id: str,
) -> tuple[Path, dict[str, Any]]:
    attempts_root = task_root / "attempts"
    attempts_root.mkdir(parents=True, exist_ok=True)
    if attempts_root.is_symlink() or not attempts_root.is_dir():
        raise WorkflowError(f"unsafe attempts path: {attempts_root}")
    final = _submission_child(task_root, Path("attempts") / attempt_id, "submission attempt")
    if final.exists() or final.is_symlink():
        raise WorkflowError(f"submission attempt already exists: {final}")
    stage = Path(tempfile.mkdtemp(prefix=f".{attempt_id}.", dir=str(attempts_root)))
    try:
        snapshot = stage / "submission_snapshot"
        snapshot.mkdir()
        records: dict[str, dict[str, Any]] = {}
        all_files = list(declared_files) + [(job_path.relative_to(task_root).as_posix(), job_path)]
        for relative, source in all_files:
            parts = _submission_relative_parts(relative, "submission snapshot file")
            destination = snapshot.joinpath(*parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists() or destination.is_symlink():
                raise WorkflowError(f"submission snapshot destination collision: {destination}")
            if source.is_symlink() or not source.is_file():
                raise WorkflowError(f"submission snapshot source is unsafe: {source}")
            shutil.copy2(source, destination)
            digest = sha256_file(source)
            if sha256_file(destination) != digest:
                raise WorkflowError("input changed while creating submission snapshot")
            records[Path(relative).as_posix()] = {
                "path": Path(relative).as_posix(),
                "sha256": digest,
                "size": source.stat().st_size,
            }
        design = workflow.get("design")
        baseline = design.get("baseline_parameter_hash") if isinstance(design, Mapping) else None
        if not isinstance(baseline, str) or not baseline:
            raise WorkflowError("workflow design is missing baseline_parameter_hash")
        manifest = {
            "schema_version": 1,
            "kind": "submission_snapshot",
            "attempt_id": attempt_id,
            "created_at": utc_now(),
            "baseline_parameter_hash": baseline,
            "files": records,
            "hashes": {name: item["sha256"] for name, item in records.items()},
        }
        _atomic_write_text(
            snapshot / "manifest.json",
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        )
        if final.exists() or final.is_symlink():
            raise WorkflowError(f"submission attempt appeared during creation: {final}")
        os.rename(stage, final)
        return final, manifest
    except Exception:
        if stage.exists() and not stage.is_symlink():
            shutil.rmtree(stage, ignore_errors=True)
        raise


def _scheduler_result(result: object) -> tuple[int, str, str]:
    return (
        int(getattr(result, "returncode", 1)),
        str(getattr(result, "stdout", "") or ""),
        str(getattr(result, "stderr", "") or ""),
    )


def _write_sbatch_receipt(
    attempt_dir: Path,
    attempt_id: str,
    argv: Sequence[str],
    returncode: int,
    stdout: str,
    stderr: str,
) -> Path:
    """Durably record a successful external submission before ledger mutation."""

    receipt_path = attempt_dir / "sbatch.receipt.json"
    receipt = {
        "schema_version": 1,
        "kind": "sbatch_receipt",
        "attempt_id": attempt_id,
        "job_id": stdout.strip().splitlines()[0].split(";", 1)[0].strip(),
        "argv": list(argv),
        "stdout": stdout,
        "stderr": stderr,
        "returncode": returncode,
        "recorded_at": utc_now(),
    }
    _atomic_write_text(
        receipt_path,
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
    )
    return receipt_path


def _run_submission_command(runner: Any, task_root: Path, script: str = "job.sh") -> object:
    argv = ["sbatch", "--parsable", script]
    if runner is subprocess.run:
        return runner(
            argv,
            cwd=str(task_root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    return runner(argv, cwd=str(task_root), env=dict(os.environ))


def _write_submission_workflow(
    workflow_path: Path, workflow: Mapping[str, Any]
) -> None:
    errors = validate_document("workflow-v2", dict(workflow))
    if errors:
        raise WorkflowError("updated workflow-v2 is invalid: " + "; ".join(errors))
    _atomic_write_text(
        workflow_path,
        json.dumps(workflow, ensure_ascii=False, indent=2) + "\n",
    )


def _record_scheduler_failure(
    project_root: Path,
    workflow_path: Path,
    workflow: Mapping[str, Any],
    attempt_dir: Path,
    manifest: Mapping[str, Any],
    returncode: int,
    stderr: str,
) -> None:
    stderr_path = attempt_dir / "sbatch.stderr"
    _atomic_write_text(stderr_path, stderr)
    updated = copy.deepcopy(dict(workflow))
    timestamp = utc_now()
    attempts = updated.get("attempts", [])
    if not isinstance(attempts, list):
        raise WorkflowError("workflow attempts must be a list")
    attempt_id = str(manifest["attempt_id"])
    attempts.append(
        {
            "attempt_id": attempt_id,
            "reason": "scheduler_rejection",
            "snapshot": {
                "archive": f"task_root:attempts/{attempt_id}/submission_snapshot",
                "files": copy.deepcopy(manifest.get("files", {})),
                "baseline_parameter_hash": manifest.get("baseline_parameter_hash"),
            },
            "scheduler": {"returncode": returncode, "stderr": stderr},
            "job_id": None,
            "submitted_at": timestamp,
        }
    )
    updated["attempts"] = attempts
    updated["status"] = "failed"
    updated["updated_at"] = timestamp
    updated["technical_failure"] = {
        "category": "scheduler",
        "code": "SCHEDULER_REJECTED",
        "returncode": returncode,
        "stderr_path": f"task_root:attempts/{attempt_id}/sbatch.stderr",
    }
    submission = updated.setdefault("submission", {})
    if not isinstance(submission, dict):
        raise WorkflowError("workflow submission must be an object")
    submission.update(
        {
            "state": "failed",
            "allowed": False,
            "job_id": None,
            "attempt_id": attempt_id,
            "error": stderr.strip() or "sbatch rejected the submission",
            "blockers": ["scheduler_rejection"],
        }
    )
    history = updated.setdefault("history", [])
    if not isinstance(history, list):
        raise WorkflowError("workflow history must be a list")
    history.append(
        {
            "at": timestamp,
            "status": "failed",
            "note": "sbatch rejected the submission; stderr preserved in the attempt",
            "attempt_id": attempt_id,
        }
    )
    _write_submission_workflow(workflow_path, updated)


def submit_task(task_root: Path, *, runner: Any = subprocess.run) -> str:
    """One entry point for reconciliation, dependency checks and durable submission."""
    from submission_safety import submission_lock
    root, _, _ = _load_submission_workflow(task_root)
    try:
        with submission_lock(root):
            return _submit_locked(root, runner=runner)
    finally:
        from dft_contracts.readmes import after_operation
        after_operation(root)


def _check_rerun_inputs(root: Path, workflow: Mapping[str, Any]) -> None:
    rerun = workflow.get("rerun", {})
    if not rerun.get("verify_parameter_changes"):
        return
    from input_reconciliation import _same_value as same_value
    current = parse_current_inputs(workflow["engine"], root,
                                   primary_input=snapshot_primary_input(root, workflow))
    values = dict(current.get("parameters", {}))
    values.update(current.get("file_hashes", {}))
    for filename, fields in current.get("file_semantics", {}).items():
        if isinstance(fields, Mapping):
            values.update({f"{filename}.{key}": value for key, value in fields.items()})
    folded = {key.casefold(): value for key, value in values.items()}
    for change in rerun.get("parameter_changes", []):
        name = str(change.get("name", "")).casefold()
        if not name or "new" not in change or name not in folded or not same_value(folded[name], change["new"]):
            raise WorkflowError("Rerun inputs do not implement the recorded parameter changes; update/reconcile the candidate before submission")


def _submit_locked(root: Path, *, runner: Any) -> str:
    from submission_safety import (assert_content, job_id_from_output, persist_success,
        recover_receipt, syntax_check)
    root, workflow_path, workflow = _load_submission_workflow(root)
    recovered = recover_receipt(root, workflow_path, workflow)
    if recovered:
        return recovered
    if not workflow.get("design", {}).get("approval_ref") or workflow.get("design", {}).get("draft"):
        raise WorkflowError("draft has no scientific parameter approval; bind approval first")
    _check_rerun_inputs(root, workflow)
    project_root = _submission_project_root(root)
    from dft_contracts.organization import guard_execution
    try:
        guard_execution(project_root, root)
    except ValueError as exc:
        raise WorkflowError(str(exc)) from exc
    from dft_contracts.layout import project_role
    try:
        if project_role(project_root) == "cluster":
            from paired_execution import check_execution
            reconciliation = check_execution(root, workflow)
        else:
            design_path = _submission_design_path(project_root, workflow)
            reconciliation = reconcile_before_readiness(root, design_path, write=True)
    except Exception as exc:
        raise WorkflowError(f"submission reconciliation failed: {exc}") from exc
    verdict = str(reconciliation.get("verdict", "NEEDS_AGENT"))
    if verdict == "MAJOR_CONFLICT":
        raise WorkflowError("submission stopped for MAJOR_CONFLICT")
    if verdict == "NEEDS_AGENT":
        return "NEEDS_AGENT"
    root, workflow_path, workflow = _load_submission_workflow(root)
    status = str(workflow.get("status", ""))
    if status not in {"prepared", "awaiting_upstream"}:
        raise WorkflowError(f"task is not ready for submission: {status or 'unknown'}")
    parsed_hashes = workflow.get("input_snapshot", {}).get("file_hashes", {})
    try:
        gate = evaluate_dependencies(root)
    except Exception as exc:
        raise WorkflowError(f"dependency gate failed: {exc}") from exc
    assert_content(root, parsed_hashes)
    gate_verdict = str(gate.get("verdict", "NEEDS_AGENT"))
    if gate_verdict == "MAJOR_CONFLICT":
        raise WorkflowError("submission stopped for MAJOR_CONFLICT dependency evidence")
    if gate_verdict != "ADVANCE":
        return gate_verdict
    from recipe_inputs import materialize_recipes
    if materialize_recipes(root, workflow_path, workflow, gate=gate):
        assert_content(root, parsed_hashes)
        # First arrival of a declared recipe is an approved dependency transition,
        # not a user change of physical model. Check its exact reviewed parameters
        # before establishing the new baseline; never baseline arbitrary file edits.
        available = dict(_declared_submission_files(root, workflow))
        validate_engine_inputs(workflow["engine"], available,
            workflow["design"].get("engine_parameters", {}), workflow.get("primary_input"))
        current = parse_current_inputs(workflow["engine"], root,
            primary_input=workflow.get("primary_input"), previous_snapshot=workflow.get("input_snapshot"))
        workflow["input_snapshot"] = current
        workflow["design"]["baseline_parameter_hash"] = current["parameter_hash"]
        _write_submission_workflow(workflow_path, workflow)
        parsed_hashes = current["file_hashes"]
    declared_files = _declared_submission_files(root, workflow)
    job_path = _job_script_path(root, workflow)
    script = job_path.relative_to(root).as_posix()
    checked_hashes = {name: sha256_file(path) for name, path in declared_files}
    checked_hashes[script] = sha256_file(job_path)
    profile = _submission_profile(workflow)
    ledger_before_checks = sha256_file(workflow_path)
    resource_module = __import__("resource_preflight")
    cached = resource_module.load_cached_preflight(project_root, profile=profile)
    cache_matches_profile = (
        cached is not None and cached.get("cache_status") == "ready"
        and resource_module.profiles_equivalent(cached.get("approved_profile"), profile))
    if not cache_matches_profile:
        probe_runner = resource_module._run_command if runner is subprocess.run else runner
        cached = resource_module.lightweight_preflight(profile, probe_runner)
        resource_module._store_cached_preflight(project_root, cached)
        if cached.get("cache_status") != "ready":
            raise WorkflowError("lightweight resource preflight failed: "
                + str(cached.get("invalidation_reason") or "unknown"))
    syntax_check(root, workflow_path, workflow, job_path, runner, expected_ledger_hash=ledger_before_checks)
    assert_content(root, checked_hashes)
    assert_content(root, parsed_hashes)
    ledger_hash = sha256_file(workflow_path)
    attempt_id = _submission_attempt_id(root, workflow)
    attempt_dir, manifest = _stage_submission_snapshot(root, workflow, declared_files, job_path, attempt_id)
    assert_content(root, checked_hashes)
    if manifest["hashes"] != checked_hashes:
        raise WorkflowError("snapshot differs from checked inputs")
    if sha256_file(workflow_path) != ledger_hash:
        raise WorkflowError("workflow changed during submission; realign before submitting")
    scheduler_argv = ["sbatch", "--parsable", script]
    # This durable intent prevents a crash/timeout after side effect from causing a blind retry.
    _atomic_write_text(attempt_dir / "submission.intent.json", json.dumps({
        "attempt_id": attempt_id, "argv": scheduler_argv, "created_at": utc_now(),
        "state": "outcome_requires_receipt"}, ensure_ascii=False, indent=2) + "\n")
    try:
        scheduler_result = _run_submission_command(runner, root, script)
        returncode, stdout, stderr = _scheduler_result(scheduler_result)
    except Exception as exc:
        _atomic_write_text(attempt_dir / "sbatch.uncertain.json",
            json.dumps({"error": str(exc), "recorded_at": utc_now()}) + "\n")
        raise WorkflowError("submission outcome is uncertain; reconcile scheduler before retrying") from exc
    job_id = job_id_from_output(stdout)
    if returncode != 0:
        # Scheduler rejections unrelated to environment/resources do not discard a valid cache.
        if re.search(r"partition|qos|account|invalid.*resource|node configuration|executable|module|activation", stderr, re.I):
            resource_module.invalidate_preflight(project_root, "scheduler_rejection", profile=profile)
        _record_scheduler_failure(project_root, workflow_path, workflow, attempt_dir, manifest,
            returncode, stderr or stdout)
        raise WorkflowError("sbatch rejected the submission")
    if not job_id:
        _atomic_write_text(attempt_dir / "sbatch.uncertain.json",
            json.dumps({"stdout": stdout, "stderr": stderr, "returncode": returncode}) + "\n")
        raise WorkflowError("submission returned no unambiguous numeric job id; reconcile scheduler before retrying")
    _write_sbatch_receipt(attempt_dir, attempt_id, scheduler_argv, returncode, stdout, stderr)
    persist_success(workflow_path, workflow, manifest, scheduler_argv, job_id)
    return job_id


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _job_script_path(task_root, workflow, *, required=True):
    from job_paths import JobPathError, resolve_job_script
    try:
        return resolve_job_script(task_root, workflow, required=required)
    except JobPathError as exc:
        raise WorkflowError(str(exc)) from exc


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _inside(root: Path, path: Path, label: str) -> Path:
    root = root.resolve()
    path = path.expanduser().resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise WorkflowError(f"{label} must stay inside the workspace: {path}") from exc
    return path


def workspace_path(project_root: Path, path: str | Path, label: str) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = project_root / candidate
    return _inside(project_root, candidate, label)


def relative_ref(project_root: Path, path: Path) -> str:
    return path.resolve().relative_to(project_root.resolve()).as_posix()


def validate_project(
    project_root: str | Path, *, require_calculations: bool = True
) -> Path:
    root = Path(project_root).expanduser().resolve()
    if not root.is_dir():
        raise WorkflowError(f"workspace does not exist: {root}")
    if require_calculations and not (root / "calculations").is_dir() and not (root / PROJECT_FILE).is_file():
        raise WorkflowError(f"workspace is missing calculations/: {root}")
    markers = (PROJECT_FILE, "AGENTS.md", "README.md", "README.rst", "pyproject.toml", ".git")
    if not any((root / marker).exists() for marker in markers):
        raise WorkflowError(f"workspace has no project marker: {root}")
    return root


def initialize_calculation_tree(project_root: str | Path) -> Path:
    """Explicitly initialize only the canonical calculations root."""

    root = validate_project(project_root, require_calculations=False)
    calculations = root / "calculations"
    if calculations.exists() and not calculations.is_dir():
        raise WorkflowError(f"calculations path exists but is not a directory: {calculations}")
    calculations.mkdir(exist_ok=True)
    _write_if_missing(
        calculations / "README.md",
        "# Calculations\n\nRaw engine inputs and outputs organized by composition and structure.",
    )
    return calculations


def _slug(value: str, label: str, *, task: bool = False) -> str:
    pattern = TASK_RE if task else SLUG_RE
    if not isinstance(value, str) or not pattern.fullmatch(value):
        expected = "pN[_name]" if task else "lowercase ASCII"
        raise WorkflowError(f"{label} slug must use {expected}: {value!r}")
    return value


def resolve_leaf(
    project_root: str | Path,
    composition: str,
    structure: str,
    task: str,
    variant: str | None,
) -> Path:
    root = validate_project(project_root)
    parts = [
        _slug(composition, "composition"),
        _slug(structure, "structure"),
        _slug(task, "task", task=True),
    ]
    if variant is not None:
        parts.append(_slug(variant, "variant"))
    return _inside(root / "calculations", root / "calculations" / Path(*parts), "task leaf")


def _load_design_verifier():
    if not (DESIGN_SCRIPTS / "computation_design.py").is_file():
        raise WorkflowError(
            "dft-design verifier is unavailable; cannot verify history.jsonl approval"
        )
    path_text = str(DESIGN_SCRIPTS)
    if path_text not in sys.path:
        sys.path.insert(0, path_text)
    try:
        import computation_design  # type: ignore
    except Exception as exc:  # pragma: no cover - defensive import boundary
        raise WorkflowError(f"cannot load dft-design verifier: {exc}") from exc
    return computation_design


def verify_design_approval(
    project_root: Path,
    history_path: str | Path,
    event_id: str,
    matrix_id: str,
    stage: str,
    engine: str,
    composition: str,
    structure: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], Path]:
    history = workspace_path(project_root, history_path, "design history")
    if history.name != "history.jsonl" or not history.is_file():
        raise WorkflowError(f"design approval must reference an existing history.jsonl: {history}")
    verifier = _load_design_verifier()
    try:
        approval, design = verifier.verify_approval(history, event_id)
    except Exception as exc:
        raise WorkflowError(f"scientific design approval verification failed: {exc}") from exc
    plan_root = (design_plan_root(history, composition, structure) if (project_root / PROJECT_FILE).exists()
                 else project_root / "plans" / composition / structure)
    expected_history = plan_root / "history.jsonl"
    expected_design = (plan_root / "calculation_design.json").relative_to(project_root).as_posix()
    if history != expected_history.resolve() or approval.get("design_path") != expected_design:
        raise WorkflowError(
            "design plan scope does not match target composition/structure: "
            f"expected plans/{composition}/{structure}/"
        )
    if matrix_id not in approval.get("scope", []):
        raise WorkflowError(f"matrix {matrix_id!r} is outside approval event scope")
    matrices = [item for item in design.get("calculation_matrix", []) if item.get("id") == matrix_id]
    if len(matrices) != 1:
        raise WorkflowError(f"expected one calculation matrix {matrix_id!r}, found {len(matrices)}")
    matrix = matrices[0]
    if stage not in matrix.get("stages", []):
        raise WorkflowError(f"stage {stage!r} is not approved for matrix {matrix_id!r}")
    envelopes = [
        item
        for item in design.get("engine_stage_envelopes", [])
        if item.get("matrix_id") == matrix_id and item.get("engine") == engine
    ]
    if len(envelopes) != 1:
        raise WorkflowError(
            f"expected one approved {engine!r} envelope for matrix {matrix_id!r}, found {len(envelopes)}"
        )
    envelope = envelopes[0]
    if not isinstance(envelope.get("engine_parameters"), dict) or not envelope["engine_parameters"]:
        raise WorkflowError("approved engine_parameters must contain exact input values")
    return approval, design, matrix, envelope, history


def _initial_approval(
    project_root: Path,
    composition: str,
    structure: str,
    history_path: str | Path | None,
    event_id: str | None,
    design_path: str | Path | None,
) -> tuple[dict[str, Any], dict[str, Any], Path, str]:
    """Load exactly one immutable approval for a full-tree initialization."""

    history = workspace_path(
        project_root,
        history_path or ((design_plan_root(project_root, composition, structure) if (project_root / PROJECT_FILE).exists()
                         else project_root / "plans" / composition / structure) / "history.jsonl"),
        "design history",
    )
    if history.name != "history.jsonl" or not history.is_file():
        raise WorkflowError(f"design approval must reference an existing history.jsonl: {history}")

    plan_root = (design_plan_root(history, composition, structure) if (project_root / PROJECT_FILE).exists()
                 else project_root / "plans" / composition / structure)
    expected_history = (plan_root / "history.jsonl").resolve()
    if history != expected_history:
        raise WorkflowError(
            "design plan scope does not match target composition/structure: "
            f"expected plans/{composition}/{structure}/"
        )

    verifier = _load_design_verifier()
    events = verifier.load_history(history)
    approvals = [
        event
        for event in events
        if event.get("event_type") == "scientific_design_approved"
    ]
    if event_id is None:
        if len(approvals) != 1:
            raise WorkflowError(
                "initialize requires --event-id when history does not contain exactly one "
                "scientific_design_approved event"
            )
        event_id = str(approvals[0].get("event_id", ""))
    if not event_id:
        raise WorkflowError("scientific design approval event_id must not be empty")

    try:
        approval, design = verifier.verify_approval(history, event_id)
    except Exception as exc:
        raise WorkflowError(f"scientific design approval verification failed: {exc}") from exc
    expected_design = (plan_root / "calculation_design.json").relative_to(project_root).as_posix()
    if approval.get("design_path") != expected_design:
        raise WorkflowError(
            "design plan scope does not match target composition/structure: "
            f"expected plans/{composition}/{structure}/"
        )

    if design_path is not None:
        current_path = workspace_path(project_root, design_path, "calculation design")
        if current_path.is_file():
            current = verifier.load_json(current_path)
            if verifier.canonical_json_sha256(current) != approval.get("design_sha256"):
                raise WorkflowError(
                    "current calculation design does not match the immutable approval snapshot"
                )
    return approval, design, history, event_id


def _parameter_baseline_hash(
    task: Mapping[str, Any], matrix: Mapping[str, Any], envelope: Mapping[str, Any]
) -> str:
    """Hash only stable scientific/task parameter semantics, not paths or timestamps."""

    semantic = {
        "task_slug": task.get("task_slug"),
        "matrix_id": task.get("matrix_id"),
        "stage": task.get("stage"),
        "engine": task.get("engine"),
        "matrix_variables": matrix.get("variables", {}),
        "matrix_fixed_parameters": matrix.get("fixed_parameters", {}),
        "engine_parameters": envelope.get("engine_parameters", {}),
        "parameter_selection": envelope.get("parameter_selection", {}),
    }
    return canonical_sha256(semantic)


def _profile_resource_record(
    profile_id: str, profile: Mapping[str, Any]
) -> dict[str, Any]:
    environment = profile.get("environment")
    return {
        "profile_id": profile_id,
        "engine": profile.get("engine"),
        "software": profile.get("software"),
        "partition": profile.get("partition"),
        "qos": profile.get("qos"),
        "account": profile.get("account"),
        "nodelist": profile.get("nodelist"),
        "gres": profile.get("gres"),
        "nodes": profile.get("nodes"),
        "ntasks": profile.get("ntasks", profile.get("nodes", 0) * profile.get("ntasks_per_node", 0)),
        "ntasks_per_node": profile.get("ntasks_per_node"),
        "cpus_per_task": profile.get("cpus_per_task"),
        "walltime": profile.get("walltime"),
        "environment": dict(environment) if isinstance(environment, Mapping) else environment,
        "modules": list(environment.get("modules", [])) if isinstance(environment, Mapping) else [],
        "pre_commands": list(profile.get("pre_commands", [])),
        "executable": profile.get("executable"),
    }


def _engine_required_inputs(engine: str) -> set[str] | None:
    if engine == "vasp":
        return {"POSCAR", "INCAR", "KPOINTS", "POTCAR"}
    if engine == "quantum-espresso":
        return None
    return set()


def _task_leaf_path(
    structure_root: Path, task: Mapping[str, Any]
) -> tuple[Path, str | None]:
    task_slug = task.get("task_slug")
    if not isinstance(task_slug, str) or not TASK_RE.fullmatch(task_slug):
        raise WorkflowError(f"task slug must use pN[_name] lowercase format: {task_slug!r}")
    directory = task.get("directory")
    if directory is not None:
        parts = Path(directory).parts if isinstance(directory, str) else ()
        if (not parts or Path(directory).is_absolute() or not STAGE_RE.fullmatch(parts[0])
                or any(not SLUG_RE.fullmatch(p) for p in parts)):
            raise WorkflowError("Task directory must be a safe numbered stage and optional nested groups")
        return structure_root.joinpath(*parts), None
    raw_variant = task.get("variant", task.get("variant_slug"))
    variant = None if raw_variant in (None, "") else _slug(str(raw_variant), "variant")
    return structure_root / task_slug / variant if variant else structure_root / task_slug, variant


def _managed_documents(
    composition: str,
    structure: str,
    tasks: Sequence[Mapping[str, Any]],
) -> dict[Path, str]:
    calculations = Path("calculations")
    composition_root = calculations / composition
    structure_root = composition_root / structure
    documents: dict[Path, str] = {
        calculations / "README.md": (
            "# Calculations\n\nRaw engine inputs and outputs organized by composition and structure."
        ),
        composition_root / "README.md": f"# {composition}\n\nComposition-level calculation case.",
        composition_root / "refs/README.md": (
            "# References\n\nShared structures, pseudopotentials, and method references."
        ),
        structure_root / "README.md": (
            f"# {structure}\n\nStructure calculation status and accepted lineage."
        ),
        structure_root / "scripts/README.md": (
            "# Local scripts\n\nSmall CLI helpers specific to this structure."
        ),
        structure_root / "analysis/README.md": (
            "# Analysis\n\nProcessed data, figures, and reports derived from task leaves."
        ),
        structure_root / "analysis/plot_data/README.md": (
            "# Plot data\n\nProcessed numeric data with source-task provenance."
        ),
        structure_root / "analysis/figures/README.md": (
            "# Figures\n\nFigures derived from recorded plot data."
        ),
        structure_root / "analysis/reports/README.md": (
            "# Reports\n\nHuman-readable analysis reports."
        ),
        structure_root / "failed/README.md": (
            "# Failed tasks\n\nConfirmed failed or rejected leaves with no approved recovery plan."
        ),
    }
    for task in tasks:
        leaf, variant = _task_leaf_path(structure_root, task)
        task_slug = str(task["task_slug"])
        if variant:
            documents[leaf.parent / "README.md"] = (
                f"# {task_slug}\n\nParameter-variant index for this task."
            )
        documents[leaf / "README.md"] = f"# {task_slug}{('/' + variant) if variant else ''}\n\nStatus: initializing"
    return documents


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _initialized_leaf_readme(
    *,
    task: Mapping[str, Any],
    status: str,
    profile_id: str,
    resources: Mapping[str, Any],
    materialization: str,
) -> str:
    if status == "planned":
        return (f"# {task['task_slug']}\n\nInitial state: `planned`. Current state: [workflow.json](workflow.json).\n\n"
                "At initialization, inputs were prepared for the first parameter review and not approved.\n"
                "Review current input parameters, then bind the real approval event without rebuilding.\n")
    dependency_note = (
        "等待上游产物后再进入确定性依赖门控。"
        if task.get("dependencies")
        else "可在资源缓存通过后进入提交流程。"
    )
    return (
        f"# {task['task_slug']}\n\n"
        f"- Initial state: `{status}`. Current state: [workflow.json](workflow.json).\n"
        f"- Stage: `{task['stage']}`\n"
        f"- Engine: `{task['engine']}`\n"
        f"- Approved matrix: `{task['matrix_id']}`\n"
        f"- Resource profile: `{profile_id}`\n"
        "- Environment details: selected private profile and local resource baseline.\n"
        f"- Input materialization: `{materialization}`\n"
        "- Scientific parameters: inherited from the one immutable design approval\n"
        "- Submission state and authority: read workflow.json before acting.\n"
        f"- Next action: {dependency_note}\n"
        f"- Last update: `{utc_now()}`\n"
    )


def initialize_workflow_tree(
    project_root: str | Path,
    composition: str,
    structure: str,
    *,
    history_path: str | Path | None = None,
    event_id: str | None = None,
    design_path: str | Path | None = None,
    resource_document: str | Path = Path("docs/project-resources.md"),
    resource_profile: str | None = None,
    draft: bool = False,
    route: str | None = None,
) -> list[Path]:
    """Initialize all known tasks, either unapproved drafts or an approved graph."""

    root = validate_project(project_root, require_calculations=False)
    from dft_contracts.layout import project_role
    if project_role(root) == "local":
        from paired_execution import prepare_workspace
        return prepare_workspace(root, composition, structure, history_path=history_path,
            event_id=event_id, design_path=design_path, resource_document=resource_document,
            resource_profile=resource_profile, draft=draft, route=route)
    if project_role(root) == "cluster":
        raise WorkflowError("Prepare through the local project and deploy an execution snapshot")
    _slug(composition, "composition")
    _slug(structure, "structure")
    selected = route_for(workspace_path(root, route, "route") if route else root, composition, structure) if (root / PROJECT_FILE).exists() else None
    route_mode = selected is not None
    calculations = root / "calculations"
    if calculations.exists() and not calculations.is_dir():
        raise WorkflowError(f"calculations path exists but is not a directory: {calculations}")
    structure_root = selected[0] if selected else calculations / composition / structure
    composition_root = structure_root.parent
    if structure_root.exists() and not route_mode:
        raise WorkflowError(
            f"managed target structure already exists; refusing to merge or overwrite: {structure_root}"
        )
    if composition_root.exists() and not composition_root.is_dir():
        raise WorkflowError(f"composition path exists but is not a directory: {composition_root}")

    verifier = _load_design_verifier()
    plan_root = design_plan_root(structure_root, composition, structure) if route_mode else root / "plans" / composition / structure
    if route_mode:
        history_path = history_path or (None if draft else plan_root / "history.jsonl")
        design_path = design_path or plan_root / "calculation_design.json"
    if draft:
        if history_path is not None or event_id is not None:
            raise WorkflowError("draft initialization does not consume an approval event")
        source_design = workspace_path(root, design_path or plan_root /
                                       "calculation_design.json", "draft design")
        expected_design = (plan_root / "calculation_design.json").resolve()
        if source_design != expected_design:
            raise WorkflowError("draft design plan scope does not match composition/structure")
        try:
            design = verifier.load_json(source_design)
            errors = verifier.validate_design(design)
        except Exception as exc:
            raise WorkflowError(f"invalid draft design: {exc}") from exc
        if errors:
            raise WorkflowError("invalid draft design: " + "; ".join(errors))
        # A draft has design intent, never a fabricated approval event.
        approval = None
        history = None
        resolved_event_id = None
        approval_scope = [item["id"] for item in design["calculation_matrix"]]
    else:
        approval, design, history, resolved_event_id = _initial_approval(
            root, composition, structure, history_path, event_id, design_path
        )
        approval_scope = approval.get("scope", [])
    if not isinstance(approval_scope, list):
        raise WorkflowError("scientific design approval scope must be a list")
    plan_errors = verifier.validate_execution_plan(
        design, required_matrix_ids=approval_scope
    )
    if plan_errors:
        raise WorkflowError("execution plan is invalid: " + "; ".join(plan_errors))
    execution_tasks = design["execution_plan"]["tasks"]
    targets = [_task_leaf_path(structure_root, task)[0] for task in execution_tasks]
    if len(set(targets)) != len(targets) or any(a in b.parents for a in targets for b in targets if a != b):
        raise WorkflowError("Executable task directories must not overlap")
    if route_mode and any(p.exists() for p in targets):
        raise WorkflowError("Task directory already exists; preserve it and reconcile or create an explicit rerun")
    scope = set(approval_scope)
    outside_scope = sorted(
        {
            str(task.get("matrix_id"))
            for task in execution_tasks
            if task.get("matrix_id") not in scope
        }
    )
    if outside_scope:
        raise WorkflowError(f"execution plan contains matrices outside approval scope: {outside_scope}")

    matrices = {
        item["id"]: item
        for item in design.get("calculation_matrix", [])
        if isinstance(item, Mapping)
        and isinstance(item.get("id"), str)
        and item.get("id", "").strip()
    }
    envelopes = {
        item["matrix_id"]: item
        for item in verifier.engine_envelopes(design)
        if isinstance(item, Mapping)
        and isinstance(item.get("matrix_id"), str)
        and item.get("matrix_id", "").strip()
    }
    profile_cache: dict[tuple[str, str, bool], tuple[dict[str, Any], dict[str, Any], Path]] = {}
    source_cache: dict[str, Path] = {}
    prepared: list[dict[str, Any]] = []

    for raw_task in execution_tasks:
        task = raw_task
        matrix_id = str(task["matrix_id"])
        stage = str(task["stage"])
        engine = str(task["engine"])
        matrix = matrices[matrix_id]
        envelope = envelopes[matrix_id]
        profile_id = resource_profile or envelope.get("resource_profile")
        if not isinstance(profile_id, str) or not profile_id:
            raise WorkflowError(f"task {task['task_slug']} has no approved resource profile")
        approved_profile_id = envelope.get("resource_profile")
        if profile_id != approved_profile_id:
            raise WorkflowError(
                f"resource profile {profile_id!r} does not match approved profile {approved_profile_id!r}"
            )
        profile_key = (profile_id, engine, bool(task.get("job_script")))
        if profile_key not in profile_cache:
            profile_cache[profile_key] = load_resource_profile(
                root, resource_document, profile_id, engine, supplied_script=bool(task.get("job_script"))
            )
        profile, resource_payload, resource_doc = profile_cache[profile_key]

        static_inputs: dict[str, Path] = {}
        recipe_inputs: dict[str, Mapping[str, Any]] = {}
        for raw_input in task["inputs"]:
            name = str(raw_input["name"])
            mode = raw_input["mode"]
            if mode == "static":
                source_ref = str(raw_input["source"])
                source = source_cache.get(source_ref)
                if source is None:
                    source = workspace_path(root, source_ref, "execution input source")
                    if not source.is_file():
                        raise WorkflowError(f"execution input source does not exist: {source}")
                    source_cache[source_ref] = source
                static_inputs[name] = source
            else:
                recipe_inputs[name] = raw_input

        required = _engine_required_inputs(engine)
        missing_declared = set() if required is None else required - set(static_inputs) - set(recipe_inputs)
        if missing_declared:
            raise WorkflowError(
                f"task {task['task_slug']} is missing declared engine inputs: {sorted(missing_declared)}"
            )

        static_complete = False
        primary_input = task.get("primary_input")
        if engine == "vasp":
            static_complete = required is not None and required.issubset(static_inputs)
        elif engine == "quantum-espresso":
            qe_inputs = sorted(name for name in static_inputs if name.lower().endswith(".in"))
            known_qe_inputs = sorted(name for name in (*static_inputs, *recipe_inputs) if name.lower().endswith(".in"))
            if primary_input is None and known_qe_inputs:
                primary_input = known_qe_inputs[0]
            static_complete = bool(qe_inputs and isinstance(primary_input, str) and primary_input in static_inputs)
        else:
            static_complete = bool(static_inputs)

        job_script: str | None = None
        script_name = {"vasp": "vasp.sh", "quantum-espresso": "qe.sh"}.get(engine, "job.sh") if design.get("design_mode") == "task" else "job.sh"
        rendered_resources = _profile_resource_record(profile_id, profile)
        if static_complete:
            validate_engine_inputs(
                engine,
                static_inputs,
                envelope.get("engine_parameters", {}),
                primary_input if isinstance(primary_input, str) else None,
            )
        if task.get("job_script"):
            script_source = workspace_path(root, task["job_script"], "dft-submit script template")
            if not script_source.is_file():
                raise WorkflowError(f"missing submission template: {script_source}")
            script_name = script_source.name
            if script_name in {"workflow.json", "README.md"} or script_name in static_inputs or script_name in recipe_inputs:
                raise WorkflowError("submission template filename collides with an input or ledger")
            job_script = script_source.read_text(encoding="utf-8")
        elif static_complete or draft or design.get("design_mode") == "task":
            job_script, rendered_resources = render_job_script(
                profile_id,
                profile,
                job_name="-".join(
                    part for part in (composition, structure, str(task["task_slug"]), task.get("variant")) if part
                ),
                primary_input=primary_input if isinstance(primary_input, str) else None,
            )

        if script_name in static_inputs or script_name in recipe_inputs:
            raise WorkflowError("submission script collides with a declared input")
        status = "planned" if draft else ("awaiting_upstream" if task["dependencies"] else "prepared")
        materialization = (
            "mixed"
            if static_inputs and recipe_inputs
            else "static"
            if static_inputs
            else "recipe"
        )
        approval_ref = None if draft else f"workspace_root:{relative_ref(root, history)}#{resolved_event_id}"
        input_files: list[dict[str, Any]] = []
        input_authority: dict[str, str] = {}
        for raw_input in task["inputs"]:
            name = str(raw_input["name"])
            reference: dict[str, Any] = {
                "base": "task_root",
                "path": name,
                "name": name,
                "role": "engine_input",
                "mode": raw_input["mode"],
                "authority": "generated",
            }
            input_authority[name] = "generated"
            if raw_input["mode"] == "static":
                reference.update(
                    {
                        "source": f"workspace_root:{relative_ref(root, static_inputs[name])}",
                        "sha256": sha256_file(static_inputs[name]),
                    }
                )
            else:
                reference.update(
                    {
                        "source_task": raw_input["source_task"],
                        "artifact": raw_input["artifact"],
                    }
                )
            input_files.append(reference)

        dependency_records = [
            {
                "task_ref": dependency,
                "required_artifacts": sorted(
                    {
                        str(recipe["artifact"])
                        for recipe in recipe_inputs.values()
                        if recipe.get("source_task") == dependency
                    }
                ),
                "gate_status": "awaiting_upstream",
            }
            for dependency in task["dependencies"]
        ]
        workflow: dict[str, Any] = {
            "schema_version": 2,
            "contract": "dft.workflow.v2",
            "task_uuid": str(uuid4()),
            "composition_slug": composition,
            "structure_slug": structure,
            "task_slug": task["task_slug"],
            "status": status,
            "engine": engine,
            "updated_at": utc_now(),
            "stage": stage,
            "engine_backend": "canonical_workflow",
            "design": {
                "path": (plan_root / "calculation_design.json").relative_to(root).as_posix(),
                "design_id": design["design_id"],
                "revision": design["revision"],
                "approval_ref": approval_ref,
                "baseline_parameter_hash": _parameter_baseline_hash(task, matrix, envelope),
                "design_sha256": verifier.canonical_json_sha256(design),
                "draft": draft,
                "matrix_id": matrix_id,
                "matrix_class": matrix.get("class"),
                "engine_parameters": envelope.get("engine_parameters", {}),
                "completion_gate": envelope.get("completion_gates", {}).get(stage),
            },
            "inputs": {"materialization": materialization, "files": input_files},
            "input_authority": input_authority,
            "dependencies": dependency_records,
            "parameter_reconciliation": {
                "status": "synchronized",
                "changed_parameters": [],
                "affected_tasks": [],
            },
            "resource_profile": {
                "ref": f"workspace_root:{relative_ref(root, resource_doc)}#{profile_id}",
                "overrides": {},
            },
            "resources": {
                "document": f"workspace_root:{relative_ref(root, resource_doc)}",
                "document_sha256": sha256_file(resource_doc),
                "cluster": resource_payload.get("cluster"),
                "scheduler": resource_payload.get("scheduler"),
                **rendered_resources,
            },
            "attempts": [],
            "submission": {
                "state": "not_submitted",
                "allowed": False,
                "job_id": None,
                "blockers": ["upstream dependency gate"] if task["dependencies"] else [],
            },
            "completion": {
                "scheduler_complete": False,
                "artifact_complete": False,
                "scientifically_accepted": False,
            },
            "lineage": {"derived_from": None, "supersedes": None},
            "result": {"status": "not_started", "summary": None},
            "history": [
                {
                    "at": utc_now(),
                    "status": status,
                    "note": "prepared for parameter review" if draft else "initialized from the one immutable scientific design approval",
                }
            ],
        }
        if job_script is not None:
            workflow["job"] = {
                "script": f"task_root:{script_name}",
                "sha256": canonical_sha256(job_script),
                "encoding": "utf-8",
                "line_endings": "lf",
            }
        if task.get("variant", task.get("variant_slug")) not in (None, ""):
            workflow["variant_slug"] = task.get("variant", task.get("variant_slug"))
        contract_errors = validate_document("workflow-v2", workflow)
        if contract_errors:
            raise WorkflowError(
                f"generated workflow for {task['task_slug']} is invalid: "
                + "; ".join(contract_errors)
            )
        prepared.append(
            {
                "task": task,
                "workflow": workflow,
                "static_inputs": static_inputs,
                "job_script": job_script,
                "script_name": script_name,
                "profile_id": profile_id,
                "resources": rendered_resources,
                "materialization": materialization,
                "primary_input": primary_input if isinstance(primary_input, str) else None,
            }
        )

    staging_root: Path | None = None
    try:
        staging_root = Path(tempfile.mkdtemp(prefix=".dft-workflow-init-", dir=str(root)))
        staged_structure = staging_root / "structure"
        structure_prefix = Path("calculations") / composition / structure
        for relative_path, content in _managed_documents(
            composition, structure, [item["task"] for item in prepared]
        ).items():
            try:
                structure_relative = relative_path.relative_to(structure_prefix)
            except ValueError:
                continue
            if route_mode:
                continue  # Three-role README renderer owns registered-route navigation.
            _atomic_write_text(staged_structure / structure_relative, content.rstrip() + "\n")

        staged_leaf_paths: list[Path] = []
        for item in prepared:
            task = item["task"]
            raw_leaf, _ = _task_leaf_path(staged_structure, task)
            raw_leaf.mkdir(parents=True, exist_ok=True)
            for name, source in item["static_inputs"].items():
                destination = raw_leaf / name
                if destination.exists():
                    raise WorkflowError(f"input destination already exists; refusing to overwrite: {destination}")
                shutil.copy2(source, destination)
            job_script = item["job_script"]
            if job_script is not None:
                _atomic_write_text(raw_leaf / item["script_name"], job_script)
                try:
                    (raw_leaf / item["script_name"]).chmod(0o755)
                except OSError:
                    pass
            workflow = item["workflow"]
            for reference in workflow["inputs"]["files"]:
                if reference["mode"] == "static":
                    materialized = raw_leaf / reference["name"]
                    reference["sha256"] = sha256_file(materialized)
            if item["job_script"] is not None:
                workflow["job"]["sha256"] = sha256_file(raw_leaf / item["script_name"])
            if item["primary_input"]:
                workflow["primary_input"] = item["primary_input"]
            current_snapshot = parse_current_inputs(
                str(task["engine"]),
                raw_leaf,
                primary_input=snapshot_primary_input(raw_leaf, workflow),
            )
            workflow["input_snapshot"] = current_snapshot
            workflow["design"]["baseline_parameter_hash"] = current_snapshot["parameter_hash"]
            _atomic_write_text(
                raw_leaf / "workflow.json",
                json.dumps(workflow, ensure_ascii=False, indent=2) + "\n",
            )
            readme = _initialized_leaf_readme(
                task=task,
                status=workflow["status"],
                profile_id=item["profile_id"],
                resources=item["resources"],
                materialization=item["materialization"],
            )
            if not route_mode or len(raw_leaf.relative_to(staged_structure).parts) == 1:
                _atomic_write_text(raw_leaf / "README.md", readme)
            staged_leaf_paths.append(raw_leaf)

        # Revalidate the final serialized records after materialized-file hashes are added.
        for leaf in staged_leaf_paths:
            workflow = json.loads((leaf / "workflow.json").read_text(encoding="utf-8"))
            if validate_document("workflow-v2", workflow):
                raise WorkflowError(f"generated workflow failed final validation: {leaf}")

        if route_mode:
            # Stage all leaves before merging only the declared new tasks into an existing route.
            from dft_contracts.project import explain_directories, _lock
            committed = []
            with _lock(root):
                if any(p.exists() for p in targets):
                    raise WorkflowError("Task appeared during initialization; refusing to overwrite")
                try:
                    for item, target in zip(prepared, targets):
                        staged, _ = _task_leaf_path(staged_structure, item["task"])
                        target.parent.mkdir(parents=True, exist_ok=True)
                        os.rename(staged, target)
                        committed.append(target)
                    for target in targets:
                        explain_directories(root, target)
                except Exception:
                    for target in reversed(committed):
                        staged, _ = _task_leaf_path(staged_structure, prepared[targets.index(target)]["task"])
                        staged.parent.mkdir(parents=True, exist_ok=True)
                        os.rename(target, staged)
                    raise
            from dft_contracts.readmes import after_operation
            after_operation(structure_root)
            return targets
        init_project(root, "legacy")
        calculations.mkdir(parents=True, exist_ok=True)
        _write_if_missing(
            calculations / "README.md",
            "# Calculations\n\nRaw engine inputs and outputs organized by composition and structure.",
        )
        if composition_root.exists() and not composition_root.is_dir():
            raise WorkflowError(
                f"composition path appeared as a non-directory during initialization: {composition_root}"
            )
        if structure_root.exists():
            raise WorkflowError(
                f"managed target structure appeared during initialization; refusing to overwrite: {structure_root}"
            )
        composition_root.mkdir(parents=True, exist_ok=True)
        _write_if_missing(
            composition_root / "README.md",
            f"# {composition}\n\nComposition-level calculation case.",
        )
        _write_if_missing(
            composition_root / "refs/README.md",
            "# References\n\nShared structures, pseudopotentials, and method references.",
        )
        structure_root.parent.mkdir(parents=True, exist_ok=True)
        os.replace(staged_structure, structure_root)
        result: list[Path] = []
        for item in prepared:
            task = item["task"]
            task_path, _ = _task_leaf_path(
                root / "calculations" / composition / structure, task
            )
            result.append(task_path)
        return result
    finally:
        if staging_root is not None and staging_root.exists():
            shutil.rmtree(staging_root, ignore_errors=True)


def _resource_payload(text: str) -> dict[str, Any]:
    if text.count(RESOURCE_START) != 1 or text.count(RESOURCE_END) != 1:
        raise WorkflowError(
            "project resource document must contain exactly one dft-workflow profiles block"
        )
    body = text.split(RESOURCE_START, 1)[1].split(RESOURCE_END, 1)[0].strip()
    match = re.fullmatch(r"```json\s*(\{.*\})\s*```", body, flags=re.DOTALL)
    if not match:
        raise WorkflowError("resource profiles block must contain one fenced JSON object")
    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise WorkflowError(f"invalid resource profile JSON: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("schema") != "dft.project-resources.v1":
        raise WorkflowError("resource profile schema must be dft.project-resources.v1")
    if payload.get("scheduler") != "slurm":
        raise WorkflowError("canonical job preparation currently requires scheduler=slurm")
    if not isinstance(payload.get("profiles"), dict):
        raise WorkflowError("resource profile payload requires a profiles object")
    return payload


def bind_approval(project_root, composition, structure, *, history_path=None, event_id=None, route=None):
    from dft_contracts.layout import project_role
    if project_role(Path(project_root)) == "local":
        from paired_execution import bind_workspace
        return bind_workspace(project_root, composition, structure, history_path=history_path, event_id=event_id, route=route)
    from approval_binding import bind_approval as bind
    return bind(project_root, composition, structure, history_path=history_path, event_id=event_id, route=route)


def _single_line(value: Any, label: str, *, optional: bool = False) -> str | None:
    if value in (None, "") and optional:
        return None
    if not isinstance(value, str) or not value.strip() or "\n" in value or "\r" in value:
        raise WorkflowError(f"resource profile {label} must be a non-empty single line")
    return value.strip()


def _positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise WorkflowError(f"resource profile {label} must be a positive integer")
    return value


def _string_list(value: Any, label: str, *, allow_empty: bool = True) -> list[str]:
    if not isinstance(value, list) or (not allow_empty and not value):
        suffix = "non-empty " if not allow_empty else ""
        raise WorkflowError(f"resource profile {label} must be a {suffix}list")
    result: list[str] = []
    for index, item in enumerate(value):
        result.append(str(_single_line(item, f"{label}[{index}]")))
    return result


def _reviewed_source_command(value: Any, label: str) -> str:
    command = str(_single_line(value, label))
    if (
        not re.match(r"^(?:source|\.)\s+\S+", command)
        or re.search(r"[;&|`<>]|\$\(", command)
    ):
        raise WorkflowError(
            f"resource profile {label} must explicitly source one reviewed script"
        )
    return command


def _module_identifiers(value: Any) -> list[str]:
    modules = _string_list(value, "environment.modules", allow_empty=False)
    for module in modules:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.+/@:-]*", module):
            raise WorkflowError(
                f"resource profile module identifier is unsafe: {module!r}"
            )
    return modules


def _executable_verification(value: Any, executable: str) -> str:
    command = str(_single_line(value, "environment.verify_command"))
    expected = f"command -v {executable}"
    if command != expected:
        raise WorkflowError(
            "resource profile environment.verify_command must resolve the "
            f"approved executable with exactly: {expected}"
        )
    return command


def normalize_environment(profile: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a typed activation method, adapting old module-only profiles."""

    raw = profile.get("environment")
    executable = str(profile.get("executable") or "")
    if raw is None:
        modules = _module_identifiers(profile.get("modules", []))
        return {
            "method": "modules",
            "module_init": None,
            "purge": False,
            "modules": modules,
            "availability_probe": None,
            "verify_command": f"command -v {executable}",
            "documentation_url": None,
            "legacy_shape": True,
        }
    if not isinstance(raw, dict):
        raise WorkflowError("resource profile environment must be an object")
    if raw.get("legacy_shape") is True:
        return dict(raw)
    method = raw.get("method")
    if method == "modules":
        raw_module_init = raw.get("module_init")
        module_init = (
            _reviewed_source_command(raw_module_init, "environment.module_init")
            if raw_module_init not in (None, "")
            else None
        )
        purge = raw.get("purge", False)
        if not isinstance(purge, bool):
            raise WorkflowError("resource profile environment.purge must be boolean")
        modules = _module_identifiers(raw.get("modules"))
        availability_probe = _single_line(
            raw.get("availability_probe"), "environment.availability_probe"
        )
        verify_command = _executable_verification(
            raw.get("verify_command"), executable
        )
        return {
            "method": "modules",
            "module_init": module_init,
            "purge": purge,
            "modules": modules,
            "availability_probe": availability_probe,
            "verify_command": verify_command,
            "documentation_url": _single_line(
                raw.get("documentation_url"),
                "environment.documentation_url",
                optional=True,
            ),
            "legacy_shape": False,
        }
    if method == "source-script":
        source_command = _reviewed_source_command(
            raw.get("source_command"), "environment.source_command"
        )
        return {
            "method": "source-script",
            "availability_probe": _single_line(
                raw.get("availability_probe"), "environment.availability_probe"
            ),
            "source_command": source_command,
            "verify_command": _executable_verification(
                raw.get("verify_command"), executable
            ),
            "documentation_url": _single_line(
                raw.get("documentation_url"),
                "environment.documentation_url",
            ),
            "legacy_shape": False,
        }
    raise WorkflowError(
        "resource profile environment.method must be 'modules' or 'source-script'"
    )


def load_resource_profile(
    project_root: str | Path,
    resource_document: str | Path,
    profile_id: str,
    engine: str,
    *, supplied_script: bool = False,
) -> tuple[dict[str, Any], dict[str, Any], Path]:
    root = validate_project(project_root)
    document = workspace_path(root, resource_document, "project resource document")
    if not document.is_file():
        raise WorkflowError(f"project resource document does not exist: {document}")
    payload = _resource_payload(document.read_text(encoding="utf-8"))
    profile = payload["profiles"].get(profile_id)
    if not isinstance(profile, dict):
        raise WorkflowError(f"resource profile is missing: {profile_id}")
    if profile.get("status") != "approved":
        raise WorkflowError(f"resource profile is not approved: {profile_id}")
    if profile.get("engine") != engine:
        raise WorkflowError(
            f"resource profile engine {profile.get('engine')!r} does not match approved engine {engine!r}"
        )
    _single_line(profile.get("software"), "software")
    _single_line(profile.get("partition"), "partition")
    _single_line(profile.get("executable"), "executable")
    if not supplied_script:
        _single_line(profile.get("launch_template"), "launch_template")
    for field in ("nodes", "ntasks_per_node", "cpus_per_task"):
        if not supplied_script or field in profile:
            _positive_int(profile.get(field), field)
    for field in ("qos", "account", "nodelist", "gres", "walltime"):
        _single_line(profile.get(field), field, optional=True)
    environment = normalize_environment(profile)
    _string_list(profile.get("pre_commands", []), "pre_commands")
    if "ntasks" in profile:
        _positive_int(profile["ntasks"], "ntasks")
    normalized = dict(profile)
    normalized["environment"] = environment
    return normalized, payload, document


def _strip_comment(line: str, markers: str) -> str:
    positions = [line.find(marker) for marker in markers if marker in line]
    return line[: min(positions)] if positions else line


def parse_vasp_incar(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = _strip_comment(raw_line, "#!")
        for statement in line.split(";"):
            if "=" not in statement:
                continue
            key, value = statement.split("=", 1)
            key = key.strip().upper()
            if key:
                values[key] = value.strip()
    return values


def parse_vasp_kpoints(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) < 4:
        raise WorkflowError("KPOINTS is too short to identify the approved mesh")
    numbers = re.findall(r"[0-9]+", lines[3])
    if len(numbers) < 3:
        raise WorkflowError("KPOINTS automatic mesh is not parseable")
    return "x".join(numbers[:3])


def parse_qe_parameters(texts: Sequence[str]) -> tuple[dict[str, str], str | None]:
    values: dict[str, str] = {}
    mesh: str | None = None
    for text in texts:
        lines = text.splitlines()
        for index, raw_line in enumerate(lines):
            line = _strip_comment(raw_line, "!").strip()
            if re.match(r"K_POINTS\s+automatic", line, flags=re.IGNORECASE):
                if index + 1 < len(lines):
                    numbers = re.findall(r"[0-9]+", _strip_comment(lines[index + 1], "!"))
                    if len(numbers) >= 3:
                        mesh = "x".join(numbers[:3])
            for match in re.finditer(
                r"\b([A-Za-z][A-Za-z0-9_]*)\s*=\s*([^,\n/]+)", line
            ):
                values[match.group(1).lower()] = match.group(2).strip()
    return values, mesh


def _normal_value(value: Any) -> Any:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if not isinstance(value, str):
        return value
    text = value.strip().strip("'\"")
    lowered = text.lower()
    if lowered in {".true.", "true", "t"}:
        return True
    if lowered in {".false.", "false", "f"}:
        return False
    try:
        return float(re.sub(r"[dD]", "e", text))
    except ValueError:
        return re.sub(r"\s+", " ", text).lower()


def _same_value(actual: Any, approved: Any) -> bool:
    left = _normal_value(actual)
    right = _normal_value(approved)
    if isinstance(left, float) and isinstance(right, float):
        return math.isclose(left, right, rel_tol=1e-10, abs_tol=1e-12)
    return left == right


def validate_engine_inputs(
    engine: str,
    staged_inputs: Mapping[str, Path],
    engine_parameters: Mapping[str, Any],
    primary_input: str | None,
) -> None:
    if engine == "vasp":
        required = {"POSCAR", "INCAR", "KPOINTS", "POTCAR"}
        missing = sorted(required - set(staged_inputs))
        if missing:
            raise WorkflowError(f"VASP staged inputs are missing: {missing}")
        incar = parse_vasp_incar(staged_inputs["INCAR"].read_text(encoding="utf-8"))
        kmesh = parse_vasp_kpoints(staged_inputs["KPOINTS"].read_text(encoding="utf-8"))
        for key, approved in engine_parameters.items():
            if not isinstance(key, str) or isinstance(approved, (dict, list)):
                raise WorkflowError(f"VASP engine parameter {key!r} must be a scalar")
            if key.upper() == "KPOINTS":
                actual = kmesh
            else:
                if key.upper() not in incar:
                    raise WorkflowError(f"approved VASP parameter {key} is missing from INCAR")
                actual = incar[key.upper()]
            if not _same_value(actual, approved):
                raise WorkflowError(
                    f"approved VASP parameter {key}={approved!r} disagrees with staged input value {actual!r}"
                )
        return
    if engine == "quantum-espresso":
        input_names = [name for name in staged_inputs if name.lower().endswith(".in")]
        if not input_names:
            raise WorkflowError("Quantum ESPRESSO preparation requires at least one staged .in file")
        if primary_input is None or primary_input not in staged_inputs:
            raise WorkflowError("Quantum ESPRESSO preparation requires a staged primary_input")
        texts = [staged_inputs[name].read_text(encoding="utf-8") for name in input_names]
        values, kmesh = parse_qe_parameters(texts)
        for key, approved in engine_parameters.items():
            if not isinstance(key, str) or isinstance(approved, (dict, list)):
                raise WorkflowError(f"QE engine parameter {key!r} must be a scalar")
            if key.upper() == "KPOINTS":
                actual = kmesh
            else:
                lookup = key.lower()
                if lookup not in values:
                    raise WorkflowError(f"approved QE parameter {key} is missing from staged input")
                actual = values[lookup]
            if actual is None or not _same_value(actual, approved):
                raise WorkflowError(
                    f"approved QE parameter {key}={approved!r} disagrees with staged input value {actual!r}"
                )
        return
    raise WorkflowError(f"canonical input preparation is not implemented for engine {engine!r}")


def _safe_input_map(
    project_root: Path, values: Mapping[str, str | Path], label: str
) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for name, raw_path in values.items():
        if not isinstance(name, str) or Path(name).name != name or name in {"", ".", ".."}:
            raise WorkflowError(f"{label} name must be one safe leaf filename: {name!r}")
        if name in {"README.md", "workflow.json", "job.sh"} or name in FORBIDDEN_MACHINE_FILES:
            raise WorkflowError(f"{label} name is reserved: {name}")
        source = workspace_path(project_root, raw_path, f"{label} source")
        if not source.is_file():
            raise WorkflowError(f"{label} source does not exist: {source}")
        result[name] = source
    return result


def render_job_script(
    profile_id: str,
    profile: Mapping[str, Any],
    *,
    job_name: str,
    primary_input: str | None,
) -> tuple[str, dict[str, Any]]:
    nodes = int(profile["nodes"])
    ntasks_per_node = int(profile["ntasks_per_node"])
    ntasks = int(profile.get("ntasks", nodes * ntasks_per_node))
    cpus_per_task = int(profile["cpus_per_task"])
    values = {
        "executable": profile["executable"],
        "primary_input": primary_input or "",
        "primary_stem": Path(primary_input).stem if primary_input else "",
    }
    try:
        launch = str(profile["launch_template"]).format(**values)
    except (KeyError, ValueError) as exc:
        raise WorkflowError(f"invalid launch_template in profile {profile_id}: {exc}") from exc
    if str(profile["executable"]) not in launch:
        raise WorkflowError("rendered launch command does not contain the approved executable")
    if "\n" in launch or "\r" in launch:
        raise WorkflowError("rendered launch command must be one line")
    directives = [
        "#!/usr/bin/env bash",
        f"#SBATCH --job-name={job_name[:128]}",
        f"#SBATCH --partition={profile['partition']}",
        f"#SBATCH --nodes={nodes}",
        f"#SBATCH --ntasks={ntasks}",
        f"#SBATCH --ntasks-per-node={ntasks_per_node}",
        "#SBATCH --output=slurm-%j.out",
        "#SBATCH --error=slurm-%j.err",
    ]
    for field, flag in (
        ("qos", "--qos"),
        ("account", "--account"),
        ("nodelist", "--nodelist"),
        ("gres", "--gres"),
    ):
        if profile.get(field) not in (None, ""):
            directives.append(f"#SBATCH {flag}={profile[field]}")
    if cpus_per_task > 1:
        directives.append(f"#SBATCH --cpus-per-task={cpus_per_task}")
    lines = directives + [""]
    environment = normalize_environment(profile)
    if environment["method"] == "modules":
        if environment.get("module_init"):
            lines.append(str(environment["module_init"]))
        if environment.get("purge"):
            lines.append("module purge")
        lines.extend(f"module load {module}" for module in environment["modules"])
    else:
        lines.append(str(environment["source_command"]))
    # Approved runtime tuning belongs in the job; probe/check commands do not.
    lines.extend(str(command) for command in profile.get("pre_commands", []))
    lines.append("")
    lines.append(launch)
    script = "\n".join(lines).rstrip() + "\n"
    resources = {
        "profile_id": profile_id,
        "engine": profile["engine"],
        "software": profile["software"],
        "partition": profile["partition"],
        "qos": profile.get("qos"),
        "account": profile.get("account"),
        "nodelist": profile.get("nodelist"),
        "gres": profile.get("gres"),
        "nodes": nodes,
        "ntasks": ntasks,
        "ntasks_per_node": ntasks_per_node,
        "cpus_per_task": cpus_per_task,
        "walltime": profile.get("walltime"),
        "environment": environment,
        "modules": list(environment.get("modules", [])),
        "pre_commands": list(profile.get("pre_commands", [])),
        "executable": profile["executable"],
        "launch_command": launch,
    }
    return script, resources


def _write_if_missing(path: Path, text: str) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text.rstrip() + "\n")


def ensure_tree(
    project_root: Path, composition: str, structure: str, task: str, variant: str | None
) -> Path:
    calculations = project_root / "calculations"
    composition_root = calculations / composition
    structure_root = composition_root / structure
    task_root = structure_root / task
    leaf = task_root / variant if variant else task_root
    documents = {
        calculations / "README.md": "# Calculations\n\nRaw engine inputs and outputs organized by composition and structure.",
        composition_root / "README.md": f"# {composition}\n\nComposition-level calculation case.",
        composition_root / "refs/README.md": "# References\n\nShared structures, pseudopotentials, and method references.",
        structure_root / "README.md": f"# {structure}\n\nStructure calculation status and accepted lineage.",
        structure_root / "scripts/README.md": "# Local scripts\n\nSmall CLI helpers specific to this structure.",
        structure_root / "analysis/README.md": "# Analysis\n\nProcessed data, figures, and reports derived from task leaves.",
        structure_root / "analysis/plot_data/README.md": "# Plot data\n\nProcessed numeric data with source-task provenance.",
        structure_root / "analysis/figures/README.md": "# Figures\n\nFigures derived from recorded plot data.",
        structure_root / "analysis/reports/README.md": "# Reports\n\nHuman-readable analysis reports.",
        structure_root / "failed/README.md": "# Failed tasks\n\nConfirmed failed or rejected leaves with no approved recovery plan.",
    }
    if variant:
        documents[task_root / "README.md"] = f"# {task}\n\nParameter-variant index for this task."
        documents[leaf / "README.md"] = f"# {task}/{variant}\n\nStatus: planned"
    else:
        documents[leaf / "README.md"] = f"# {task}\n\nStatus: planned"
    for path, content in documents.items():
        _write_if_missing(path, content)
    return leaf


def _leaf_readme(
    *,
    task: str,
    variant: str | None,
    stage: str,
    engine: str,
    matrix_id: str,
    profile_id: str,
    resources: Mapping[str, Any],
    parameters: Mapping[str, Any],
) -> str:
    title = f"{task}/{variant}" if variant else task
    return (
        f"# {title}\n\n"
        "- Status: `prepared`\n"
        f"- Stage: `{stage}`\n"
        f"- Engine: `{engine}`\n"
        f"- Approved matrix: `{matrix_id}`\n"
        f"- Resource profile: `{profile_id}`\n"
        f"- Resources: `{resources['partition']}`, {resources['nodes']} node(s), "
        f"{resources['ntasks']} task(s), `{resources['software']}`\n"
        f"- Exact engine parameters: `{json.dumps(parameters, ensure_ascii=False, sort_keys=True)}`\n"
        "- Submission: blocked until targeted live resource checks, exact submit review, and explicit user approval\n"
        "- Results: none\n"
        "- Evidence level: prepared inputs only\n"
        "- Next action: run targeted live checks and review all inputs/resources\n"
        f"- Last update: `{utc_now()}`\n"
    )


def prepare_task(
    *,
    project_root: str | Path,
    composition: str,
    structure: str,
    task: str,
    variant: str | None,
    stage: str,
    engine: str,
    history_path: str | Path,
    event_id: str,
    matrix_id: str,
    resource_document: str | Path,
    resource_profile: str | None,
    staged_inputs: Mapping[str, str | Path],
    dependencies: Mapping[str, str | Path],
    primary_input: str | None,
) -> Path:
    root = validate_project(project_root)
    leaf = resolve_leaf(root, composition, structure, task, variant)
    if (leaf / "workflow.json").exists():
        raise WorkflowError(f"managed task leaf already exists; refusing to overwrite: {leaf}")
    approval, design, matrix, envelope, history = verify_design_approval(
        root, history_path, event_id, matrix_id, stage, engine, composition, structure
    )
    approved_profile = envelope.get("resource_profile")
    selected_profile = resource_profile or approved_profile
    if selected_profile != approved_profile:
        raise WorkflowError(
            f"resource profile {selected_profile!r} does not match approved profile {approved_profile!r}"
        )
    if not isinstance(selected_profile, str) or not selected_profile:
        raise WorkflowError("approved design does not select a resource profile")
    profile, resource_payload, resource_doc = load_resource_profile(
        root, resource_document, selected_profile, engine
    )
    sources = _safe_input_map(root, staged_inputs, "staged input")
    dependency_sources = _safe_input_map(root, dependencies, "dependency")
    overlap = sorted(set(sources) & set(dependency_sources))
    if overlap:
        raise WorkflowError(f"names cannot be both staged inputs and dependencies: {overlap}")
    validate_engine_inputs(engine, sources, envelope["engine_parameters"], primary_input)
    job_name = "-".join(part for part in (composition, structure, task, variant) if part)
    job_script, resources = render_job_script(
        selected_profile, profile, job_name=job_name, primary_input=primary_input
    )

    # All scientific and resource gates above run before the first task-tree write.
    leaf = ensure_tree(root, composition, structure, task, variant)
    for destination_name, source in sources.items():
        destination = leaf / destination_name
        if destination.exists():
            raise WorkflowError(f"input destination already exists; refusing to overwrite: {destination}")
        shutil.copy2(source, destination)
    job_path = leaf / "job.sh"
    if job_path.exists():
        raise WorkflowError(f"job script already exists; refusing to overwrite: {job_path}")
    with job_path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(job_script)
    try:
        job_path.chmod(0o755)
    except OSError:
        pass

    input_records = [
        {
            "base": "task_root",
            "path": name,
            "sha256": sha256_file(leaf / name),
            "role": "engine_input",
        }
        for name, source in sorted(sources.items())
    ]
    input_records.extend(
        {
            "base": "workspace_root",
            "path": relative_ref(root, source),
            "sha256": sha256_file(source),
            "role": f"dependency:{name}",
        }
        for name, source in sorted(dependency_sources.items())
    )
    input_sources = {
        name: f"workspace_root:{relative_ref(root, source)}"
        for name, source in sorted(sources.items())
    }
    prepared_at = utc_now()
    workflow = {
        "schema_version": 1,
        "contract": "dft.workflow.v1",
        "composition_slug": composition,
        "structure_slug": structure,
        "task_slug": task,
        "status": "prepared",
        "updated_at": prepared_at,
        "stage": stage,
        "engine": engine,
        "engine_backend": "canonical_workflow",
        "design": {
            "approval_ref": f"workspace_root:{relative_ref(root, history)}#{event_id}",
            "event_id": event_id,
            "design_id": approval["design_id"],
            "revision": approval["revision"],
            "design_sha256": approval["design_sha256"],
            "matrix_id": matrix_id,
            "matrix_class": matrix.get("class"),
            "engine_parameters": envelope["engine_parameters"],
            "completion_gate": envelope.get("completion_gates", {}).get(stage),
        },
        "inputs": input_records,
        "input_sources": input_sources,
        "resources": {
            "document": f"workspace_root:{relative_ref(root, resource_doc)}",
            "document_sha256": sha256_file(resource_doc),
            "cluster": resource_payload.get("cluster"),
            "scheduler": resource_payload.get("scheduler"),
            **resources,
        },
        "resource_preflight": {
            "baseline": "verified_for_job_render",
            "targeted_live_check": "required_before_submit",
            "checked_at": None,
            "status": "pending",
        },
        "job": {
            "script": "task_root:job.sh",
            "sha256": sha256_file(job_path),
            "encoding": "utf-8",
            "line_endings": "lf",
        },
        "submission": {
            "state": "not_approved",
            "allowed": False,
            "review_digest": None,
            "approved_at": None,
            "job_id": None,
            "blockers": [
                "targeted live resource drift check",
                "complete exact input/resource submit review",
                "explicit user submission approval",
            ],
        },
        "result": {"status": "not_started", "summary": None},
        "history": [
            {
                "at": prepared_at,
                "status": "prepared",
                "note": "verified design approval, staged exact inputs, and rendered job.sh",
            }
        ],
    }
    if variant is not None:
        workflow["variant_slug"] = variant
    with (leaf / "workflow.json").open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(workflow, ensure_ascii=False, indent=2) + "\n")
    with (leaf / "README.md").open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(
            _leaf_readme(
                task=task,
                variant=variant,
                stage=stage,
                engine=engine,
                matrix_id=matrix_id,
                profile_id=selected_profile,
                resources=resources,
                parameters=envelope["engine_parameters"],
            )
        )
    return leaf


def _mapping(values: Sequence[str], label: str) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for value in values:
        if "=" not in value:
            raise WorkflowError(f"{label} must use NAME=PATH: {value!r}")
        name, path = value.split("=", 1)
        if name in result:
            raise WorkflowError(f"duplicate {label} name: {name}")
        result[name] = Path(path)
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="canonical_workflow.py",
        description="Prepare and submit canonical DFT workflow-v2 task leaves.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    init_tree = sub.add_parser("init-tree")
    init_tree.add_argument("--project-root", type=Path, required=True)
    initialize = sub.add_parser(
        "initialize",
        help="Initialize a complete task graph; --draft prepares it before parameter review.",
    )
    initialize.add_argument("--project-root", type=Path, required=True)
    initialize.add_argument("--composition", "--composition-slug", dest="composition", required=True)
    initialize.add_argument("--structure", "--structure-slug", dest="structure", required=True)
    initialize.add_argument("--history", type=Path)
    initialize.add_argument("--event-id")
    initialize.add_argument("--design", type=Path)
    initialize.add_argument("--draft", action="store_true", help="Prepare unapproved inputs before parameter review.")
    initialize.add_argument("--route", help="Registered project-relative research route.")
    initialize.add_argument(
        "--resource-document", type=Path, default=Path("docs/project-resources.md")
    )
    initialize.add_argument("--resource-profile")
    bind = sub.add_parser("bind-approval", help="Bind a real review to existing drafts without replacing inputs.")
    bind.add_argument("--project-root", type=Path, required=True)
    bind.add_argument("--composition", required=True)
    bind.add_argument("--structure", required=True)
    bind.add_argument("--history", type=Path)
    bind.add_argument("--event-id", required=True)
    bind.add_argument("--route")
    rerun = sub.add_parser("rerun", help="Create a candidate from a terminal task; never submit it.")
    rerun.add_argument("--task-root", type=Path, required=True)
    rerun.add_argument("--reason", required=True)
    rerun.add_argument("--changes", type=Path, required=True, help="JSON list of parameter changes recorded in the revised plan.")
    submit = sub.add_parser(
        "submit",
        help="Reconcile, gate, snapshot, and submit one workflow-v2 task leaf.",
    )
    submit.add_argument("--task-root", type=Path, required=True)
    prepare = sub.add_parser("prepare")
    prepare.add_argument("--project-root", type=Path, required=True)
    prepare.add_argument("--composition", required=True)
    prepare.add_argument("--structure", required=True)
    prepare.add_argument("--task", required=True)
    prepare.add_argument("--variant")
    prepare.add_argument("--stage", required=True)
    prepare.add_argument("--engine", choices=["vasp", "quantum-espresso"], required=True)
    prepare.add_argument("--history", type=Path, required=True)
    prepare.add_argument("--event-id", required=True)
    prepare.add_argument("--matrix-id", required=True)
    prepare.add_argument("--resource-document", type=Path, default=Path("docs/project-resources.md"))
    prepare.add_argument("--resource-profile")
    prepare.add_argument("--input", action="append", default=[], metavar="NAME=PATH")
    prepare.add_argument("--dependency", action="append", default=[], metavar="NAME=PATH")
    prepare.add_argument("--primary-input")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "init-tree":
            calculations = initialize_calculation_tree(args.project_root)
            print(f"[initialized] {calculations}")
            return 0
        if args.command == "initialize":
            leaves = initialize_workflow_tree(
                args.project_root,
                args.composition,
                args.structure,
                history_path=args.history,
                event_id=args.event_id,
                design_path=args.design,
                resource_document=args.resource_document,
                resource_profile=args.resource_profile,
                draft=args.draft,
                route=args.route,
            )
            for leaf in leaves:
                print(f"[initialized] {leaf}")
            return 0
        if args.command == "bind-approval":
            for leaf in bind_approval(args.project_root, args.composition, args.structure,
                                      history_path=args.history, event_id=args.event_id, route=args.route):
                print(f"[bound] {leaf}")
            return 0
        if args.command == "rerun":
            print(create_rerun_branch(args.task_root, args.reason, json.loads(args.changes.read_text())))
            return 0
        if args.command == "submit":
            result = submit_task(args.task_root)
            if result in {"NEEDS_AGENT", "RETRY_IN_PLACE", "MAJOR_CONFLICT"}:
                print(f"[{result}] submission paused")
                return 1
            print(f"[submitted] {result}")
            return 0
        if args.command == "prepare":
            leaf = prepare_task(
                project_root=args.project_root,
                composition=args.composition,
                structure=args.structure,
                task=args.task,
                variant=args.variant,
                stage=args.stage,
                engine=args.engine,
                history_path=args.history,
                event_id=args.event_id,
                matrix_id=args.matrix_id,
                resource_document=args.resource_document,
                resource_profile=args.resource_profile,
                staged_inputs=_mapping(args.input, "input"),
                dependencies=_mapping(args.dependency, "dependency"),
                primary_input=args.primary_input,
            )
            print(f"[prepared] {leaf}")
            print("[blocked] submission still requires live drift checks, full review, and explicit approval")
            return 0
    except WorkflowError as exc:
        print(f"BLOCKER: {exc}", file=sys.stderr)
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
