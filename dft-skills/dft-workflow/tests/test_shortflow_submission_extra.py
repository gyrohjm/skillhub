import json
from types import SimpleNamespace
import pytest
import canonical_workflow as cw
from test_shortflow_receipts import cached_task


@pytest.mark.parametrize("script",["vasp.sh","qe.sh","job.sh","scripts/vasp.sh"])
def test_actual_script_is_used_for_scheduler_and_snapshot(tmp_path,monkeypatch,script):
    root = cached_task(tmp_path,monkeypatch)
    original = root/"job.sh"
    if script != "job.sh":
        target = root/script
        target.parent.mkdir(parents=True,exist_ok=True)
        original.rename(target)
    w = json.loads((root/"workflow.json").read_text())
    w["job"]["script"]="task_root:"+script
    (root/"workflow.json").write_text(json.dumps(w))
    calls=[]
    def runner(argv,**kwargs):
        calls.append(argv)
        return SimpleNamespace(returncode=0,stdout="12345\n" if argv[0]=="sbatch" else "",stderr="")
    assert cw.submit_task(root,runner=runner)=="12345"
    assert calls == [["bash","-n",script],["sbatch","--parsable",script]]
    assert (root/"attempts/attempt-001/submission_snapshot"/script).is_file()


def test_concurrent_submit_is_blocked_by_exclusive_lock(tmp_path,monkeypatch):
    root=cached_task(tmp_path,monkeypatch)
    jobs=[]
    def runner(argv,**kwargs):
        if argv[0]=="sbatch":
            with pytest.raises(cw.WorkflowError,match="locked"):
                cw.submit_task(root,runner=runner)
            jobs.append(argv)
        return SimpleNamespace(returncode=0,stdout="12345\n",stderr="")
    assert cw.submit_task(root,runner=runner)=="12345"
    assert len(jobs)==1 and not (root/".submission.lock").exists()


def test_timeout_requires_reconciliation_before_retry(tmp_path,monkeypatch):
    root=cached_task(tmp_path,monkeypatch)
    jobs=[]
    def runner(argv,**kwargs):
        if argv[0]=="sbatch":
            jobs.append(argv)
            raise TimeoutError("scheduler response lost")
        return SimpleNamespace(returncode=0,stdout="",stderr="")
    with pytest.raises(cw.WorkflowError,match="uncertain"):
        cw.submit_task(root,runner=runner)
    with pytest.raises(cw.WorkflowError,match="reconciliation"):
        cw.submit_task(root,runner=runner)
    assert len(jobs)==1


def test_mutation_during_syntax_check_prevents_submission(tmp_path,monkeypatch):
    root=cached_task(tmp_path,monkeypatch)
    jobs=[]
    def runner(argv,**kwargs):
        if argv[0]=="bash":
            with (root/"INCAR").open("a") as handle: handle.write("\nENCUT=999\n")
        else: jobs.append(argv)
        return SimpleNamespace(returncode=0,stdout="12345\n",stderr="")
    with pytest.raises(cw.WorkflowError,match="changed"):
        cw.submit_task(root,runner=runner)
    assert jobs==[]


def test_science_edit_reuses_environment_and_script_syntax_evidence(tmp_path,monkeypatch):
    import resource_preflight as rp
    from test_shortflow_lifecycle import draft_case, approve_fixture
    project,history,event,design=draft_case(tmp_path)
    root,*_=cw.initialize_workflow_tree(project,"mgb2","ref_struct",design_path=design,draft=True)
    cw.bind_approval(project,"mgb2","ref_struct",history_path=history,event_id=approve_fixture(history,event,design))
    profile=cw._submission_profile(json.loads((root/"workflow.json").read_text()))
    monkeypatch.setattr(rp,"load_cached_preflight",lambda *a,**k: {"cache_status":"ready","approved_profile":profile})
    calls=[]
    monkeypatch.setattr(rp,"lightweight_preflight",lambda *a,**k: pytest.fail("unexpected environment probe"))
    monkeypatch.setattr(rp,"invalidate_preflight",lambda *a,**k: pytest.fail("unrelated rejection invalidated environment"))
    def runner(argv,**kwargs):
        calls.append(argv)
        if argv[0]=="sbatch" and len([c for c in calls if c[0]=="sbatch"])==1:
            return SimpleNamespace(returncode=1,stdout="",stderr="temporary submission rate limit")
        return SimpleNamespace(returncode=0,stdout="12345\n",stderr="")
    with pytest.raises(cw.WorkflowError,match="rejected"):
        cw.submit_task(root,runner=runner)
    w=json.loads((root/"workflow.json").read_text())
    w["status"]="prepared"
    w.pop("technical_failure",None)
    (root/"workflow.json").write_text(json.dumps(w))
    p=root/"INCAR"
    p.write_text(p.read_text().replace("600","610"))
    assert cw.submit_task(root,runner=runner)=="12345"
    assert len([c for c in calls if c[:2]==["bash","-n"]])==1
    assert len([c for c in calls if c[0]=="sbatch"])==2


def test_concurrent_ledger_edit_is_preserved_not_overwritten_by_syntax_cache(tmp_path,monkeypatch):
    root=cached_task(tmp_path,monkeypatch)
    def runner(argv,**kwargs):
        assert argv[:2]==["bash","-n"]
        path=root/"workflow.json"
        w=json.loads(path.read_text())
        w['user_note']='new user edit'
        path.write_text(json.dumps(w))
        return SimpleNamespace(returncode=0,stdout='',stderr='')
    with pytest.raises(cw.WorkflowError,match='workflow changed'):
        cw.submit_task(root,runner=runner)
    assert json.loads((root/'workflow.json').read_text())['user_note']=='new user edit'
