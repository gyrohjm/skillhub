"""Paired-project behavior using fictional records, local endpoints and fake schedulers."""
import hashlib
import json
from argparse import Namespace
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

SUITE = Path(__file__).resolve().parents[2]
for folder in ('dft-contracts', 'dft-workflow/scripts', 'dft-workflow/tests', 'dft-design/tests'):
    sys.path.insert(0, str(SUITE / folder))
from dft_contracts import paired as pair, project as p
from dft_contracts.project_transport import Endpoint, digest
import canonical_workflow as cw
import paired_execution as execution
from test_canonical_workflow import resource_document, vasp_profile, qe_profile, write_vasp_inputs
from test_task_mode_20260910 import task_design

SPEC = {'routes': [{'path': 'sample/bands', 'composition': 'si', 'structure': 'bulk', 'stages': ['03_scf']}]}


@pytest.fixture
def locations(tmp_path, monkeypatch):
    monkeypatch.setenv('DFT_SKILLS_CONFIG_DIR', str(tmp_path / 'private'))
    return tmp_path / 'local', tmp_path / 'cluster'


def initialize(locations, **kwargs):
    local, remote = locations
    pair.init_pair(local, str(remote), spec=SPEC, git=False, **kwargs)
    return local, remote


def prepared(locations, *, approved=True, deploy=True, engine='vasp', dependent=False):
    resource_document(locations[0], {'approved-profile': vasp_profile() if engine == 'vasp' else qe_profile()})
    local, remote = initialize(locations)
    source = local / 'inputs/p1_scf'
    if engine == 'vasp':
        write_vasp_inputs(source)
        (source / 'INCAR').write_text('ENCUT=520\nISMEAR=0\nSIGMA=0.05\n')
    else:
        source.mkdir(parents=True)
        (source / 'pw.in').write_text("&CONTROL\n calculation='scf',\n/\n&SYSTEM\n ecutwfc=80, ecutrho=640, occupations='smearing', degauss=0.01, nat=1, ntyp=1,\n/\nATOMIC_SPECIES\nSi 28.085 Si.upf\nCELL_PARAMETERS angstrom\n3 0 0\n0 3 0\n0 0 3\nATOMIC_POSITIONS crystal\nSi 0 0 0\nK_POINTS automatic\n6 6 1 0 0 0\n")
        (source / 'Si.upf').write_text('fictional potential')
    design = task_design(engine)
    design['title'] = 'LOCAL_ONLY_RESEARCH_NARRATIVE'
    design['execution_plan']['tasks'][0].pop('job_script')
    design['execution_plan']['tasks'][0]['directory'] = '03_scf/mesh_6'
    if dependent:
        import copy
        child = copy.deepcopy(design['execution_plan']['tasks'][0])
        child.update(task_slug='p2_band', stage='band', directory='05_band', dependencies=['p1_scf'])
        child['inputs'][0] = {'name':'pw.in', 'mode':'recipe', 'source_task':'p1_scf', 'artifact':'next.in'}
        design['execution_plan']['tasks'].append(child)
        design['calculation_matrix'][0]['stages'].append('band')
        design['engine_stage_envelopes'][0]['completion_gates']['band'] = 'engine normal termination'
    plan = local / 'sample/bands/docs/calculation_design.json'
    plan.write_text(json.dumps(design))
    leaves = cw.initialize_workflow_tree(local, 'si', 'bulk', draft=True, route='sample/bands')
    leaf = leaves[0]
    if approved:
        cd = cw._load_design_verifier()
        sync = json.dumps({'design_id': design['design_id'], 'revision': design['revision']})
        (plan.parent / 'plan.md').write_text(f'<!-- dft-design-sync: {sync} -->\n# Plan\n')
        (plan.parent / 'history.jsonl').write_text('')
        cd.cmd_approve(Namespace(project=local / 'sample/bands', composition_slug='si', structure_slug='bulk',
            design=plan, reviewer='fictional_reviewer', scope=['M1'], note='review supplied parameters'))
        event = json.loads((plan.parent / 'history.jsonl').read_text().splitlines()[-1])
        cw.bind_approval(local, 'si', 'bulk', event_id=event['event_id'], route='sample/bands')
    if not deploy:
        return local, remote, leaf, plan
    for candidate in leaves:
        execution.deploy_task(local, candidate)
    task = leaf.relative_to(execution.preparation_root(local)).as_posix()
    return local, remote, remote / task, plan


