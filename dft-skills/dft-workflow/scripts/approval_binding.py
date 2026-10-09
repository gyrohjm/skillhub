"""Attach an actual scientific review to a prepared, unapproved task graph."""
from __future__ import annotations
import copy
import json
from pathlib import Path
import canonical_workflow as cw
from input_reconciliation import _commit_file_transaction


def _check_parameters(workflow, task, envelope, current, leaf):
    baseline = workflow["input_snapshot"]
    wanted = dict(baseline.get("parameters", {}))
    has_parameters = (leaf / "INCAR").is_file() if task["engine"] == "vasp" else any(
        p.is_file() and p.suffix.lower() == ".in" for p in leaf.iterdir())
    for key, value in envelope["engine_parameters"].items():
        key = key.upper() if task["engine"] == "vasp" or key.upper() == "KPOINTS" else key.lower()
        if not has_parameters:
            continue  # Explicit future input recipe, not fabricated data.
        if key == "KPOINTS" and task["engine"] == "vasp" and not (leaf / "KPOINTS").exists():
            continue
        wanted[key] = value
    if set(current["parameters"]) != set(wanted) or any(
        not cw._same_value(current["parameters"].get(key), value) for key, value in wanted.items()
    ):
        raise cw.WorkflowError(f"current parameters in {leaf.name} do not match the reviewed parameters")
    for name in ("POSCAR", "POTCAR", "KPOINTS", "QE_INPUT"):
        before = copy.deepcopy(baseline.get("file_semantics", {}).get(name))
        after = copy.deepcopy(current.get("file_semantics", {}).get(name))
        if name in {"KPOINTS", "QE_INPUT"}:
            for semantic in (before, after):
                if isinstance(semantic, dict):
                    semantic.pop("mesh", None)
                    semantic.pop("k_mesh", None)
        if before != after:
            raise cw.WorkflowError(f"reviewed structure/pseudopotential identity changed: {leaf.name}/{name}")


