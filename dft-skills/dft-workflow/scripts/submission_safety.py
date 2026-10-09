"""Small durable guards around the single canonical scheduler adapter."""
from __future__ import annotations
import copy
import json
import os
import re
import subprocess
from contextlib import contextmanager
from pathlib import Path


def _cw():
    import canonical_workflow
    return canonical_workflow


@contextmanager
def submission_lock(root):
    cw = _cw()
    path = cw._submission_child(root, ".submission.lock", "submission lock")
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise cw.WorkflowError("submission is locked; reconcile the running or interrupted submit before retrying") from exc
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps({"pid": os.getpid(), "created_at": cw.utc_now()}))
            handle.flush()
            os.fsync(handle.fileno())
        yield
    finally:
        path.unlink(missing_ok=True)


def job_id_from_output(stdout):
    match = re.fullmatch(r"\s*([1-9][0-9]*)(?:;[A-Za-z0-9_.-]+)?\s*", stdout)
    return match.group(1) if match else None


def recover_receipt(root, workflow_path, workflow):
    cw = _cw()
    attempts_root = cw._submission_child(root, "attempts", "attempts")
    if not attempts_root.exists():
        return None
    known = {item.get("attempt_id") for item in workflow.get("attempts", [])}
    for attempt in sorted(attempts_root.iterdir()):
        if not cw._SUBMISSION_ATTEMPT_RE.fullmatch(attempt.name) or attempt.name in known:
            continue
        attempt = cw._submission_child(root, attempt.relative_to(root), "attempt")
        receipt = cw._submission_child(root, attempt.relative_to(root) / "sbatch.receipt.json", "receipt")
        intent = cw._submission_child(root, attempt.relative_to(root) / "submission.intent.json", "submission intent")
        if not receipt.is_file():
            if intent.exists():
                raise cw.WorkflowError("submission outcome requires scheduler reconciliation; refusing another sbatch")
            continue
        try:
            value = json.loads(receipt.read_text(encoding="utf-8"))
            manifest_path = cw._submission_child(root, attempt.relative_to(root) / "submission_snapshot/manifest.json", "snapshot manifest")
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            job_id = job_id_from_output(value.get("stdout", ""))
            if not job_id or value.get("job_id") != job_id or value.get("returncode") != 0 or value.get("attempt_id") != attempt.name:
                raise ValueError("invalid receipt")
            if manifest.get("attempt_id") != attempt.name or not manifest.get("files"):
                raise ValueError("invalid snapshot manifest")
            for name, record in manifest["files"].items():
                path = cw._submission_child(root, attempt.relative_to(root) / "submission_snapshot" / name, "snapshot file")
                if not path.is_file() or cw.sha256_file(path) != record["sha256"]:
                    raise ValueError("snapshot hash mismatch")
        except (ValueError, KeyError, OSError, TypeError) as exc:
            raise cw.WorkflowError("cannot safely recover scheduler receipt; reconcile external job first") from exc
        persist_success(workflow_path, workflow, manifest, value["argv"], job_id, value.get("recorded_at"))
        return job_id
    return None


def persist_success(workflow_path, workflow, manifest, argv, job_id, timestamp=None):
    cw = _cw()
    updated = copy.deepcopy(workflow)
    attempt_id = manifest["attempt_id"]
    receipt_ref = f"task_root:attempts/{attempt_id}/sbatch.receipt.json"
    timestamp = timestamp or cw.utc_now()
    updated.setdefault("attempts", []).append({
        "attempt_id": attempt_id, "reason": "submission",
        "snapshot": {"archive": f"task_root:attempts/{attempt_id}/submission_snapshot",
            "files": copy.deepcopy(manifest["files"]), "hashes": copy.deepcopy(manifest["hashes"]),
            "baseline_parameter_hash": manifest["baseline_parameter_hash"]},
        "scheduler": {"command": " ".join(argv), "argv": argv, "returncode": 0, "receipt": receipt_ref},
        "job_id": job_id, "submitted_at": timestamp})
    updated.update(status="submitted", updated_at=timestamp)
    updated.setdefault("submission", {}).update(state="submitted", allowed=True, job_id=job_id,
        attempt_id=attempt_id, receipt=receipt_ref, blockers=[])
    updated.setdefault("history", []).append({"at": timestamp, "status": "submitted",
        "note": "scheduler receipt persisted before ledger; no repeated parameter approval",
        "attempt_id": attempt_id, "job_id": job_id})
    cw._write_submission_workflow(workflow_path, updated)


def assert_content(root, hashes):
    cw = _cw()
    for name, digest in hashes.items():
        path = cw._submission_child(root, name, "checked input")
        if not path.is_file() or cw.sha256_file(path) != digest:
            raise cw.WorkflowError("input changed during submission checks; realign current parameters before submitting")


def syntax_check(root, workflow_path, workflow, job_path, runner, *, expected_ledger_hash=None):
    cw = _cw()
    expected_ledger_hash = expected_ledger_hash or cw.sha256_file(workflow_path)
    if cw.sha256_file(workflow_path) != expected_ledger_hash:
        raise cw.WorkflowError("workflow changed during submission checks; preserve and realign it")
    digest = cw.sha256_file(job_path)
    if workflow.get("job", {}).get("syntax_checked_sha256") == digest:
        return
    argv = ["bash", "-n", job_path.relative_to(root).as_posix()]
    if runner is subprocess.run:
        result = runner(argv, cwd=str(root), capture_output=True, text=True, check=False)
    else:
        result = runner(argv, cwd=str(root), env=dict(os.environ))
    if getattr(result, "returncode", 1) != 0:
        raise cw.WorkflowError("submission script failed bash -n: " + str(getattr(result, "stderr", "")))
    if cw.sha256_file(job_path) != digest:
        raise cw.WorkflowError("submission script changed during syntax validation")
    if cw.sha256_file(workflow_path) != expected_ledger_hash:
        raise cw.WorkflowError("workflow changed during submission checks; preserve and realign it")
    workflow.setdefault("job", {})["syntax_checked_sha256"] = digest
    cw._atomic_write_text(workflow_path, json.dumps(workflow, ensure_ascii=False, indent=2) + "\n")