def scheduler(monkeypatch):
    import resource_preflight as rp
    monkeypatch.setattr(rp, 'load_cached_preflight', lambda *a, **k: {'cache_status': 'ready', 'approved_profile': k['profile']})
    calls = []
    def run(argv, **kwargs):
        calls.append(argv)
        return SimpleNamespace(returncode=0, stdout='34567\n' if argv[0] == 'sbatch' else '', stderr='')
    return calls, run


def test_preview_and_organization_are_non_overwriting_idempotent_and_private(locations):
    local, remote = locations
    refs = local / 'docs/refs'
    refs.mkdir(parents=True)
    (refs / 'seed.cif').write_text('fictional original structure')
    (local / 'AGENTS.md').write_text('# User rules\nKeep this instruction.\n')
    spec = dict(SPEC, references=[{'source': 'docs/refs/seed.cif', 'target': 'docs/refs/structures/seed.cif'}])
    before = {str(x): x.read_bytes() for x in local.rglob('*') if x.is_file()}
    pair.init_pair(local, str(remote), spec=spec, dry_run=True)
    assert before == {str(x): x.read_bytes() for x in local.rglob('*') if x.is_file()}
    assert not remote.exists() and not (local.parent / 'private').exists()
    pair.init_pair(local, str(remote), spec=spec, git=False)
    assert 'Keep this instruction' in (local / 'AGENTS.md').read_text()
    assert not (refs / 'seed.cif').exists()
    assert (refs / 'structures/seed.cif').read_text() == 'fictional original structure'
    before = {str(x): x.read_bytes() for root in (local, remote) for x in root.rglob('*') if x.is_file()}
    pair.init_pair(local, str(remote), spec=spec, git=False)
    assert before == {str(x): x.read_bytes() for root in (local, remote) for x in root.rglob('*') if x.is_file()}
    assert not list(remote.rglob('plan.md')) and not list(remote.rglob('main_report.md'))
    assert not (local / 'results').exists()
    for root in (local, remote):
        assert not list(root.rglob('scripts/README.md')) and not list(root.rglob('docs/README.md'))
    assert not (local / 'sample/bands/03_scf').exists()
    assert p.check_project(remote) == []
    private = local.parent / 'private'
    assert private.stat().st_mode & 0o777 == 0o700
    assert all(p.stat().st_mode & 0o777 == 0o600 for p in private.glob('*.json'))
    assert str(remote) not in (local / 'dft-project.json').read_text()


def test_reference_collision_and_binding_conflict_preserve_contents(locations):
    local, remote = locations
    refs = local / 'docs/refs'; refs.mkdir(parents=True)
    (refs / 'a.cif').write_text('source')
    (refs / 'b.cif').write_text('different')
    with pytest.raises(ValueError, match='conflict'):
        pair.init_pair(local, str(remote), spec=dict(SPEC, references=[{'source':'docs/refs/a.cif','target':'docs/refs/b.cif'}]), git=False)
    assert not remote.exists() and (refs / 'a.cif').read_text() == 'source'
    initialize(locations)
    with pytest.raises(ValueError, match='one main cluster'):
        pair.init_pair(local, str(remote.parent / 'elsewhere'), spec=SPEC, git=False)


def test_pair_prepare_deploy_and_submit_need_no_remote_plan(locations, monkeypatch):
    local, remote, leaf, plan = prepared(locations)
    assert p.check_project(remote) == []
    assert not (local / 'sample/bands/03_scf').exists()
    assert not (leaf / 'README.md').exists()
    assert (leaf.parent / 'README.md').is_file()
    assert not list(remote.rglob('calculation_design.json')) and not list(remote.rglob('history.jsonl'))
    assert all(b'LOCAL_ONLY_RESEARCH_NARRATIVE' not in p.read_bytes() for p in remote.rglob('*') if p.is_file())
    calls, runner = scheduler(monkeypatch)
    assert cw.submit_task(leaf, runner=runner) == '34567'
    assert sum(argv[0] == 'sbatch' for argv in calls) == 1
    assert plan.is_file() and not list(remote.rglob('plan.md'))


def test_draft_blocks_submission_and_cluster_edits_require_local_review(locations, monkeypatch):
    local, remote, leaf, plan = prepared(locations, approved=False)
    calls, runner = scheduler(monkeypatch)
    with pytest.raises(cw.WorkflowError, match='approval'):
        cw.submit_task(leaf, runner=runner)
    assert not calls