def bind_approval(project_root, composition, structure, *, history_path=None, event_id=None, route=None):
    root = cw.validate_project(project_root)
    cw._slug(composition, "composition")
    cw._slug(structure, "structure")
    scope = cw.workspace_path(root, route, "route") if route else root
    plan_root = cw.design_plan_root(scope, composition, structure)
    design_path = plan_root / "calculation_design.json"
    history_path = history_path or plan_root / "history.jsonl"
    if not design_path.is_file():
        raise cw.WorkflowError("current design is required to bind the reviewed parameters")
    initial_design_hash = cw.sha256_file(design_path)
    approval, design, history, verified_id = cw._initial_approval(
        root, composition, structure, history_path, event_id, design_path)
    verifier = cw._load_design_verifier()
    errors = verifier.validate_execution_plan(design, required_matrix_ids=approval["scope"])
    if errors:
        raise cw.WorkflowError("invalid reviewed task graph: " + "; ".join(errors))
    tasks = design["execution_plan"]["tasks"]
    case_root = cw.calculation_scope(scope, composition, structure)
    expected = [cw._task_leaf_path(case_root, task)[0].resolve() for task in tasks]
    if set(expected) != {p.parent.resolve() for p in case_root.rglob("workflow.json")}:
        raise cw.WorkflowError("existing draft graph does not match the complete reviewed graph")
    envelopes = {item["matrix_id"]: item for item in verifier.engine_envelopes(design)}
    updates = {}
    observed = {design_path: initial_design_hash, history: cw.sha256_file(history)}
    for task, leaf in zip(tasks, expected):
        if task["matrix_id"] not in approval["scope"]:
            raise cw.WorkflowError("task is outside the reviewed approval scope")
        workflow_path = cw._submission_child(leaf, "workflow.json", "draft workflow")
        observed[workflow_path] = cw.sha256_file(workflow_path)
        _, workflow_path, workflow = cw._load_submission_workflow(leaf)
        wd = workflow["design"]
        if workflow["status"] != "planned" or wd.get("approval_ref") or workflow.get("attempts"):
            raise cw.WorkflowError("approval binding requires an unapproved, unsubmitted draft")
        if (workflow.get("composition_slug") != composition
                or workflow.get("structure_slug") != structure
                or wd.get("design_id") != approval["design_id"]
                or wd.get("matrix_id") != task["matrix_id"]
                or any(workflow.get(key) != task[key] for key in ("task_slug", "stage", "engine"))):
            raise cw.WorkflowError("draft identity does not match the reviewed task")
        if [d["task_ref"] for d in workflow["dependencies"]] != task["dependencies"]:
            raise cw.WorkflowError("draft dependencies do not match the reviewed task")
        records = workflow["inputs"]["files"]
        def signature(item):
            return (item.get("name"), item.get("mode"), item.get("source_task"), item.get("artifact"))
        if sorted(map(signature, records)) != sorted(map(signature, task["inputs"])):
            raise cw.WorkflowError("draft inputs/recipes do not match the reviewed task")
        envelope = envelopes[task["matrix_id"]]
        current = cw.parse_current_inputs(task["engine"], leaf,
            primary_input=cw.snapshot_primary_input(leaf, workflow), previous_snapshot=workflow["input_snapshot"])
        _check_parameters(workflow, task, envelope, current, leaf)
        for record in records:
            path = cw._submission_child(leaf, record["path"], "draft input")
            if not path.is_file():
                if record.get("mode") == "recipe":
                    continue
                raise cw.WorkflowError(f"missing draft input: {path}")
            digest = cw.sha256_file(path)
            parsed_digest = current.get("file_hashes", {}).get(record["name"])
            if parsed_digest is not None and parsed_digest != digest:
                raise cw.WorkflowError("input changed during approval parameter parsing")
            observed[path] = digest
            if record.get("sha256") != digest:
                record["authority"] = "user_override"
                workflow["input_authority"][record["name"]] = "user_override"
            record["sha256"] = digest
        job_path = cw._job_script_path(leaf, workflow)
        observed[job_path] = cw.sha256_file(job_path)
        workflow["job"]["sha256"] = observed[job_path]
        wd.update({"revision": approval["revision"], "approval_ref":
            f"workspace_root:{cw.relative_ref(root, history)}#{verified_id}",
            "design_sha256": approval["design_sha256"], "draft": False,
            "engine_parameters": copy.deepcopy(envelope["engine_parameters"]),
            "completion_gate": envelope["completion_gates"].get(task["stage"]),
            "baseline_parameter_hash": current["parameter_hash"]})
        workflow["input_snapshot"] = current
        workflow["status"] = "awaiting_upstream" if task["dependencies"] else "prepared"
        workflow["updated_at"] = cw.utc_now()
        workflow["history"].append({"at": workflow["updated_at"], "status": workflow["status"],
            "note": "bound first parameter review without rewriting inputs"})
        errors = cw.validate_document("workflow-v2", workflow)
        if errors:
            raise cw.WorkflowError("invalid bound workflow: " + "; ".join(errors))
        updates[workflow_path] = json.dumps(workflow, ensure_ascii=False, indent=2) + "\n"
        readme = leaf / "README.md"
        if readme.is_file() and not readme.is_symlink():
            text = readme.read_text(encoding="utf-8")
            text = text.replace("Status: `planned`", f"Status: `{workflow['status']}`", 1)
            text = text.replace("Not approved; cannot submit.", "Parameter review bound; dependency readiness is checked at submission.")
            updates[readme] = text + f"\nParameter review bound: `{verified_id}`. Inputs preserved.\n"
    if any(cw.sha256_file(path) != digest for path, digest in observed.items()):
        raise cw.WorkflowError("inputs changed during approval binding; reread current parameters")
    _commit_file_transaction(updates)
    from dft_contracts.readmes import after_operation
    after_operation(case_root)
    return expected
