"""Materialize explicit upstream-file recipes, never replace user-present inputs."""
from __future__ import annotations
import json
import os


def materialize_recipes(root, workflow_path, workflow, *, gate=None):
    import canonical_workflow as cw
    import workflow_control as control
    gate = gate if gate is not None else cw.evaluate_dependencies(root)
    if gate.get("verdict") != "ADVANCE":
        raise cw.WorkflowError("upstream recipe is not approved by the dependency gate")
    dependencies = {item["task_ref"]: item for item in workflow.get("dependencies", [])}
    changed = False
    for record in workflow["inputs"]["files"]:
        if record.get("mode") != "recipe":
            continue
        destination = cw._submission_child(root, record["path"], "recipe destination")
        if destination.exists():
            continue  # User files are authoritative; reconciliation handles their semantics.
        dependency = dependencies.get(record["source_task"])
        if dependency is None:
            raise cw.WorkflowError("recipe source is not a declared dependency")
        upstream, _ = control._resolve_dependency(root, dependency)
        if upstream is None:
            raise cw.WorkflowError("recipe upstream task disappeared")
        _, _, upstream_workflow = cw._load_submission_workflow(upstream)
        artifact = record["artifact"]
        records = control._artifact_records(upstream_workflow)
        source_record = records.get(artifact.casefold())
        source = control._artifact_path(upstream, artifact, source_record)
        if not source.is_file():
            raise cw.WorkflowError("recipe artifact disappeared")
        content = source.read_bytes()
        digest = cw.hashlib.sha256(content).hexdigest()
        expected = control._recorded_hashes(dependency).get(artifact.casefold())
        if source_record:
            expected = expected or source_record.get("sha256",source_record.get("hash"))
        if expected and expected.lower() != digest.lower():
            raise cw.WorkflowError("recipe artifact changed after dependency validation")
        destination.parent.mkdir(parents=True,exist_ok=True)
        try:
            with destination.open("xb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
        except FileExistsError as exc:
            raise cw.WorkflowError("input appeared during recipe materialization; preserve and reconcile it") from exc
        record.update(sha256=digest, materialized_from=record["source_task"] + "/" + artifact)
        changed = True
    if changed:
        cw._atomic_write_text(workflow_path,json.dumps(workflow,ensure_ascii=False,indent=2)+"\n")
    return changed