def test_parameter_edit_roundtrip_and_snapshot_tamper(locations, monkeypatch):
    local, remote, leaf, plan = prepared(locations)
    (leaf / 'INCAR').write_text('ENCUT=600\nISMEAR=0\nSIGMA=0.05\n')
    calls, runner = scheduler(monkeypatch)
    before_plan = plan.read_bytes()
    assert cw.submit_task(leaf, runner=runner) == 'NEEDS_AGENT'
    assert not calls and plan.read_bytes() == before_plan
    result = execution.reconcile_remote(local, leaf.relative_to(remote).as_posix())
    assert result['verdict'] == 'ADVANCE'
    assert json.loads(plan.read_text())['engine_stage_envelopes'][0]['engine_parameters']['ENCUT'] == 600
    assert not list(remote.rglob('plan.md'))
    history = (plan.parent / 'history.jsonl').read_bytes()
    ledger = (leaf / 'workflow.json').read_bytes()
    assert execution.reconcile_remote(local, leaf.relative_to(remote).as_posix())['status'] == 'synchronized'
    assert (plan.parent / 'history.jsonl').read_bytes() == history
    assert (leaf / 'workflow.json').read_bytes() == ledger
    assert cw.submit_task(leaf, runner=runner) == '34567'
    with pytest.raises(ValueError, match='snapshots'):
        execution.reconcile_remote(local, leaf.relative_to(remote).as_posix())


def selected(locations):
    local, remote, leaf, plan = prepared(locations)
    workflow = json.loads((leaf / 'workflow.json').read_text())
    workflow['status'] = 'completed'
    workflow['completion'] = dict(scheduler_complete=True, artifact_complete=True, scientifically_accepted=True)
    workflow['submission']['state'] = 'completed'
    (leaf / 'workflow.json').write_text(json.dumps(workflow))
    for name, content in {'scripts/plot.py': "print('fictional plot')\n", 'data/bands.dat':'0 1\n', 'figures/bands.svg':'<svg/>\n'}.items():
        file = leaf / name; file.parent.mkdir(parents=True, exist_ok=True); file.write_text(content)
    task = leaf.relative_to(remote).as_posix()
    evidence = [task + '/scripts/plot.py', task + '/data/bands.dat']
    pair.mark_pair(local, task, 'selected', 'Recorded convergence and evidence gates passed.', evidence, 'bands')
    return local, remote, leaf, task, evidence


def test_publication_limit_reproduction_conflicts_and_source_invalidation(locations):
    local, remote, leaf, task, evidence = selected(locations)
    source = task + '/figures/bands.svg'
    args = (local, task, source, 'figure', 'bands', evidence)
    assert pair.publish_pair(*args, max_bytes=1)['status'] == 'needs_scope_approval'
    assert not (local / 'analysis/figures/bands.svg').exists()
    assert pair.publish_pair(*args)['status'] == 'published'
    assert (local / task / 'scripts/plot.py').read_bytes() == (leaf / 'scripts/plot.py').read_bytes()
    assert (local / task / 'inputs/INCAR').is_file()
    assert not (local / task / 'README.md').exists()
    assert not (local / 'analysis/README.md').exists()
    report = (local / 'analysis/main_report.md').read_text()
    assert report.index('Artifact navigation') < report.index('## Findings')
    assert pair.check_pair(local) == []
    (leaf / 'data/bands.dat').write_text('0 2\n')
    pair.sync_pair(local)
    assert 'needs_review' in (local / 'docs/data-index.md').read_text()
    assert 'Review affected' in (local / 'analysis/main_report.md').read_text()
    assert any('source/selection changed' in issue for issue in pair.check_pair(local))
    (local / task / 'scripts/plot.py').write_text('local edit')
    with pytest.raises(ValueError, match='edited'):
        pair.publish_pair(*args)


def test_interrupted_transfer_is_pending_resumable_and_never_removes_sources(locations, monkeypatch):
    local, remote, leaf, task, evidence = selected(locations)
    endpoint = Endpoint(str(remote))
    original = endpoint.fetch
    count = 0
    def broken(*args, **kwargs):
        nonlocal count
        count += 1
        if count == 2:
            raise RuntimeError('simulated disconnect')
        return original(*args, **kwargs)
    monkeypatch.setattr(endpoint, 'fetch', broken)
    args = (local, task, task + '/figures/bands.svg', 'figure', 'bands', evidence)
    with pytest.raises(RuntimeError):
        pair.publish_pair(*args, endpoint=endpoint)
    assert not (local / '.dft/publications.json').exists()
    assert any('pending' in issue for issue in pair.check_pair(local))
    monkeypatch.setattr(endpoint, 'fetch', original)
    assert pair.publish_pair(*args, endpoint=endpoint)['status'] == 'published'
    assert (leaf / 'data/bands.dat').exists()
    monkeypatch.setattr(endpoint, 'read', lambda *a, **k: (_ for _ in ()).throw(RuntimeError('offline')))
    with pytest.raises(RuntimeError, match='stale'):
        pair.sync_pair(local, endpoint=endpoint)
    assert 'not refreshed' in (local / 'README.md').read_text()


