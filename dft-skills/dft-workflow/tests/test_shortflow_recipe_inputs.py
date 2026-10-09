import json
import pytest
import canonical_workflow as cw
from test_shortflow_lifecycle import draft_case, approve_fixture


def ready_recipe(tmp_path):
    project, history, event, design = draft_case(tmp_path)
    upstream, leaf = cw.initialize_workflow_tree(project,"mgb2","ref_struct",design_path=design,draft=True)
    event_id = approve_fixture(history,event,design)
    cw.bind_approval(project,"mgb2","ref_struct",history_path=history,event_id=event_id)
    content = (upstream / "POSCAR").read_bytes()
    (upstream / "CONTCAR").write_bytes(content)
    w = json.loads((upstream / "workflow.json").read_text())
    w["status"] = "completed"
    w["completion"].update(scheduler_complete=True,artifact_complete=True,scientifically_accepted=True)
    w["result"]["artifacts"] = {"CONTCAR":{"path":"CONTCAR","sha256":cw.sha256_file(upstream/"CONTCAR")}}
    (upstream / "workflow.json").write_text(json.dumps(w))
    return leaf,upstream


def test_recipe_materializes_only_after_dependency_gate(tmp_path):
    from recipe_inputs import materialize_recipes
    leaf,upstream = ready_recipe(tmp_path)
    assert cw.evaluate_dependencies(leaf)["verdict"] == "ADVANCE"
    w = json.loads((leaf / "workflow.json").read_text())
    assert materialize_recipes(leaf, leaf/"workflow.json",w)
    assert (leaf/"POSCAR").read_bytes() == (upstream/"CONTCAR").read_bytes()
    record = next(item for item in w["inputs"]["files"] if item["name"]=="POSCAR")
    assert record["sha256"] == cw.sha256_file(leaf/"POSCAR")
    assert not materialize_recipes(leaf,leaf/"workflow.json",w)


def test_recipe_preserves_user_materialized_input(tmp_path):
    from recipe_inputs import materialize_recipes
    leaf,upstream = ready_recipe(tmp_path)
    (leaf/"POSCAR").write_text("user data")
    w = json.loads((leaf/"workflow.json").read_text())
    assert not materialize_recipes(leaf,leaf/"workflow.json",w)
    assert (leaf/"POSCAR").read_text() == "user data"

