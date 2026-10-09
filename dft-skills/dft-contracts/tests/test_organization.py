"""Old-tree organization with fictional files and recorded fake inactivity checks."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sys

import pytest

SUITE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SUITE / 'dft-contracts'))
sys.path.insert(0, str(SUITE / 'dft-work-manager/scripts'))
from dft_contracts import organization as org, project as p, readmes
import dft_project


@pytest.fixture
def root(tmp_path, monkeypatch):
    monkeypatch.setenv('DFT_SKILLS_CONFIG_DIR', str(tmp_path / 'private'))
    project = tmp_path / 'project'
    project.mkdir()
    return project


def write(root, name, content):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def contents(root):
    return {p.relative_to(root).as_posix(): p.read_bytes()
            for p in root.rglob('*') if p.is_file() and not p.is_symlink()}


def spec(source='old_notes', target='route/docs/sources/notes', **extra):
    return {'id': 'tidy_notes', 'moves': [{'source': source, 'target': target}], **extra}


def proof(root, task, *, age=0, scheduler_active=False):
    path = write(root, '.dft/fake-scheduler-observation.json', json.dumps({
        'observed_at': (datetime.now(timezone.utc) - timedelta(seconds=age)).isoformat(),
        'tasks': {task: {'scheduler_active': scheduler_active,
                         'source': 'fictional scheduler fixture, exact task scope'}},
    }))
    return {'path': task, 'evidence': path.relative_to(root).as_posix(), 'sha256': sha(path)}


def task(root, name='old/task', *, status='completed', execution=False):
    native = write(root, name + '/INCAR', 'ENCUT = 520\n')
    write(root, name + '/POSCAR', 'fictional original structure\n')
    write(root, name + '/attempts/001/INCAR', 'ENCUT = 480\n')
    if status is not None:
        record = {'task_uuid': '58fce23e-a63f-4bbf-b520-f00c4f81e452',
                  'task_slug': 'p1_scf', 'status': status,
                  'submission': {'state': status}, 'dependencies': []}
        if execution:
            record['execution'] = {'path': '.dft/execution/snapshot.json', 'sha256': '1' * 64}
        write(root, name + '/workflow.json', json.dumps(record))
    return native.parent


def test_inventory_reads_unregistered_tree_without_inventing_task_records(root):
    task(root, status=None)
    write(root, 'qe/pw.in', "&CONTROL\n calculation='scf'\n/\n")
    write(root, 'docs/refs/structure/POSCAR', 'reference structure, not a task\n')
    write(root, 'notes/plan.md', '# Initial outline\n')
    write(root, 'copies/plan.md', '# Initial outline\n')
    write(root, '.git/ignored-file', 'not project data')
    (root / 'alias').symlink_to(root / 'old/task', target_is_directory=True)
    before = contents(root)
    result = org.inventory(root)
    assert contents(root) == before
    assert not list(root.rglob('workflow.json')) and not (root / '.dft').exists()
    assert {t['path'] for t in result['tasks']} == {'old/task', 'qe'}
    assert all(t['state'] == 'unknown' and t['scientific_acceptance'] == 'unverified'
               for t in result['tasks'])
    assert ['copies/plan.md', 'notes/plan.md'] in result['identical_documents']
    assert result['symlinks'] == ['alias']
    assert all('.git' not in d['path'] for d in result['documents'])


@pytest.mark.parametrize('reference', ['task_root:upstream', 'structure_root:upstream'])
def test_scoped_execution_dependency_prevents_path_relocation(root, reference):
    task(root, 'old/upstream')
    downstream = task(root, 'old/downstream')
    ledger = json.loads((downstream / 'workflow.json').read_text())
    ledger['task_slug'] = 'p2_band'
    ledger['dependencies'] = [{'task_ref': reference}]
    (downstream / 'workflow.json').write_text(json.dumps(ledger))
    request = spec('old/upstream', 'sample/bands/03_scf', inactive=[proof(root, 'old/upstream')])
    result = org.preview(root, request)
    assert result['status'] == 'needs_review'
    assert any('dependency' in reason for reason in result['moves'][0]['blockers'])
    assert (root / 'old/upstream/INCAR').is_file()


def test_document_move_repairs_references_retains_originals_and_is_byte_idempotent(root):
    note = write(root, 'old_notes/outline.md', '# Original scientific outline\n')
    script = write(root, 'old_notes/open.sh', 'cat old_notes/outline.md\n')
    script.chmod(0o755)
    readme = write(root, 'README.md', 'Read old_notes/outline.md for the original outline.\n')
    original = contents(root)
    changes = [{'path': p.relative_to(root).as_posix(), 'old': 'old_notes/outline.md',
                'new': 'route/docs/sources/notes/outline.md', 'sha256': sha(p)}
               for p in (script, readme)]
    request = spec(edits=changes)
    preview = org.preview(root, request)
    assert preview['status'] == 'ready' and contents(root) == original
    assert not (root / '.dft').exists()
    assert all(ref['resolved'] for ref in preview['references'])
    result = org.apply(root, request, preview['sha256'])
    assert result['status'] == 'complete'
    assert not (root / 'old_notes').exists()
    target = root / 'route/docs/sources/notes'
    assert (target / note.name).read_bytes() == original['old_notes/outline.md']
    assert (target / 'open.sh').stat().st_mode & 0o777 == 0o755
    assert (target / 'open.sh').read_text() == 'cat route/docs/sources/notes/outline.md\n'
    assert 'old_notes/outline.md' not in readme.read_text()
    journal = root / '.dft/organization/tidy_notes'
    assert (journal / 'originals/0/outline.md').read_bytes() == original['old_notes/outline.md']
    assert (journal / 'originals/0/open.sh').read_bytes() == original['old_notes/open.sh']
    assert (journal / 'text-originals' / hashlib.sha256(b'README.md').hexdigest()).read_bytes() == original['README.md']
    assert (journal / 'journal.json').stat().st_mode & 0o777 == 0o600
    assert journal.stat().st_mode & 0o777 == 0o700
    assert '.dft/' in (root / '.gitignore').read_text().splitlines()
    settled = contents(root)
    assert org.apply(root, request, preview['sha256'])['status'] == 'complete'
    assert org.check(root, request['id'])['issues'] == []
    assert contents(root) == settled


@pytest.mark.parametrize('change', ['source', 'destination', 'reference', 'preview_hash'])
def test_preview_changes_never_overwrite_files(root, change):
    note = write(root, 'old_notes/outline.md', 'original\n')
    link = write(root, 'README.md', 'old_notes/outline.md\n')
    request = spec(edits=[{'path': 'README.md', 'old': 'old_notes/outline.md',
                          'new': 'route/docs/sources/notes/outline.md', 'sha256': sha(link)}])
    preview = org.preview(root, request)
    expected = preview['sha256']
    if change == 'source':
        note.write_text('new source content\n')
    elif change == 'destination':
        write(root, 'route/docs/sources/notes/outline.md', 'unrelated destination\n')
    elif change == 'reference':
        link.write_text('manual reference edit\n')
    else:
        expected = '0' * 64
    before = contents(root)
    with pytest.raises(ValueError):
        org.apply(root, request, expected)
    assert contents(root) == before and note.exists()
    assert not (root / '.dft/organization').exists()


def test_existing_destination_is_blocked_and_never_merged(root):
    write(root, 'old_notes/outline.md', 'original\n')
    write(root, 'route/docs/sources/notes/other.md', 'independent\n')
    request = spec()
    before = contents(root)
    preview = org.preview(root, request)
    assert preview['status'] == 'needs_review' and preview['moves'][0]['blockers']
    assert org.apply(root, request, preview['sha256'])['status'] == 'needs_review'
    assert contents(root) == before


@pytest.mark.parametrize('reference', ['incoming_symlink', 'nested_symlink', 'native_input'])
def test_unsafe_references_block_relocation_without_mutation(root, reference):
    write(root, 'old_notes/outline.md', 'original\n')
    if reference == 'incoming_symlink':
        (root / 'alias').symlink_to(root / 'old_notes', target_is_directory=True)
    elif reference == 'nested_symlink':
        target = write(root, 'outside.md', 'external note\n')
        (root / 'old_notes/alias.md').symlink_to(target)
    else:
        write(root, 'calculation/pw.in', "&CONTROL\n outdir='old_notes/scratch'\n/\n")
    request = spec()
    before = contents(root)
    preview = org.preview(root, request)
    assert preview['status'] == 'needs_review'
    assert preview['moves'][0]['blockers']
    assert org.apply(root, request, preview['sha256'])['status'] == 'needs_review'
    assert contents(root) == before


@pytest.mark.parametrize('name', ['INCAR', 'pw.in', 'workflow.json', 'attempts/001/note.md'])
def test_generic_reference_edits_cannot_rewrite_native_or_execution_snapshots(root, name):
    path = write(root, 'calculation/' + name, 'old/location/input\n')
    request = {'id': 'unsafe_edit', 'edits': [{'path': path.relative_to(root).as_posix(),
               'old': 'old/location/input', 'new': 'new/location/input', 'sha256': sha(path)}]}
    before = contents(root)
    with pytest.raises(ValueError):
        org.preview(root, request)
    assert contents(root) == before


@pytest.mark.parametrize('kind', ['unrecorded', 'active', 'paired', 'expired', 'invalid_proof'])
def test_calculation_movement_requires_valid_inactivity_and_unbound_state(root, kind):
    task(root, status=None if kind == 'unrecorded' else ('running' if kind == 'active' else 'completed'),
         execution=kind == 'paired')
    request = spec('old/task', 'route/03_scf/task')
    if kind != 'unrecorded':
        request['inactive'] = [proof(root, 'old/task', age=3601 if kind == 'expired' else 0)]
        if kind == 'invalid_proof':
            request['inactive'][0]['sha256'] = '0' * 64
    before = contents(root)
    preview = org.preview(root, request)
    assert preview['status'] == 'needs_review' and preview['moves'][0]['blockers']
    assert org.apply(root, request, preview['sha256'])['status'] == 'needs_review'
    assert contents(root) == before and (root / 'old/task').is_dir()


@pytest.mark.parametrize('recorded', [False, True])
def test_inactive_calculation_move_preserves_uuid_native_inputs_and_attempts(root, recorded):
    source = task(root, status='completed' if recorded else None)
    before = contents(source)
    request = spec('old/task', 'route/03_scf/task', inactive=[proof(root, 'old/task')])
    preview = org.preview(root, request)
    assert preview['status'] == 'ready'
    assert org.apply(root, request, preview['sha256'])['status'] == 'complete'
    target = root / 'route/03_scf/task'
    assert contents(target) == before
    assert contents(root / '.dft/organization/tidy_notes/originals/0') == before
    assert (target / 'workflow.json').exists() is recorded
    if recorded:
        assert json.loads((target / 'workflow.json').read_text())['task_uuid'] == '58fce23e-a63f-4bbf-b520-f00c4f81e452'
    else:
        assert org.inventory(root)['tasks'][0]['state'] == 'unknown'


@pytest.mark.parametrize('failure', ['copy', 'install_rename'])
def test_interruption_preserves_bytes_blocks_execution_and_resumes(root, monkeypatch, failure):
    source = task(root)
    original = contents(source)
    request = spec('old/task', 'route/03_scf/task', inactive=[proof(root, 'old/task')])
    preview = org.preview(root, request)
    target = root / 'route/03_scf/task'
    if failure == 'copy':
        copy = org._copy
        def fail_copy(*args):
            copy(*args)
            raise OSError('simulated interrupted copy')
        monkeypatch.setattr(org, '_copy', fail_copy)
    else:
        rename = org.os.rename
        def fail_install(src, dst):
            if Path(dst) == target:
                raise OSError('simulated interrupted installation')
            return rename(src, dst)
        monkeypatch.setattr(org.os, 'rename', fail_install)
    with pytest.raises(OSError):
        org.apply(root, request, preview['sha256'])
    report = org.check(root, request['id'])
    assert report['status'] == 'needs_review' and report['issues']
    retained = source if source.exists() else root / '.dft/organization/tidy_notes/originals/0'
    assert contents(retained) == original
    assert not target.exists()
    with pytest.raises(ValueError):
        org.guard_execution(root, source)
    with pytest.raises(ValueError):
        org.guard_execution(root, target)
    org.guard_execution(root, root / 'unrelated/task')
    monkeypatch.undo()
    assert org.apply(root, request, preview['sha256'])['status'] == 'complete'
    assert contents(target) == original
    org.guard_execution(root, target)


def test_resume_detects_destination_conflict_and_check_detects_later_tampering(root, monkeypatch):
    write(root, 'old_notes/outline.md', 'original\n')
    request = spec()
    preview = org.preview(root, request)
    target = root / request['moves'][0]['target']
    rename = org.os.rename
    def fail_install(src, dst):
        if Path(dst) == target:
            raise OSError('simulated interruption')
        return rename(src, dst)
    monkeypatch.setattr(org.os, 'rename', fail_install)
    with pytest.raises(OSError):
        org.apply(root, request, preview['sha256'])
    monkeypatch.undo()
    outsider = write(root, target.relative_to(root).as_posix() + '/outline.md', 'other user content\n')
    with pytest.raises(ValueError):
        org.apply(root, request, preview['sha256'])
    assert outsider.read_text() == 'other user content\n'
    outsider.unlink()
    target.rmdir()
    assert org.apply(root, request, preview['sha256'])['status'] == 'complete'
    (target / 'outline.md').write_text('post-migration edit\n')
    assert org.check(root, request['id'])['status'] == 'needs_review'
    assert org.apply(root, request, preview['sha256'])['status'] == 'needs_review'
    assert (target / 'outline.md').read_text() == 'post-migration edit\n'


def test_interrupted_task_requires_refreshed_inactivity_before_source_is_retained(root, monkeypatch):
    source = task(root)
    request = spec('old/task', 'route/03_scf/task', inactive=[proof(root, 'old/task')])
    preview = org.preview(root, request)
    copy = org._copy
    def interrupt(*args):
        copy(*args)
        raise OSError('simulated interruption before original retention')
    monkeypatch.setattr(org, '_copy', interrupt)
    with pytest.raises(OSError):
        org.apply(root, request, preview['sha256'])
    monkeypatch.undo()
    request['inactive'] = [proof(root, 'old/task', age=7200)]
    before = contents(source)
    with pytest.raises(ValueError):
        org.apply(root, request, preview['sha256'])
    assert contents(source) == before
    request['inactive'] = [proof(root, 'old/task')]
    assert org.apply(root, request, preview['sha256'])['status'] == 'complete'
    assert contents(root / 'route/03_scf/task') == before


def test_corrupt_staged_copy_cannot_replace_verified_source(root, monkeypatch):
    source = write(root, 'old_notes/outline.md', 'original\n')
    request = spec()
    preview = org.preview(root, request)
    copy = org.shutil.copy2
    def corrupt(src, dst, *args, **kwargs):
        result = copy(src, dst, *args, **kwargs)
        Path(dst).write_text('corrupted in transfer\n')
        return result
    monkeypatch.setattr(org.shutil, 'copy2', corrupt)
    with pytest.raises(ValueError):
        org.apply(root, request, preview['sha256'])
    assert source.read_text() == 'original\n'
    assert not (root / request['moves'][0]['target']).exists()
    assert org.check(root, request['id'])['status'] == 'needs_review'
    monkeypatch.undo()
    assert org.apply(root, request, preview['sha256'])['status'] == 'complete'
    assert (root / request['moves'][0]['target'] / 'outline.md').read_text() == 'original\n'


@pytest.mark.parametrize('alias', ['task_ref', 'task_id', 'path'])
def test_bare_slug_dependency_blocks_incoming_task_relocation(root, alias):
    task(root)
    dependent = task(root, 'later/task')
    workflow = json.loads((dependent / 'workflow.json').read_text())
    workflow.update(task_uuid='399ba013-844f-4e8d-a178-c24aef0b1cbb', task_slug='p2_band',
                    dependencies=[{alias: 'p1_scf'}])
    (dependent / 'workflow.json').write_text(json.dumps(workflow))
    request = spec('old/task', 'route/03_scf/task', inactive=[proof(root, 'old/task')])
    before = contents(root)
    preview = org.preview(root, request)
    assert preview['status'] == 'needs_review'
    assert org.apply(root, request, preview['sha256'])['status'] == 'needs_review'
    assert contents(root) == before


def test_partial_scope_preserves_blocked_task_and_only_applies_independent_notes(root):
    source = task(root, status='running')
    original_task = contents(source)
    write(root, 'old_notes/outline.md', 'independent notes\n')
    request = spec()
    request['moves'].append({'source': 'old/task', 'target': 'route/03_scf/task'})
    preview = org.preview(root, request)
    assert preview['status'] == 'needs_review'
    result = org.apply(root, request, preview['sha256'])
    assert result['status'] == 'needs_review'
    assert contents(source) == original_task
    assert not (root / 'route/03_scf/task').exists()
    assert (root / 'route/docs/sources/notes/outline.md').read_text() == 'independent notes\n'
    assert any(mapping['preserved'] for mapping in result['mapping'])
    settled = contents(root)
    assert org.apply(root, request, preview['sha256'])['status'] == 'needs_review'
    assert contents(root) == settled


@pytest.mark.parametrize('reference', ['cd oldtask\n', '[run](oldtask)\n'])
def test_bare_project_root_directory_references_block_movement(root, reference):
    write(root, 'oldtask/notes.md', 'task notes\n')
    write(root, 'README.md', reference)
    request = spec('oldtask', 'route/03_task')
    before = contents(root)
    preview = org.preview(root, request)
    assert preview['status'] == 'needs_review'
    assert any(ref['file'] == 'README.md' and not ref['resolved'] for ref in preview['references'])
    assert org.apply(root, request, preview['sha256'])['status'] == 'needs_review'
    assert contents(root) == before


@pytest.mark.parametrize('manifest,path', [('copies', 'sample/03_scf/scripts/plot.py'),
                                         ('publications', 'analysis/figures/final.svg')])
def test_paired_reproduction_and_publication_bindings_block_generic_relocation(root, manifest, path):
    write(root, 'dft-project.json', json.dumps({'schema_version': 1, 'storage_role': 'local', 'routes': []}))
    item = write(root, path, 'selected immutable copy\n')
    write(root, f'.dft/{manifest}.json', json.dumps({path: {'sha256': sha(item)}}))
    request = spec(str(Path(path).parent), 'reorganized/artifacts')
    before = contents(root)
    preview = org.preview(root, request)
    assert preview['status'] == 'needs_review'
    assert preview['moves'][0]['blockers']
    assert org.apply(root, request, preview['sha256'])['status'] == 'needs_review'
    assert contents(root) == before


@pytest.mark.parametrize('filename', ['structure.xyz', 'submit.sh'])
def test_custom_declared_execution_inputs_and_launchers_cannot_be_generically_edited(root, filename):
    source = task(root)
    item = write(root, 'old/task/' + filename, 'old/location/input\n')
    workflow = json.loads((source / 'workflow.json').read_text())
    workflow.update(inputs={'files': [{'path': 'structure.xyz', 'base': 'task_root'}]},
                    job={'script': 'task_root:submit.sh'})
    (source / 'workflow.json').write_text(json.dumps(workflow))
    request = {'id': 'edit_execution', 'edits': [{'path': item.relative_to(root).as_posix(),
               'old': 'old/location/input', 'new': 'new/location/input', 'sha256': sha(item)}],
               'inactive': [proof(root, 'old/task')]}
    before = contents(root)
    with pytest.raises(ValueError, match='declared execution'):
        org.preview(root, request)
    assert contents(root) == before


def test_declared_input_ownership_requires_whole_task_move(root):
    source = task(root)
    item = write(root, 'old/task/structure.xyz', 'fictional geometry\n')
    workflow = json.loads((source / 'workflow.json').read_text())
    workflow['inputs'] = {'files': [{'path': 'structure.xyz', 'base': 'task_root'}]}
    (source / 'workflow.json').write_text(json.dumps(workflow))
    inactive = [proof(root, 'old/task')]
    request = spec('old/task/structure.xyz', 'shared/structure.xyz', inactive=inactive)
    before = contents(root)
    preview = org.preview(root, request)
    assert preview['status'] == 'needs_review'
    assert org.apply(root, request, preview['sha256'])['status'] == 'needs_review'
    assert contents(root) == before and item.exists()
    original_task = contents(source)
    whole = spec('old/task', 'route/03_scf/task', inactive=inactive)
    preview = org.preview(root, whole)
    assert preview['status'] == 'ready'
    assert org.apply(root, whole, preview['sha256'])['status'] == 'complete'
    assert contents(root / 'route/03_scf/task') == original_task


def test_registered_route_view_failure_resumes_once_without_touching_moved_native_files(root, monkeypatch):
    p.init_project(root, 'routes')
    route = p.register_route(root, 'sample', 'si', 'bulk')
    source = task(root, 'sample/03_old')
    write(root, 'sample/03_old/README.md', '# Task stage\n\nHuman interpretation stays intact.\n')
    before_task = contents(source)
    root_readme = write(root, 'README.md', '# Project\n\nSee sample/03_old/README.md.\n')
    route_readme = write(root, 'sample/README.md', '# Route\n\nSee 03_old/README.md.\n')
    original_log = (route / 'docs/log.md').read_text()
    request = spec('sample/03_old', 'sample/03_scf', inactive=[proof(root, 'sample/03_old')], edits=[
        {'path': 'README.md', 'old': 'sample/03_old/README.md', 'new': 'sample/03_scf/README.md', 'sha256': sha(root_readme)},
        {'path': 'sample/README.md', 'old': '03_old/README.md', 'new': '03_scf/README.md', 'sha256': sha(route_readme)},
    ])
    preview = org.preview(root, request)
    assert preview['status'] == 'ready'
    refresh = readmes.refresh
    calls = 0
    def fail_once(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError('simulated view-generation interruption')
        return refresh(*args, **kwargs)
    monkeypatch.setattr(readmes, 'refresh', fail_once)
    with pytest.raises(OSError):
        org.apply(root, request, preview['sha256'])
    journal = root / '.dft/organization/tidy_notes/journal.json'
    assert json.loads(journal.read_text())['state'] == 'views_pending'
    assert org.check(root, request['id'])['status'] == 'needs_review'
    with pytest.raises(ValueError):
        org.guard_execution(root, root / 'sample/03_scf')
    assert contents(root / 'sample/03_scf') == before_task
    assert org.apply(root, request, preview['sha256'])['status'] == 'complete'
    assert contents(root / 'sample/03_scf') == before_task
    assert contents(root / '.dft/organization/tidy_notes/originals/0') == before_task
    for document in (root_readme, route_readme):
        assert '<!-- dft-view:start -->' in document.read_text()
        assert '03_scf' in document.read_text()
    log = (route / 'docs/log.md').read_text()
    assert log.startswith(original_log.rstrip())
    assert log.count(':start -->') == 1
    settled = contents(root)
    assert org.apply(root, request, preview['sha256'])['status'] == 'complete'
    assert contents(root) == settled
    org.guard_execution(root, root / 'sample/03_scf')


def test_cli_inventory_preview_apply_and_check(root, capsys):
    write(root, 'old_notes/outline.md', 'original\n')
    request = spec()
    spec_file = root.parent / 'organization-spec.json'
    spec_file.write_text(json.dumps(request))
    base = ['--project-root', str(root)]
    before = contents(root)
    assert dft_project.main(['organize-inventory', *base]) == 0
    assert json.loads(capsys.readouterr().out)['files'] == 1
    assert dft_project.main(['organize-preview', *base, '--spec', str(spec_file)]) == 0
    preview = json.loads(capsys.readouterr().out)
    assert contents(root) == before
    assert dft_project.main(['organize-apply', *base, '--spec', str(spec_file),
                             '--expected-sha256', preview['sha256']]) == 0
    assert json.loads(capsys.readouterr().out)['status'] == 'complete'
    assert dft_project.main(['organize-check', *base, '--key', request['id']]) == 0
    assert json.loads(capsys.readouterr().out)['issues'] == []