def test_readme_roles_recent_events_and_git_use_new_final_entry(locations):
    local, remote = initialize(locations)
    route = local / 'sample/bands'
    for number in range(5):
        p.append_event(local, route, f'event_{number}', f'Change number {number}.', [])
    pair.sync_pair(local)
    text = (route / 'README.md').read_text()
    assert 'Change number 4' in text and 'Change number 0' not in text and 'Change number 1' not in text
    timeline = (route / 'docs/log.md').read_bytes()
    p.append_event(local, route, 'event_4', 'Change number 4.', [])
    assert timeline == (route / 'docs/log.md').read_bytes()
    stage = local / 'sample/bands/03_scf'
    p.save_document(local, 'report', 'bands', '.md', b'# Band analysis\n\nEvidence remains preliminary.\n', task_root=stage)
    assert (stage / 'README.md').exists()
    pair.init_pair(local, str(remote), spec=SPEC)
    assert subprocess.run(['git','-C',str(local),'rev-parse','--verify','HEAD'],capture_output=True).returncode != 0
    subprocess.run(['git','-C',str(local),'add','analysis/main_report.md'],check=True)
    from dft_contracts.project_git import check_index
    assert check_index(local) == []


def test_endpoint_rejects_symlinks_traversal_and_guard_conflicts(tmp_path):
    root = tmp_path / 'endpoint'; root.mkdir()
    (root / 'data').write_text('old')
    endpoint = Endpoint(str(root))
    with pytest.raises(ValueError):
        endpoint.read('../escape')
    (root / 'link').symlink_to(root / 'data')
    with pytest.raises(RuntimeError):
        endpoint.read('link')
    with pytest.raises(RuntimeError):
        endpoint.write('data', b'new', expected=digest(root / 'data'), guards={'missing':'wrong'})
    assert (root / 'data').read_text() == 'old'
    metadata = endpoint.stat('data')
    destination = tmp_path / 'copy'; destination.write_text('preserved local copy')
    (root / 'data').write_text('changed during transport')
    with pytest.raises((RuntimeError, ValueError), match='checksum|changed'):
        endpoint.fetch('data', destination, metadata, expected=digest(destination))
    assert destination.read_text() == 'preserved local copy'


def test_offline_init_completes_known_local_work_and_resumes(locations, monkeypatch):
    original = Endpoint.read
    monkeypatch.setattr(Endpoint, 'read', lambda *a, **k: (_ for _ in ()).throw(RuntimeError('offline')))
    local, remote = locations
    assert pair.init_pair(local, str(remote), spec=SPEC, git=False)['status'] == 'pending'
    assert (local / 'sample/bands/docs/plan.md').is_file() and not remote.exists()
    assert 'not refreshed' in (local / 'README.md').read_text()
    monkeypatch.setattr(Endpoint, 'read', original)
    assert pair.init_pair(local, str(remote), spec=SPEC, git=False)['status'] == 'complete'
    assert pair.check_pair(local) == []


def test_unreviewed_preparation_and_execution_metadata_changes_fail_closed(locations):
    local, remote, leaf, plan = prepared(locations, deploy=False)
    original = (leaf / 'INCAR').read_text()
    (leaf / 'INCAR').write_text(original.replace('520', '700'))
    with pytest.raises(ValueError, match='after review'):
        execution.deploy_task(local, leaf)
    assert not list(remote.rglob('workflow.json'))
    (leaf / 'INCAR').write_text(original)
    execution.deploy_task(local, leaf)
    target = remote / leaf.relative_to(execution.preparation_root(local))
    workflow = json.loads((target / 'workflow.json').read_text())
    workflow['dependencies'].append({'task_ref':'unreviewed', 'required_artifacts':[], 'gate_status':'pending'})
    (target / 'workflow.json').write_text(json.dumps(workflow))
    with pytest.raises(cw.WorkflowError, match='dependencies'):
        execution.check_execution(target, workflow)
    with pytest.raises(ValueError, match='metadata changed'):
        execution.reconcile_remote(local, target.relative_to(remote).as_posix())


