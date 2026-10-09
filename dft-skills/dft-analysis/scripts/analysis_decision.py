"""Decision helpers for the dft-analysis completion and failure gates.

The module is deliberately read-only: it evaluates records and evidence but
never edits a task, changes an input, or submits a job.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping

from adapters import parse_quantum_espresso, parse_vasp
from parse_result import detect_engine


PARSERS = {
    "vasp": parse_vasp,
    "quantum-espresso": parse_quantum_espresso,
    "qe": parse_quantum_espresso,
}


SUCCESS_STATES = {"COMPLETED", "COMPLETE", "SUCCESS", "SUCCEEDED", "DONE", "FINISHED"}
FAILURE_STATES = {
    "FAILED",
    "FAILURE",
    "CANCELLED",
    "CANCELED",
    "TIMEOUT",
    "OUT_OF_MEMORY",
    "OOM",
    "PREEMPTED",
}
TECHNICAL_FAILURE_CLASSES = {
    "input_preparation",
    "scheduler_resource",
    "runtime_environment",
    "postprocess",
}
POSITIVE_SCIENTIFIC_VERDICTS = {"SUPPORTED", "ACCEPTED", "TRUE", "PASS", "PASSED"}
NEGATIVE_SCIENTIFIC_VERDICTS = {
    "FALSIFIED",
    "UNEXPECTED",
    "NOT_SUPPORTED",
    "REJECTED",
    "INVALID",
    "FALSE",
}
INCONCLUSIVE_SCIENTIFIC_VERDICTS = {
    "INCONCLUSIVE",
    "NOT_EVALUATED",
    "UNKNOWN",
    "PENDING",
}
POSITIVE_ARTIFACT_STATES = {
    "AVAILABLE",
    "COMPLETE",
    "COMPLETED",
    "OK",
    "PARSED",
    "PARSEABLE",
    "PRESENT",
    "SUCCESS",
    "SUCCEEDED",
    "VALID",
    "VALIDATED",
}

_FAILURE_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "scheduler_resource",
        (
            r"out\s+of\s+memory",
            r"oom(?:[- ]kill)?",
            r"time\s*limit",
            r"timed\s*out",
            r"\btimeout\b",
            r"cancel(?:led|ed)",
            r"preempt",
            r"node\s+(?:failure|fail|down)",
            r"quota\s+exceed",
        ),
    ),
    (
        "runtime_environment",
        (
            r"segmentation\s+fault",
            r"bus\s+error",
            r"floating\s+point\s+exception",
            r"mpi[_ -]?(?:abort|error|failure)",
            r"\bpmi\b",
            r"cannot\s+load\s+(?:shared|library)",
            r"shared\s+object",
            r"command\s+not\s+found",
        ),
    ),
    (
        "numerical_convergence",
        (
            r"convergence\s+(?:not\s+achieved|not\s+reached|failed)",
            r"not\s+converged",
            r"too\s+many\s+(?:iterations|steps)",
            r"scf\s+(?:failed|did\s+not\s+converge)",
            r"diagonalization\s+(?:failed|not\s+converged)",
            r"charge\s+density.*(?:converg|mixing)",
        ),
    ),
    (
        "input_preparation",
        (
            r"error\s+in\s+reading",
            r"input\s+error",
            r"unknown\s+(?:card|namelist|keyword)",
            r"invalid\s+(?:input|namelist|parameter)",
            r"cannot\s+open",
            r"no\s+such\s+file",
            r"pseudopotential",
            r"bad\s+input",
        ),
    ),
    (
        "postprocess",
        (
            r"post[- ]?process",
            r"\b(?:projwfc|dos\.x|bands\.x|vaspkit|lobster)\b",
            r"(?:parse|parsing)\s+(?:error|failed)",
            r"no\s+data\s+(?:found|available)",
        ),
    ),
)


def assess_completion(
    workflow: Mapping[str, Any],
    result: Mapping[str, Any],
    *,
    stage: str,
    source_ref: str | None = None,
) -> dict[str, Any]:
    """Return a conservative completion decision without mutating records.

    A result is accepted only when the leaf says ``completed``, the scheduler
    exposes a successful terminal state, the engine terminated normally, and
    the convergence fields required by the stage are explicitly ``True``.
    Missing evidence is ``inconclusive`` rather than success.
    """

    submission = workflow.get("submission")
    submission = submission if isinstance(submission, Mapping) else {}
    completion_record = workflow.get("completion")
    completion_record = completion_record if isinstance(completion_record, Mapping) else {}
    scheduler_state = _first_value(
        submission,
        "scheduler_state",
        "terminal_state",
        "state",
        "status",
    )
    if scheduler_state is None:
        scheduler_state = _first_value(workflow, "scheduler_state", "terminal_state")
    scheduler_token = _normalise_state(scheduler_state)
    explicit_scheduler_complete = _bool_value(completion_record.get("scheduler_complete"))
    scheduler_complete = (
        explicit_scheduler_complete
        if explicit_scheduler_complete is not None
        else scheduler_token in SUCCESS_STATES
    )

    termination = result.get("termination")
    termination = termination if isinstance(termination, Mapping) else {}
    convergence = result.get("convergence")
    convergence = convergence if isinstance(convergence, Mapping) else {}

    needs_ionic = "relax" in stage.lower() or "vc-relax" in stage.lower()
    checks: dict[str, bool] = {
        "workflow_completed": workflow.get("status") == "completed",
        "scheduler_completed": scheduler_complete,
        "normal_termination": (
            termination.get("normal") is True
            and _normalise_state(termination.get("status")) in SUCCESS_STATES
        ),
        "electronic_convergence": convergence.get("electronic") is True,
    }
    if needs_ionic:
        checks["ionic_convergence"] = convergence.get("ionic") is True

    engine_evidence_complete = all(
        checks[key]
        for key in ("normal_termination", "electronic_convergence")
        if key in checks
    ) and (not needs_ionic or checks.get("ionic_convergence") is True)
    artifact_complete = _completion_boolean(
        completion_record,
        result,
        workflow,
        key="artifact_complete",
    )
    if artifact_complete is None:
        artifact_complete = _artifact_evidence(result, workflow)
    if artifact_complete is None:
        # Only v1 adapters may use parsed termination/convergence as their
        # artifact fallback.  A v2 leaf must carry explicit artifact evidence.
        artifact_complete = engine_evidence_complete if _workflow_version(workflow) == 1 else False

    scientific_signal = _scientific_signal(result, workflow)
    explicit_scientific_acceptance = _completion_boolean(
        completion_record,
        result,
        workflow,
        key="scientifically_accepted",
    )

    reasons: list[str] = []
    if scheduler_state is None and explicit_scheduler_complete is not True:
        reasons.append("scheduler terminal state is missing")
    elif not scheduler_complete:
        reasons.append(f"scheduler terminal state is not successful: {scheduler_state}")
    if workflow.get("status") != "completed":
        reasons.append(f"workflow status is not completed: {workflow.get('status')!r}")
    if termination.get("normal") is not True:
        reasons.append("engine normal termination is not established")
    elif _normalise_state(termination.get("status")) not in SUCCESS_STATES:
        reasons.append(f"engine terminal status is not successful: {termination.get('status')!r}")
    if convergence.get("electronic") is not True:
        reasons.append("electronic convergence evidence is missing or false")
    if needs_ionic and convergence.get("ionic") is not True:
        reasons.append("ionic convergence evidence is missing or false")
    if not artifact_complete:
        reasons.append("artifact completion evidence is missing or false")

    technical_complete = (
        checks["workflow_completed"]
        and scheduler_complete
        and artifact_complete
        and engine_evidence_complete
    )
    technical_failure = (
        workflow.get("status") == "failed"
        or termination.get("normal") is False
        or scheduler_token in FAILURE_STATES
        or _normalise_state(workflow.get("failure_class")) in {
            _normalise_state(value) for value in TECHNICAL_FAILURE_CLASSES
        }
    )

    if technical_complete:
        status = "completed"
    elif technical_failure:
        status = "failed"
    else:
        status = "inconclusive"

    scientifically_accepted = _scientific_acceptance(
        scientific_signal,
        explicit_scientific_acceptance,
        technical_complete=technical_complete,
    )
    accepted = technical_complete and (
        scientifically_accepted
        or (
            _workflow_version(workflow) == 1
            and scientific_signal is None
            and explicit_scientific_acceptance is None
        )
    )
    recovery_mode = "none"
    if _has_scientific_change(result, workflow):
        recovery_mode = "create_rerun_branch"
    elif technical_complete and scientific_signal in {"negative", "inconclusive"}:
        recovery_mode = "create_rerun_branch"
    elif technical_failure:
        recovery_mode = "retry_in_place"

    derived_from = _derived_from(workflow, source_ref) if recovery_mode == "create_rerun_branch" else None
    if scientific_signal == "negative":
        reasons.append("scientific result is unexpected; completed technical evidence is preserved")
    elif scientific_signal == "inconclusive":
        reasons.append("scientific acceptance remains unresolved")
    return {
        "status": status,
        "accepted": accepted,
        "stage": stage,
        "checks": checks,
        "reasons": reasons,
        "completion": {
            "scheduler_complete": bool(scheduler_complete),
            "artifact_complete": bool(artifact_complete),
            "scientifically_accepted": scientifically_accepted,
        },
        "recovery_mode": recovery_mode,
        "derived_from": derived_from,
    }


def diagnose_failure(
    workflow: Mapping[str, Any],
    result: Mapping[str, Any] | None,
    evidence: Mapping[str, str],
    *,
    parameter_changes: list[dict[str, Any]] | None = None,
    acceptance_rule: str | None = None,
    source_ref: str | None = None,
) -> dict[str, Any]:
    """Classify failure evidence and return a bounded handoff recommendation."""

    evidence_items: list[dict[str, str]] = []
    matches: list[tuple[int, str, str, str]] = []
    for source, content in evidence.items():
        text = str(content)
        lowered = text.lower()
        for priority, (failure_class, patterns) in enumerate(_FAILURE_RULES):
            for pattern in patterns:
                match = re.search(pattern, lowered)
                if match:
                    matches.append((priority, failure_class, source, text[max(0, match.start() - 80): match.end() + 80]))
                    break

    if matches:
        _priority, failure_class, _source, _snippet = sorted(matches, key=lambda item: item[0])[0]
        for _priority, matched_class, source, snippet in sorted(matches, key=lambda item: item[0]):
            evidence_items.append({"source": source, "class": matched_class, "snippet": " ".join(snippet.split())})
    else:
        submission = workflow.get("submission")
        submission = submission if isinstance(submission, Mapping) else {}
        scheduler_state = _first_value(
            submission,
            "scheduler_state",
            "terminal_state",
            "state",
            "status",
        )
        if _normalise_state(scheduler_state) in FAILURE_STATES:
            failure_class = "scheduler_resource"
            evidence_items.append(
                {
                    "source": "workflow.json",
                    "class": failure_class,
                    "snippet": f"scheduler terminal state={scheduler_state}",
                }
            )
        else:
            candidate = workflow.get("failure_class")
            known_classes = {item[0] for item in _FAILURE_RULES}
            failure_class = candidate if isinstance(candidate, str) and candidate in known_classes else "unknown"

    if workflow.get("status") == "failed":
        evidence_items.append({"source": "workflow.json", "class": "workflow", "snippet": "status=failed"})
    if isinstance(result, Mapping):
        termination = result.get("termination")
        if isinstance(termination, Mapping) and termination.get("normal") is False:
            evidence_items.append({"source": "result", "class": "engine", "snippet": "normal termination=false"})

    proposed_changes = parameter_changes
    if proposed_changes is None and isinstance(result, Mapping):
        candidate = result.get("parameter_changes")
        if isinstance(candidate, list):
            proposed_changes = [item for item in candidate if isinstance(item, dict)]
    recommendation = recommend_next_step(
        failure_class,
        parameter_changes=proposed_changes,
        acceptance_rule=acceptance_rule,
        workflow=workflow,
        source_ref=source_ref,
    )
    return {
        "failure_class": failure_class,
        "confidence": "high" if matches else "low",
        "evidence": evidence_items,
        **recommendation,
    }


def recommend_next_step(
    failure_class: str,
    *,
    parameter_changes: list[dict[str, Any]] | None = None,
    acceptance_rule: str | None = None,
    workflow: Mapping[str, Any] | None = None,
    source_ref: str | None = None,
    derived_from: str | None = None,
) -> dict[str, Any]:
    """Map a diagnosis to owners and a safe, non-submitting next action."""

    routes: dict[str, tuple[str, list[str], str, bool]] = {
        "input_preparation": (
            "dft-workflow",
            ["dft-workflow"],
            "recheck the approved inputs, paths, units, and engine preflight before preparing a new leaf",
            False,
        ),
        "scheduler_resource": (
            "dft-workflow",
            ["dft-workflow"],
            "recheck the approved resource profile and live scheduler evidence before preparing a bounded retry",
            False,
        ),
        "runtime_environment": (
            "dft-workflow",
            ["dft-workflow"],
            "recheck the approved module/source-script launch path and runtime diagnostics before retrying",
            False,
        ),
        "numerical_convergence": (
            "dft-design",
            ["dft-design", "dft-workflow"],
            "create a dft-design revision for the proposed numerical change, then let dft-workflow prepare and review it",
            True,
        ),
        "postprocess": (
            "dft-analysis",
            ["dft-analysis"],
            "repair or rerun the post-processing adapter after verifying the completed source leaf",
            False,
        ),
        "unknown": (
            "dft-design",
            ["dft-design", "dft-workflow"],
            "collect missing scheduler, engine, and input evidence before proposing any parameter change",
            True,
        ),
    }
    owner, handoff, action, requires_design_revision = routes.get(failure_class, routes["unknown"])
    changes = list(parameter_changes or [])
    if changes:
        recovery_mode = "create_rerun_branch"
    elif failure_class in TECHNICAL_FAILURE_CLASSES:
        recovery_mode = "retry_in_place"
    elif failure_class == "numerical_convergence":
        recovery_mode = "retry_in_place"
    else:
        recovery_mode = "none"
    lineage_source = derived_from or _derived_from(workflow or {}, source_ref)
    return {
        "next_owner": owner,
        "owner": owner,
        "handoff": handoff,
        "recommended_action": action,
        "requires_design_revision": requires_design_revision,
        "parameter_changes": changes,
        "acceptance_rule": acceptance_rule or "",
        "submission_authorized": False,
        "recovery_mode": recovery_mode,
        "derived_from": lineage_source if recovery_mode == "create_rerun_branch" else None,
    }


def _first_value(mapping: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = mapping.get(key)
        if value is not None and value != "":
            return value
    return None


def _normalise_state(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"[^A-Z0-9]+", "_", str(value).upper()).strip("_")


def _bool_value(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _workflow_version(workflow: Mapping[str, Any]) -> int:
    if workflow.get("contract") == "dft.workflow.v2" or workflow.get("schema_version") == 2:
        return 2
    return 1


def _completion_boolean(
    completion: Mapping[str, Any],
    result: Mapping[str, Any],
    workflow: Mapping[str, Any],
    *,
    key: str,
) -> bool | None:
    for document in (completion, result, workflow):
        value = _bool_value(document.get(key))
        if value is not None:
            return value
    return None


def _artifact_collection_complete(value: Any) -> bool | None:
    if isinstance(value, Mapping):
        if not value:
            return False
        if any(key in value for key in ("status", "complete", "completed", "valid", "validated", "parseable", "parsed", "parse_status")):
            values = [value]
        else:
            values = list(value.values())
    elif isinstance(value, list):
        if not value:
            return False
        values = value
    else:
        return None
    for item in values:
        if isinstance(item, bool):
            if not item:
                return False
            continue
        if not isinstance(item, Mapping):
            return False
        evidence_seen = False
        for key in ("complete", "completed", "valid", "validated", "parseable", "parsed"):
            if key in item:
                evidence_seen = True
                if item[key] is not True:
                    return False
        for key in ("status", "parse_status"):
            if key in item:
                evidence_seen = True
                status = item[key]
                if status is not True and _normalise_state(status) not in POSITIVE_ARTIFACT_STATES:
                    return False
        if not evidence_seen:
            return False
    return True


def _artifact_evidence(*documents: Mapping[str, Any]) -> bool | None:
    for document in documents:
        for key in ("artifacts", "outputs", "source_files"):
            if key in document:
                return _artifact_collection_complete(document.get(key))
    return None


def _scientific_signal(*documents: Mapping[str, Any]) -> str | None:
    keys = ("scientific_verdict", "hypothesis_verdict")

    def inspect(value: Any, *, key: str | None = None) -> str | None:
        if isinstance(value, bool) and key in {"scientific_acceptance", "scientifically_accepted"}:
            return "positive" if value else "inconclusive"
        if isinstance(value, str):
            normalized = _normalise_state(value)
            if normalized in POSITIVE_SCIENTIFIC_VERDICTS:
                return "positive"
            if normalized in NEGATIVE_SCIENTIFIC_VERDICTS:
                return "negative"
            if normalized in INCONCLUSIVE_SCIENTIFIC_VERDICTS:
                return "inconclusive"
        if isinstance(value, Mapping):
            for nested_key in ("verdict", "accepted", "scientific_verdict"):
                if nested_key in value:
                    signal = inspect(value[nested_key], key=nested_key)
                    if signal:
                        return signal
        return None

    def walk(document: Mapping[str, Any], *, allow_status: bool = False) -> str | None:
        for key in keys:
            if key in document:
                signal = inspect(document[key], key=key)
                if signal:
                    return signal
        if "verdict" in document:
            signal = inspect(document["verdict"], key="verdict")
            if signal:
                return signal
        if allow_status and "status" in document:
            signal = inspect(document["status"], key="status")
            if signal:
                return signal
        for key in ("analysis", "scientific", "hypothesis", "acceptance"):
            nested = document.get(key)
            if isinstance(nested, Mapping):
                signal = walk(nested, allow_status=True)
                if signal:
                    return signal
        return None

    for document in documents:
        signal = walk(document)
        if signal:
            return signal
    return None


def _scientific_acceptance(
    signal: str | None,
    explicit: bool | None,
    *,
    technical_complete: bool,
) -> bool:
    if not technical_complete:
        return False
    if signal == "negative" or signal == "inconclusive":
        return False
    if signal == "positive":
        return True
    return explicit is True


def _has_scientific_change(*documents: Mapping[str, Any]) -> bool:
    for document in documents:
        for key in ("parameter_changes", "scientific_parameter_changes", "model_change"):
            value = document.get(key)
            if (isinstance(value, list) and value) or (isinstance(value, Mapping) and value) or value is True:
                return True
        for key in ("analysis", "scientific", "design_change"):
            nested = document.get(key)
            if isinstance(nested, Mapping) and _has_scientific_change(nested):
                return True
    return False


def _derived_from(workflow: Mapping[str, Any], source_ref: str | None) -> str | None:
    if source_ref:
        return source_ref
    lineage = workflow.get("lineage")
    if isinstance(lineage, Mapping) and lineage.get("derived_from"):
        return str(lineage["derived_from"])
    for key in ("task_ref", "task_id", "workflow_ref", "source_workflow", "task_slug"):
        if workflow.get(key):
            return str(workflow[key])
    return None


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def _read_evidence(paths: Iterable[Path]) -> dict[str, str]:
    return {str(path): path.read_text(encoding="utf-8", errors="replace") for path in paths}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="analysis_decision.py")
    sub = parser.add_subparsers(dest="command", required=True)

    completion = sub.add_parser("completion")
    completion.add_argument("--workflow", type=Path, required=True)
    source = completion.add_mutually_exclusive_group(required=True)
    source.add_argument("--result", type=Path)
    source.add_argument("--task-dir", type=Path)
    completion.add_argument("--engine", choices=("auto", *PARSERS), default="auto")
    completion.add_argument("--stage", required=True)
    completion.set_defaults(handler=_run_completion)

    failure = sub.add_parser("diagnose")
    failure.add_argument("--workflow", type=Path, required=True)
    failure.add_argument("--result", type=Path)
    failure.add_argument("--task-dir", type=Path)
    failure.add_argument("--engine", choices=("auto", *PARSERS), default="auto")
    failure.add_argument("--evidence", type=Path, action="append", default=[])
    failure.set_defaults(handler=_run_diagnose)
    return parser


def _run_completion(args: argparse.Namespace) -> int:
    if args.task_dir:
        task_dir = args.task_dir.expanduser().resolve()
        engine = detect_engine(task_dir) if args.engine == "auto" else args.engine
        result = PARSERS[engine](task_dir)
    else:
        result = _load_json(args.result)
    decision = assess_completion(_load_json(args.workflow), result, stage=args.stage)
    print(json.dumps(decision, indent=2, ensure_ascii=False))
    return 0 if decision["accepted"] else 1


def _run_diagnose(args: argparse.Namespace) -> int:
    if args.task_dir:
        task_dir = args.task_dir.expanduser().resolve()
        engine = detect_engine(task_dir) if args.engine == "auto" else args.engine
        result = PARSERS[engine](task_dir)
    else:
        result = _load_json(args.result) if args.result else None
    evidence = _read_evidence(args.evidence)
    decision = diagnose_failure(_load_json(args.workflow), result, evidence)
    print(json.dumps(decision, indent=2, ensure_ascii=False))
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.handler(args)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
