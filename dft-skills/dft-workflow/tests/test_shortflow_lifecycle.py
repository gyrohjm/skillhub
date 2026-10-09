import copy
import json
import pytest
import canonical_workflow as cw
from test_canonical_workflow import (base_project, approved_history, two_task_execution_plan,
    write_two_task_inputs, resource_document, vasp_profile)


def draft_case(tmp_path):
    project = base_project(tmp_path)
    write_two_task_inputs(project)
    history, event_id = approved_history(project, engine='vasp', resource_profile='nmg_vasp_2n',
        engine_parameters={'ENCUT':600,'ISMEAR':0,'SIGMA':0.05,'KPOINTS':'6x6x6'},
        execution_plan=two_task_execution_plan())
    event = json.loads(history.read_text())
    history.write_text('')
    design = history.parent / 'calculation_design.json'
    design.write_text(json.dumps(event['design_snapshot']))
    resource_document(project, {'nmg_vasp_2n': vasp_profile()})
    return project, history, event, design


def approve_fixture(history, event, design):
    event = copy.deepcopy(event)
    event['design_snapshot'] = json.loads(design.read_text())
    event['design_sha256'] = cw.canonical_sha256(event['design_snapshot'])
    history.write_text(json.dumps(event) + '\n')
    return event['event_id']


def test_draft_creates_complete_tree_without_approval_and_cannot_submit(tmp_path):
    project, history, event, design = draft_case(tmp_path)
    leaves = cw.initialize_workflow_tree(project, 'mgb2', 'ref_struct', design_path=design, draft=True)
    assert (project / 'MEMORY.md').is_file()
    assert 'dft_project.py' in (project / 'AGENTS.md').read_text()
    from uuid import UUID
    ids = [json.loads((leaf / 'workflow.json').read_text())['task_uuid'] for leaf in leaves]
    assert len(set(ids)) == len(leaves)
    assert all(UUID(value) for value in ids)
    assert len(leaves) == 2 and history.read_text() == ''
    for leaf in leaves:
        w = json.loads((leaf / 'workflow.json').read_text())
        assert w['status'] == 'planned' and w['design']['approval_ref'] is None
        assert w['submission']['allowed'] is False
        assert (leaf / 'job.sh').exists()  # known launch is prepared even with a structure recipe
        w['status'] = 'prepared'  # status alone cannot promote an unapproved draft
        (leaf / 'workflow.json').write_text(json.dumps(w))
        calls = []
        with pytest.raises(cw.WorkflowError, match='approv'):
            cw.submit_task(leaf, runner=lambda *a, **k: calls.append(a))
        assert calls == []


def test_bind_real_approval_preserves_existing_inputs_and_has_no_probes(tmp_path):
    project, history, event, design = draft_case(tmp_path)
    leaves = cw.initialize_workflow_tree(project, 'mgb2', 'ref_struct', design_path=design, draft=True)
    before = {p:p.read_bytes() for leaf in leaves for p in leaf.iterdir() if p.name not in {'workflow.json','README.md'}}
    event_id = approve_fixture(history, event, design)
    assert cw.bind_approval(project, 'mgb2', 'ref_struct', history_path=history, event_id=event_id) == leaves
    for p, data in before.items():
        assert p.read_bytes() == data
    records = [json.loads((leaf / 'workflow.json').read_text()) for leaf in leaves]
    assert [w['status'] for w in records] == ['prepared','awaiting_upstream']
    assert all(w['design']['approval_ref'].endswith('#'+event_id) for w in records)
    assert len(history.read_text().splitlines()) == 1


def test_bind_rejects_unreviewed_edit_without_partial_ledger_update(tmp_path):
    project, history, event, design = draft_case(tmp_path)
    leaves = cw.initialize_workflow_tree(project, 'mgb2', 'ref_struct', design_path=design, draft=True)
    event_id = approve_fixture(history, event, design)
    input_file = leaves[-1] / 'INCAR'
    input_file.write_text(input_file.read_text().replace('600', '610'))
    before = {leaf: (leaf / 'workflow.json').read_bytes() for leaf in leaves}
    with pytest.raises(cw.WorkflowError, match='reviewed|parameter'):
        cw.bind_approval(project, 'mgb2', 'ref_struct', history_path=history, event_id=event_id)
    assert all((leaf / 'workflow.json').read_bytes() == before[leaf] for leaf in leaves)
    assert '610' in input_file.read_text()


def test_bind_adopts_numerical_edit_when_it_is_in_real_review(tmp_path):
    project, history, event, design = draft_case(tmp_path)
    leaves = cw.initialize_workflow_tree(project, 'mgb2', 'ref_struct', design_path=design, draft=True)
    for leaf in leaves:
        p = leaf / 'INCAR'
        p.write_text(p.read_text().replace('600', '610'))
    d = json.loads(design.read_text())
    d['engine_stage_envelopes'][0]['engine_parameters']['ENCUT'] = 610
    design.write_text(json.dumps(d))
    event_id = approve_fixture(history, event, design)
    cw.bind_approval(project, 'mgb2', 'ref_struct', history_path=history, event_id=event_id)
    for leaf in leaves:
        w = json.loads((leaf / 'workflow.json').read_text())
        assert w['design']['engine_parameters']['ENCUT'] == 610
        assert w['input_authority']['INCAR'] == 'user_override'


def test_bind_rejects_incomplete_graph(tmp_path):
    project, history, event, design = draft_case(tmp_path)
    leaves = cw.initialize_workflow_tree(project, 'mgb2', 'ref_struct', design_path=design, draft=True)
    event_id = approve_fixture(history, event, design)
    (leaves[-1] / 'workflow.json').unlink()
    with pytest.raises(cw.WorkflowError):
        cw.bind_approval(project, 'mgb2', 'ref_struct', history_path=history, event_id=event_id)
    assert json.loads((leaves[0] / 'workflow.json').read_text())['status'] == 'planned'


def test_bind_cli_reports_rejected_event_without_duplicate_module_traceback(tmp_path):
    import subprocess
    import sys
    project,history,event,design=draft_case(tmp_path)
    cw.initialize_workflow_tree(project,'mgb2','ref_struct',design_path=design,draft=True)
    result=subprocess.run([sys.executable,'-X','utf8',cw.__file__,'bind-approval',
        '--project-root',str(project),'--composition','mgb2','--structure','ref_struct',
        '--history',str(history),'--event-id','missing'],capture_output=True,text=True)
    assert result.returncode==1
    assert 'Traceback' not in result.stderr


def test_new_task_names_share_the_canonical_snake_case_rule(tmp_path):
    with pytest.raises(cw.WorkflowError, match="slug"):
        cw._task_leaf_path(tmp_path, {"task_slug": "p1_relax-final"})
    path, variant = cw._task_leaf_path(tmp_path, {"task_slug": "p1_relax", "variant": "spin_0"})
    assert path == tmp_path / "p1_relax/spin_0" and variant == "spin_0"
