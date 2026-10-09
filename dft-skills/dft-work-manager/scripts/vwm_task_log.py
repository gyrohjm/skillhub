#!/usr/bin/env python3
"""Append concise, structure-scoped human task events to ``logs/``."""

from __future__ import annotations

import argparse
import json
import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


SKILL_ROOT = Path(__file__).resolve().parents[1]
CONTRACTS_ROOT = SKILL_ROOT.parent / "dft-contracts"
if str(CONTRACTS_ROOT) not in sys.path:
    sys.path.insert(0, str(CONTRACTS_ROOT))

from dft_contracts import (  # noqa: E402
    calculations_root,
    discover_workspace,
    ensure_within,
    logs_root,
    structure_log_path,
)


STATUS_CHOICES = (
    "planned",
    "prepared",
    "submitted",
    "running",
    "completed",
    "failed",
    "inconclusive",
    "superseded",
)
TABLE_HEADER = "| timestamp | task | action | status | job_id | evidence | next action |"
TABLE_SEPARATOR = "|---|---|---|---|---|---|---|"
STATUS_BLOCK_START = "<!-- dft-work-manager:status:start -->"
STATUS_BLOCK_END = "<!-- dft-work-manager:status:end -->"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _escape(value: object) -> str:
    return str(value).replace("|", r"\|").replace("\r", " ").replace("\n", " ").strip()


