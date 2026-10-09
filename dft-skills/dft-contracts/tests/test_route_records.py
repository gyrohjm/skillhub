"""Behavioral checks for route layouts, stable documents and evidence selection."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dft_contracts import project as p
from dft_contracts.layout import discover_workspace, design_plan_root
from dft_contracts.lifecycle import mark_task, screen, rework_impact
from dft_contracts.project_git import init_git, check_index


@pytest.fixture
def route_project(tmp_path, monkeypatch):
    monkeypatch.setenv('DFT_SKILLS_CONFIG_DIR', str(tmp_path / 'private'))
    root = tmp_path / 'project'
    root.mkdir()
    p.init_project(root)
    route = p.register_route(root, 'sample/anharmonic', 'sample', 'reference')
    return root, route


def task(route, name='03_scf', accepted=False):
    leaf = route / name
    leaf.mkdir(parents=True)
    fixture = Path(__file__).resolve().parents[1] / 'examples/workflow-v2.example.json'
    workflow = json.loads(fixture.read_text())
    workflow.update(task_uuid=str(uuid4()), composition_slug='sample', structure_slug='reference',
                    task_slug=name.split('/')[0], status='completed')
    workflow['dependencies'] = []
    workflow['submission'] = {'state': 'completed', 'allowed': False, 'job_id': '123', 'scheduler_state': 'COMPLETED'}
    workflow['completion'] = dict(scheduler_complete=True, artifact_complete=True, scientifically_accepted=accepted)
    (leaf / 'workflow.json').write_text(json.dumps(workflow))
    (leaf / 'README.md').write_text('# Task\n\nHuman explanation.\n')
    (leaf / 'evidence.dat').write_text('1 2\n')
    return leaf


def evidence(root, leaf):
    return [(leaf / 'evidence.dat').relative_to(root).as_posix()]


def test_registration_is_minimal_idempotent_and_does_not_infer_identity(route_project):
    root, route = route_project
    assert not (root / 'calculations').exists()
    assert not (route / 'shared').exists()
    assert not (route / '00_pseudo').exists()
    assert discover_workspace(route) == root
    assert design_plan_root(route, 'sample', 'reference') == route / 'docs'
    before = {str(f): f.read_bytes() for f in root.rglob('*') if f.is_file()}
    p.init_project(root)
    p.register_route(root, 'sample/anharmonic', 'sample', 'reference')
    assert before == {str(f): f.read_bytes() for f in root.rglob('*') if f.is_file()}
    with pytest.raises(ValueError):
        p.register_route(root, 'sample/anharmonic/other', 'sample', 'reference')


def test_sections_update_unique_documents_and_reject_stale_writers(route_project):
    root, route = route_project
    target = root / 'results/main_report.md'
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    p.save_document(root, 'main_report', 'anything', '.md', b'Convergence remains unresolved.',
                    section='convergence', expected_sha256=digest)
    first = target.read_bytes()
    with pytest.raises(ValueError, match='changed since read'):
        p.save_document(root, 'main_report', 'renamed', '.md', b'Other writer', expected_sha256=digest)
    with pytest.raises(FileExistsError):
        p.save_document(root, 'main_report', 'new_title', '.md', b'clobber', replace=True)
    p.save_document(root, 'main_report', 'same_role', '.md', b'New evidence is accepted.',
                    section='convergence', expected_sha256=hashlib.sha256(first).hexdigest())
    assert target.read_text().count('dft-section:convergence:start') == 1
    assert 'remains unresolved' not in target.read_text()
    assert list((root / 'results').glob('*report*.md')) == [target]
    with pytest.raises(ValueError):
        p.document_path(root, 'note', 'main_report_final', '.md')
    (root / 'results/main_report_v2.md').write_text('duplicate')
    assert any('duplicate main report' in s for s in p.check_project(root))


def test_task_analysis_and_events_reuse_fixed_files(route_project):
    root, route = route_project
    leaf = task(route)
    first = p.save_document(root, 'report', 'first_topic', '.md', b'# Evidence\n', task_root=leaf)
    assert first == leaf / 'analysis/README.md'
    assert p.document_path(root, 'report', 'another_title', '.md', leaf) == first
    assert p.artifact_path(leaf, 'data', 'bands', '.dat') == leaf / 'analysis/data/bands.dat'
    path = p.append_event(root, leaf, 'review_001', 'Reviewed evidence.', evidence(root, leaf))
    before = path.read_bytes()
    p.append_event(root, leaf, 'review_001', 'Reviewed evidence.', evidence(root, leaf))
    assert path.read_bytes() == before
    with pytest.raises(ValueError, match='different content'):
        p.append_event(root, leaf, 'review_001', 'Changed my mind.', evidence(root, leaf))
    assert p.check_project(root) == []


def test_screen_never_selects_scheduler_completion_and_tracks_impact(route_project):
    root, route = route_project
    upstream, child = task(route), task(route, '05_tc')
    w = json.loads((child / 'workflow.json').read_text())
    w['dependencies'] = [{'task_ref': '03_scf'}]
    (child / 'workflow.json').write_text(json.dumps(w))
    assert all(r['category'] == 'needs_review' for r in screen(root))
    with pytest.raises(ValueError, match='acceptance'):
        mark_task(upstream, 'selected', 'No acceptance', evidence(root, upstream))
    impact = rework_impact(upstream)
    assert {r['path'] for r in impact['affected']} == {str(x.relative_to(root)) for x in (upstream, child)}
    mark_task(upstream, 'terminated', 'Scientific gate failed', evidence(root, upstream))
    record = next(r for r in screen(root) if r['path'] == str(upstream.relative_to(root)))
    assert not record['archive_candidate'] and record['dependents']
    with pytest.raises(ValueError, match='dependencies'):
        mark_task(upstream, 'archived', 'Retired', evidence(root, upstream))
    assert upstream.exists()


def test_selection_unique_publication_is_traced_and_staleness_detected(route_project):
    root, route = route_project
    first, second = task(route, accepted=True), task(route, '04_scf', accepted=True)
    mark_task(first, 'selected', 'Validated reference', evidence(root, first), 'reference')
    with pytest.raises(ValueError, match='Another result'):
        mark_task(second, 'selected', 'Alternative', evidence(root, second), 'reference')
    source = p.save_document(root, 'figure', 'comparison', '.svg', b'<svg/>', task_root=first)
    target = p.publish_result(root, first, source, 'figure', 'sample_comparison', evidence(root, first))
    assert target == root / 'results/figures/sample_comparison.svg'
    assert p.check_project(root) == []
    source.write_text('<svg>changed</svg>')
    assert any('source changed' in s for s in p.check_project(root))
    with pytest.raises(ValueError, match='exists'):
        p.publish_result(root, first, source, 'figure', 'sample_comparison', evidence(root, first))
    assert target.read_text() == '<svg/>'


def test_git_hook_reads_index_and_preserves_unrelated_hooks(route_project):
    root, route = route_project
    hook = init_git(root)
    assert hook.exists()
    subprocess.run(['git', '-C', str(root), 'add', 'results/main_report.md'], check=True)
    assert check_index(root) == []
    duplicate = root / 'results/main_report_final.md'
    duplicate.write_text('copy')
    subprocess.run(['git', '-C', str(root), 'add', str(duplicate)], check=True)
    duplicate.unlink()  # Working tree looks clean; staged duplicate must still fail.
    assert any('duplicate main report' in issue for issue in check_index(root))
    result = subprocess.run([str(hook)], cwd=root, capture_output=True, text=True)
    assert result.returncode != 0
    subprocess.run(['git', '-C', str(root), 'rm', '--cached', str(duplicate)], check=True, capture_output=True)
    secret = root / 'docs/private_note.md'
    secret.parent.mkdir(exist_ok=True)
    secret.write_text('api_key=' + 'fictional_secret_12345')
    subprocess.run(['git', '-C', str(root), 'add', str(secret)], check=True)
    issues = check_index(root)
    assert any('credential assignment' in issue for issue in issues)
    assert not any('fictional_secret' in issue for issue in issues)
    hook.write_text('#!/bin/sh\nexit 7\n')
    with pytest.raises(ValueError, match='Existing pre-commit'):
        init_git(root)
    assert 'exit 7' in hook.read_text()
    assert subprocess.run(['git', '-C', str(root), 'rev-parse', '--verify', 'HEAD'], capture_output=True).returncode != 0


def test_route_escape_and_symlink_protection(route_project, tmp_path):
    root, route = route_project
    with pytest.raises(ValueError):
        p.register_route(root, '../outside', 'sample', 'reference')
    outside = tmp_path / 'external'
    outside.mkdir()
    (route / '03_alias').symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError):
        p.task_context(route / '03_alias')


def test_unknown_stage_and_unknown_route_are_not_silently_adopted(route_project):
    from dft_contracts.layout import route_for
    root, route = route_project
    unknown = route / '04_phonon'
    unknown.mkdir()
    assert screen(root)[0]['category'] == 'unidentified'
    with pytest.raises(ValueError, match='not inside'):
        route_for(root / 'wrong_route', 'sample', 'reference')
    other = root / 'sample/other'
    (other / 'docs/plans').mkdir(parents=True)
    old_plan = other / 'docs/plans/tc_plan.md'
    old_plan.write_text('Existing approved plan')
    with pytest.raises(ValueError, match='consolidation'):
        p.register_route(root, 'sample/other', 'sample', 'reference')
    assert not (other / 'docs/plan.md').exists()
    assert old_plan.read_text() == 'Existing approved plan'
