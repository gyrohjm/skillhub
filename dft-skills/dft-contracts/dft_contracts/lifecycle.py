"""Read task evidence, record selection and trace the impact of a scientific change.

No scheduler calls or filesystem relocation. Execution state remains in workflow.json.
"""
from __future__ import annotations

import json
from pathlib import Path

from .layout import discover_workspace, route_for

ACTIVE = {"submitted", "running", "pending", "queued", "PENDING", "RUNNING", "COMPLETING", "CONFIGURING"}
TERMINAL = {"completed", "failed", "cancelled", "superseded"}


def active(record):
    submission = record.get("submission", {})
    return (record.get("status") in ACTIVE or submission.get("state") in ACTIVE
            or submission.get("scheduler_state") in ACTIVE)


def dependency_graph(root, records):
    """Resolve known records; ambiguous or missing references stay explicitly unknown."""
    paths = {r["path"]: r for r in records}
    edges = {path: set() for path in paths}
    unresolved = {}
    for record in records:
        dependencies = record.get("dependencies", [])
        if isinstance(dependencies, dict):
            dependencies = list(dependencies.values())
        if not isinstance(dependencies, list):
            unresolved[record["path"]] = ["invalid dependency list"]
            continue
        dependencies = list(dependencies)
        derived = record.get("lineage", {}).get("derived_from")
        if derived:
            dependencies.append(derived)
        for dependency in dependencies:
            ref = dependency if isinstance(dependency, str) else next(
                (dependency[k] for k in ("task_ref", "path", "task_id") if isinstance(dependency, dict) and k in dependency), None)
            if not isinstance(ref, str):
                unresolved.setdefault(record["path"], []).append("unrecognized dependency")
                continue
            task = root / record["path"]
            route = route_for(task)
            scope = route[0] if route else root.joinpath(*Path(record["path"]).parts[:3])
            if ref.startswith("workspace_root:"):
                candidate = root / ref.split(":", 1)[1]
            elif ref.startswith("structure_root:"):
                candidate = scope / ref.split(":", 1)[1]
            elif ref.startswith("task_root:"):
                candidate = task.parent / ref.split(":", 1)[1]
            elif Path(ref).is_absolute():
                candidate = Path(ref)
            else:
                candidate = scope / ref
            candidate = candidate.resolve()
            matches = [p for p in paths if candidate == root / p or root / p in candidate.parents]
            if not matches and not (":" in ref or "/" in ref):
                matches = [r["path"] for r in records if r.get("task_uuid") == ref or
                           (r.get("task_slug") == ref and scope in (root / r["path"]).parents)]
            if len(matches) == 1:
                edges[record["path"]].add(matches[0])
            else:
                unresolved.setdefault(record["path"], []).append("missing or ambiguous dependency")
    return edges, unresolved


def screen(project_root):
    from .project import task_records
    root = discover_workspace(project_root)
    records = task_records(root)
    edges, unresolved = dependency_graph(root, records)
    result = []
    for record in records:
        completion = record.get("completion", {})
        management = record.get("management", {})
        disposition = management.get("disposition")
        if "error" in record:
            category = "unidentified"
        elif active(record):
            category = "active"
        elif disposition in {"superseded", "terminated", "archived", "recoverable"}:
            category = disposition
        elif disposition == "selected" and completion.get("scientifically_accepted") is True:
            category = "selected"
        else:
            category = "needs_review"
        dependents = sorted(p for p, upstream in edges.items() if record["path"] in upstream
                            or p.startswith(record["path"] + "/"))
        reasons = []
        if active(record):
            reasons.append("active execution record")
        if dependents:
            reasons.append("referenced by other tasks")
        if unresolved:
            reasons.append("unresolved dependencies exist; relocation needs investigation")
        if record.get("status") not in TERMINAL:
            reasons.append("execution is not confirmed terminal")
        if disposition not in {"superseded", "terminated", "archived"}:
            reasons.append("no explicit retirement decision")
        result.append({**record, "category": category, "dependents": dependents,
                       "archive_candidate": not reasons, "archive_blockers": reasons,
                       "scheduler_recheck_required": True,
                       "unresolved_dependencies": unresolved.get(record["path"], [])})
    return result


def validate_management(root, task, workflow, records, disposition, key):
    scope = route_for(task)[0] if route_for(task) else root.joinpath(*task.relative_to(root).parts[:3])
    if active(workflow):
        raise ValueError("Reconcile active execution before selecting or retiring this task")
    if disposition == "selected":
        completion = workflow.get("completion", {})
        if not all(completion.get(k) is True for k in ("scheduler_complete", "artifact_complete", "scientifically_accepted")):
            raise ValueError("Selection requires recorded scheduler, artifact and scientific acceptance")
        for other in records:
            management = other.get("management", {})
            if (root / other["path"] != task and scope in (root / other["path"]).parents
                    and management.get("disposition") == "selected" and management.get("selection_key") == key):
                raise ValueError("Another result is selected for this purpose; record its retirement first")
    if disposition in {"superseded", "terminated", "archived"} and workflow.get("status") not in TERMINAL:
        raise ValueError("Retirement requires a terminal execution record")
    if disposition == "archived":
        edges, unresolved = dependency_graph(root, records)
        relative = task.relative_to(root).as_posix()
        if unresolved or any(relative in upstream or name.startswith(relative + "/") for name, upstream in edges.items()):
            raise ValueError("Archive blocked by dependencies; preserve the task in place")


def mark_task(task_root, disposition, reason, evidence, selection_key=None):
    from .project import _lock, _safe, _write, task_context, task_records, _name
    from .privacy import findings, markers
    root, scope, _, workflow = task_context(task_root)
    task = Path(task_root).resolve()
    if disposition not in {"selected", "recoverable", "terminated", "superseded", "archived"}:
        raise ValueError("Unknown disposition")
    if not reason.strip() or not evidence:
        raise ValueError("A disposition requires a reason and evidence")
    for ref in evidence:
        if not _safe(root, ref).is_file():
            raise ValueError("Disposition evidence must exist inside the project")
    if findings((reason + "\n" + "\n".join(evidence)).encode(), markers()):
        raise ValueError("Private information cannot enter project decisions")
    key = _name(selection_key or workflow["task_slug"])
    path = _safe(root, task.relative_to(root) / "workflow.json")
    with _lock(root):
        workflow = json.loads(path.read_text())
        validate_management(root, task, workflow, task_records(root), disposition, key)
        workflow["management"] = {"disposition": disposition, "reason": reason,
                                  "evidence": evidence, "selection_key": key}
        _write(path, json.dumps(workflow, ensure_ascii=False, indent=2) + "\n")
    from .readmes import after_operation
    after_operation(task)
    return path


def rework_impact(task_root):
    from .project import task_context, task_records
    from .layout import project_role
    root = discover_workspace(task_root)
    if project_role(root) != "local":
        task_context(task_root)
    records = task_records(root)
    origin = Path(task_root).resolve().relative_to(root).as_posix()
    edges, unresolved = dependency_graph(root, records)
    affected = {origin}
    while True:
        following = affected | {p for p, upstream in edges.items() if upstream & affected}
        if following == affected:
            break
        affected = following
    return {"source": origin, "affected": [{"path": r["path"], "running_snapshot_immutable": active(r),
             "action": "changed_task" if r["path"] == origin else "compatibility_review_required"}
             for r in records if r["path"] in affected],
            "unresolved_dependencies": unresolved, "automatic_reuse": False,
            "note": "Record old/new parameters, evidence, reuse decisions, acceptance and retry limit in the existing plan. No jobs or records were changed."}