def _workflow_context(task_path: Path, workflow: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Read derived lineage metadata without changing the live task ledger."""

    document: Mapping[str, Any] = workflow or {}
    if workflow is None:
        path = task_path / "workflow.json"
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            loaded = {}
        if isinstance(loaded, Mapping):
            document = loaded

    attempts = document.get("attempts")
    attempt_ids = [
        str(item["attempt_id"])
        for item in attempts
        if isinstance(item, Mapping) and item.get("attempt_id")
    ] if isinstance(attempts, list) else []

    lineage = document.get("lineage")
    lineage = lineage if isinstance(lineage, Mapping) else {}
    overrides: list[str] = []
    override_evidence: list[dict[str, Any]] = []

    authority = document.get("input_authority")
    if isinstance(authority, Mapping):
        for name, record in authority.items():
            if isinstance(record, Mapping) and record.get("authority") == "user_override":
                label = str(name)
                if label not in overrides:
                    overrides.append(label)
                override_evidence.append({"name": label, **dict(record)})

    inputs = document.get("inputs")
    files = inputs.get("files") if isinstance(inputs, Mapping) else None
    if isinstance(files, list):
        for record in files:
            if not isinstance(record, Mapping) or record.get("authority") != "user_override":
                continue
            label = str(record.get("name") or record.get("path") or "input")
            if label not in overrides:
                overrides.append(label)
            if not any(item.get("name") == label for item in override_evidence):
                override_evidence.append({"name": label, **dict(record)})

    return {
        "workflow_status": document.get("status", "unknown"),
        "attempt_ids": attempt_ids,
        "lineage": {
            "derived_from": lineage.get("derived_from"),
            "supersedes": lineage.get("supersedes"),
        },
        "user_overrides": overrides,
        "user_override_evidence": override_evidence,
    }


def _context_lines(context: Mapping[str, Any]) -> list[str]:
    lines: list[str] = [f"- Workflow status at recording: `{_escape(context.get('workflow_status', 'unknown'))}`"]
    attempts = context.get("attempt_ids")
    if isinstance(attempts, list) and attempts:
        lines.append(f"- Attempt IDs: `{', '.join(_escape(item) for item in attempts)}`")
    lineage = context.get("lineage")
    if isinstance(lineage, Mapping):
        if lineage.get("derived_from"):
            lines.append(f"- Derived from: `{_escape(lineage['derived_from'])}`")
        if lineage.get("supersedes"):
            lines.append(f"- Supersedes: `{_escape(lineage['supersedes'])}`")
    overrides = context.get("user_overrides")
    if isinstance(overrides, list) and overrides:
        rendered = ", ".join(f"user_override:{_escape(item)}" for item in overrides)
        lines.append(f"- User override evidence: `{rendered}`")
    return lines


def _write_if_missing(path: Path, content: str) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _task_identity(task_dir: Path, calculations: Path) -> tuple[str, str, str]:
    task_path = ensure_within(calculations, task_dir)
    relative = task_path.relative_to(calculations)
    if len(relative.parts) < 3:
        raise ValueError(
            "task directory must be calculations/<composition>/<structure>/<task>"
        )
    composition, structure = relative.parts[:2]
    task_parts = relative.parts[2:]
    if task_parts[0] == "failed":
        if len(task_parts) < 2:
            raise ValueError("failed task path is missing its original task slug")
        task_parts = task_parts[1:]
        task_label = "/".join(task_parts)
    else:
        task_label = "/".join(task_parts)
    if not task_label:
        raise ValueError("task directory is missing a task slug")
    return composition, structure, task_label


def _relative_evidence(workspace: Path, evidence: list[Path]) -> list[str]:
    rendered: list[str] = []
    for item in evidence:
        resolved = ensure_within(workspace, item)
        rendered.append(resolved.relative_to(workspace).as_posix())
    return rendered


def _ensure_log_indexes(workspace: Path, composition: str) -> None:
    root = logs_root(workspace)
    _write_if_missing(
        root / "README.md",
        "# DFT Task Logs\n\n"
        "Human-readable derived timelines live under `<composition>/<structure>.md`. "
        "workflow.json owns execution status; README preserves human explanation.\n",
    )
    _write_if_missing(
        root / composition / "README.md",
        f"# DFT Task Logs: {composition}\n\n"
        "One Markdown timeline is maintained for each structure.\n",
    )


def _upsert_marked_block(path: Path, block: str, fallback_title: str) -> None:
    """Replace one derived manager block without touching surrounding content."""

    existing = path.read_text(encoding="utf-8") if path.exists() else f"{fallback_title}\n\n"
    start = existing.find(STATUS_BLOCK_START)
    end_marker = STATUS_BLOCK_END
    end = existing.find(end_marker, start + len(STATUS_BLOCK_START)) if start >= 0 else -1
    if start >= 0 and end >= 0:
        end += len(end_marker)
        updated = existing[:start].rstrip() + "\n\n" + block.strip() + "\n" + existing[end:].lstrip()
    else:
        updated = existing.rstrip() + "\n\n" + block.strip() + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    # `Path.write_text(..., newline=...)` is not available on all supported
    # Python versions.  Open explicitly so the derived Markdown remains
    # newline-stable without making the logger version-dependent.
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(updated)


def _status_block(
    *,
    title: str,
    task_label: str,
    action: str,
    status: str,
    timestamp: str,
    job_id: str,
    evidence: list[str],
    next_action: str,
    timeline: str | None = None,
    workflow_context: Mapping[str, Any] | None = None,
) -> str:
    evidence_text = "<br>".join(evidence) if evidence else "none"
    timeline_line = f"- Timeline: `{timeline}`\n" if timeline else ""
    context_lines = _context_lines(workflow_context or {})
    context_text = "\n".join(context_lines) + ("\n" if context_lines else "")
    return (
        f"{STATUS_BLOCK_START}\n"
        f"## {title}\n"
        f"- Task: `{task_label}`\n"
        f"- Last action: `{_escape(action)}`\n"
        f"- Event status: `{_escape(status)}`\n"
        f"- Job ID: `{_escape(job_id) or 'none'}`\n"
        f"- Evidence: `{evidence_text}`\n"
        f"- Next action: `{_escape(next_action) or 'none'}`\n"
        f"- Last update: `{_escape(timestamp)}`\n"
        f"{context_text}"
        f"{timeline_line}"
        f"{STATUS_BLOCK_END}"
    )


def _update_manager_readmes(
    *,
    workspace: Path,
    calculations: Path,
    composition: str,
    structure: str,
    task_path: Path,
    task_label: str,
    action: str,
    status: str,
    timestamp: str,
    job_id: str,
    evidence: list[str],
    next_action: str,
    workflow_context: Mapping[str, Any],
) -> None:
    structure_root = calculations / composition / structure
    task_readme = task_path / "README.md"
    _upsert_marked_block(
        task_readme,
        _status_block(
            title="Manager status",
            task_label=task_label,
            action=action,
            status=status,
            timestamp=timestamp,
            job_id=job_id,
            evidence=evidence,
            next_action=next_action,
            workflow_context=workflow_context,
        ),
        f"# {task_label}",
    )
    _upsert_marked_block(
        structure_root / "README.md",
        _status_block(
            title="Latest manager event",
            task_label=task_label,
            action=action,
            status=status,
            timestamp=timestamp,
            job_id=job_id,
            evidence=evidence,
            next_action=next_action,
            workflow_context=workflow_context,
        ),
        f"# {structure}",
    )
    log_relative = f"{composition}/{structure}.md"
    _upsert_marked_block(
        logs_root(workspace) / "README.md",
        _status_block(
            title="Latest manager event",
            task_label=f"{composition}/{structure}/{task_label}",
            action=action,
            status=status,
            timestamp=timestamp,
            job_id=job_id,
            evidence=evidence,
            next_action=next_action,
            timeline=log_relative,
            workflow_context=workflow_context,
        ),
        "# DFT Task Logs",
    )
    _upsert_marked_block(
        logs_root(workspace) / composition / "README.md",
        _status_block(
            title="Latest manager event",
            task_label=f"{structure}/{task_label}",
            action=action,
            status=status,
            timestamp=timestamp,
            job_id=job_id,
            evidence=evidence,
            next_action=next_action,
            timeline=f"{structure}.md",
            workflow_context=workflow_context,
        ),
        f"# DFT Task Logs: {composition}",
    )
def append_task_event(
    task_dir: str | Path,
    *,
    action: str,
    status: str,
    timestamp: str,
    job_id: str,
    evidence: list[Path],
    next_action: str,
    workflow: Mapping[str, Any] | None = None,
    event_id: str | None = None,
) -> Path:
    """Append one manager event and return its structure log path."""

    if status not in STATUS_CHOICES:
        raise ValueError(f"status must be one of {STATUS_CHOICES}: {status!r}")
    task_path = Path(task_dir).expanduser().resolve()
    workspace = discover_workspace(task_path)
    from dft_contracts.layout import route_for
    route = route_for(task_path)
    if route:
        from dft_contracts.project import append_event
        labels = _relative_evidence(workspace, evidence)
        body = f"Task: {task_path.relative_to(workspace)}\nAction: {action}\nEvent status: {status}\nJob: {job_id}\nNext: {next_action}"
        body += "\n" + "\n".join(_context_lines(_workflow_context(task_path, workflow)))
        key = event_id or "event_" + hashlib.sha256((body + json.dumps(labels)).encode()).hexdigest()[:20]
        return append_event(workspace, task_path, key, body, labels)
    calculations = calculations_root(workspace)
    composition, structure, task_label = _task_identity(task_path, calculations)
    evidence_labels = _relative_evidence(workspace, evidence)
    workflow_context = _workflow_context(task_path, workflow)
    _ensure_log_indexes(workspace, composition)

    log_path = structure_log_path(workspace, composition, structure)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    if not log_path.exists():
        log_path.write_text(
            f"# DFT Task Log: {composition} / {structure}\n\n"
            "This is a derived human-readable timeline. Execution source of truth: workflow.json. README preserves human explanation.\n\n"
            f"{TABLE_HEADER}\n{TABLE_SEPARATOR}\n",
            encoding="utf-8",
        )

    context_evidence: list[str] = list(evidence_labels)
    attempt_ids = workflow_context.get("attempt_ids")
    if isinstance(attempt_ids, list):
        context_evidence.extend(f"attempt:{item}" for item in attempt_ids)
    lineage = workflow_context.get("lineage")
    if isinstance(lineage, Mapping) and lineage.get("derived_from"):
        context_evidence.append(f"derived_from:{lineage['derived_from']}")
    overrides = workflow_context.get("user_overrides")
    if isinstance(overrides, list):
        context_evidence.extend(f"user_override:{item}" for item in overrides)
    evidence_text = "<br>".join(_escape(item) for item in context_evidence)
    row = "| " + " | ".join(
        (
            _escape(timestamp),
            _escape(task_label),
            _escape(action),
            _escape(status),
            _escape(job_id),
            evidence_text,
            _escape(next_action),
        )
    ) + " |\n"
    if row in log_path.read_text():
        return log_path.resolve()
    with log_path.open("a", encoding="utf-8", newline="") as handle:
        handle.write(row)
    _update_manager_readmes(
        workspace=workspace,
        calculations=calculations,
        composition=composition,
        structure=structure,
        task_path=task_path,
        task_label=task_label,
        action=action,
        status=status,
        timestamp=timestamp,
        job_id=job_id,
        evidence=context_evidence,
        next_action=next_action,
        workflow_context=workflow_context,
    )
    return log_path.resolve()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="vwm_task_log.py")
    sub = parser.add_subparsers(dest="command", required=True)
    append = sub.add_parser("append", help="Append one structure-scoped task event.")
    append.add_argument("--task-dir", type=Path, required=True)
    append.add_argument("--action", required=True)
    append.add_argument("--status", choices=STATUS_CHOICES, required=True)
    append.add_argument("--timestamp", default=utc_now())
    append.add_argument("--job-id", default="")
    append.add_argument("--evidence", type=Path, action="append", default=[])
    append.add_argument("--next-action", default="")
    append.add_argument("--event-id")
    append.set_defaults(func=cmd_append)
    return parser


def cmd_append(args: argparse.Namespace) -> int:
    path = append_task_event(
        args.task_dir,
        action=args.action,
        status=args.status,
        timestamp=args.timestamp,
        job_id=args.job_id,
        evidence=args.evidence,
        next_action=args.next_action,
        event_id=args.event_id,
    )
    print(f"[ok] appended task event: {path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (OSError, ValueError) as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
