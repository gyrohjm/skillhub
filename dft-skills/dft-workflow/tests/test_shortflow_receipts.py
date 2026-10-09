"""Regression cases at the scheduler side-effect boundary (no real jobs)."""
import json
from types import SimpleNamespace
import pytest
import canonical_workflow as cw
import resource_preflight as rp
from test_canonical_workflow import submission_task_fixture


def cached_task(tmp_path, monkeypatch):
    project, root = submission_task_fixture(tmp_path)
    profile = json.loads((root / 'workflow.json').read_text())['resources']
    record = {'cache_status': 'ready', 'approved_profile': profile}
    monkeypatch.setattr(rp, 'load_cached_preflight', lambda *a, **k: record)
    return root


def test_durable_receipt_recovers_failed_ledger_without_second_job(tmp_path, monkeypatch):
    root = cached_task(tmp_path, monkeypatch)
    jobs = []
    def runner(argv, **kwargs):
        if argv[0] == 'sbatch':
            jobs.append(tuple(argv))
            return SimpleNamespace(returncode=0, stdout='12345\n', stderr='')
        assert argv[:2] == ['bash', '-n']
        return SimpleNamespace(returncode=0, stdout='', stderr='')
    original = cw._write_submission_workflow
    def fail_ledger(*args, **kwargs):
        raise OSError('simulated ledger persistence failure')
    monkeypatch.setattr(cw, '_write_submission_workflow', fail_ledger)
    with pytest.raises((OSError, cw.WorkflowError)):
        cw.submit_task(root, runner=runner)
    assert len(jobs) == 1
    assert (root / 'attempts/attempt-001/sbatch.receipt.json').is_file()
    monkeypatch.setattr(cw, '_write_submission_workflow', original)
    assert cw.submit_task(root, runner=runner) == '12345'
    assert len(jobs) == 1
    assert json.loads((root / 'workflow.json').read_text())['submission']['job_id'] == '12345'


@pytest.mark.parametrize('reply', ['not-a-job-id\n', ''])
def test_ambiguous_submission_never_becomes_a_job_id_or_auto_retries(tmp_path, monkeypatch, reply):
    root = cached_task(tmp_path, monkeypatch)
    jobs = []
    def runner(argv, **kwargs):
        if argv[0] == 'sbatch':
            jobs.append(tuple(argv))
            return SimpleNamespace(returncode=0, stdout=reply, stderr='')
        assert argv[:2] == ['bash', '-n']
        return SimpleNamespace(returncode=0, stdout='', stderr='')
    with pytest.raises(cw.WorkflowError):
        cw.submit_task(root, runner=runner)
    with pytest.raises(cw.WorkflowError):
        cw.submit_task(root, runner=runner)
    assert len(jobs) == 1
    assert json.loads((root / 'workflow.json').read_text())['submission']['job_id'] is None


def test_major_input_change_during_dependency_check_blocks_scheduler(tmp_path, monkeypatch):
    root = cached_task(tmp_path, monkeypatch)
    def gate(task):
        path = root / 'INCAR'
        path.write_text(path.read_text() + '\nGGA=PS\n')
        return {'verdict': 'ADVANCE'}
    monkeypatch.setattr(cw, 'evaluate_dependencies', gate)
    jobs = []
    def runner(argv, **kwargs):
        if argv[0] == 'sbatch':
            jobs.append(tuple(argv))
            return SimpleNamespace(returncode=0, stdout='12345\n', stderr='')
        return SimpleNamespace(returncode=0, stdout='', stderr='')
    with pytest.raises(cw.WorkflowError):
        cw.submit_task(root, runner=runner)
    assert jobs == []