def test_qe_pair_recipe_materialization_and_submission(locations, monkeypatch):
    local, remote, leaf, plan = prepared(locations, engine='quantum-espresso', dependent=True)
    workflow = json.loads((leaf / 'workflow.json').read_text())
    (leaf / 'next.in').write_bytes((leaf / 'pw.in').read_bytes())
    workflow['status'] = 'completed'
    workflow['completion'].update(scheduler_complete=True, artifact_complete=True, scientifically_accepted=True)
    workflow['result']['artifacts'] = {'next.in': {'path':'next.in', 'sha256':digest(leaf / 'next.in')}}
    (leaf / 'workflow.json').write_text(json.dumps(workflow))
    child = remote / 'sample/bands/05_band'
    calls, runner = scheduler(monkeypatch)
    assert cw.submit_task(child, runner=runner) == '34567'
    assert (child / 'pw.in').read_bytes() == (leaf / 'next.in').read_bytes()
    assert sum(argv[0] == 'sbatch' for argv in calls) == 1
    assert not list(remote.rglob('plan.md'))


def test_scientific_rerun_gets_own_binding_and_preserves_finished_source(locations, monkeypatch):
    local, remote, source, task, evidence = selected(locations)
    before = (source / 'workflow.json').read_bytes(), (source / 'INCAR').read_bytes()
    child = cw.create_rerun_branch(source, 'local_change_001', [{'name':'ENCUT', 'old':520, 'new':600, 'impact':'L2'}])
    (child / 'INCAR').write_text('ENCUT=600\nISMEAR=0\nSIGMA=0.05\n')
    calls, runner = scheduler(monkeypatch)
    with pytest.raises(cw.WorkflowError, match='identity'):
        cw.submit_task(child, runner=runner)
    assert not calls
    assert execution.reconcile_remote(local, child.relative_to(remote).as_posix())['verdict'] == 'ADVANCE'
    assert cw.submit_task(child, runner=runner) == '34567'
    assert not (child / 'README.md').exists()
    assert before == ((source / 'workflow.json').read_bytes(), (source / 'INCAR').read_bytes())


def test_default_size_boundary_counts_all_bundles_for_one_task_version(locations, monkeypatch):
    local, remote, leaf, task, evidence = selected(locations)
    source = task + '/figures/bands.svg'
    endpoint = Endpoint(str(remote))
    stat = endpoint.stat
    inventory = pair.publish_pair(local, task, source, 'figure', 'bands', evidence, dry_run=True)
    added = pair.AUTO_LIMIT - inventory['bytes']
    monkeypatch.setattr(endpoint, 'stat', lambda name: dict(stat(name), size=stat(name)['size'] + added)
                        if str(name) == task + '/data/bands.dat' else stat(name))
    args = (local, task, source, 'figure', 'bands', evidence)
    assert pair.publish_pair(*args, dry_run=True, endpoint=endpoint)['status'] == 'ready'
    added += 1
    assert pair.publish_pair(*args, dry_run=True, endpoint=endpoint)['status'] == 'needs_scope_approval'
    assert not (local / 'analysis/figures/bands.svg').exists()
    monkeypatch.setattr(endpoint, 'stat', stat)
    pair.publish_pair(*args)
    (leaf / 'figures/second.svg').write_text('<svg>second</svg>')
    second = pair.publish_pair(local, task, task + '/figures/second.svg', 'figure', 'second', evidence, dry_run=True)
    assert second['bytes'] == inventory['bytes'] + (leaf / 'figures/second.svg').stat().st_size


def test_renamed_shared_sources_and_existing_git_hook_are_preserved(locations):
    local, remote = locations
    refs = local / 'docs/refs'; refs.mkdir(parents=True)
    (refs / 'seed.cif').write_text('fictional seed')
    subprocess.run(['git', 'init', '-q', str(local)], check=True)
    hook = local / '.git/hooks/pre-commit'
    hook.write_text('#!/bin/sh\nexit 0\n'); hook.chmod(0o755)
    spec = dict(SPEC, references=[{'source':'docs/refs/seed.cif', 'target':'docs/refs/structures/seed.cif'}],
        cluster_files=[{'source':'docs/refs/structures/seed.cif', 'target':'shared/structures/v1_seed.cif'}])
    result = pair.init_pair(local, str(remote), spec=spec)
    assert result['git_check'] == 'requires_existing_hook_integration'
    assert hook.read_text() == '#!/bin/sh\nexit 0\n'
    assert (remote / 'shared/structures/v1_seed.cif').read_bytes() == (refs / 'structures/seed.cif').read_bytes()
