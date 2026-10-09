import copy
import json
from types import SimpleNamespace
import pytest
import resource_preflight as rp


def batch_output(partition="compute",executable="vasp_std",*,activation_rc=0):
    return rp.format_batched_probe_output({
        "scheduler_command":{"returncode":0,"detail":"/usr/bin/sbatch"},
        "target_partition":{"returncode":0,"detail":partition+"|up"},
        "approved_activation":{"returncode":activation_rc,"detail":""},
        "approved_executable":{"returncode":0,"detail":"/bin/"+executable}})


def profile(partition="compute"):
    return {"cluster":"test","partition":partition,"executable":"vasp_std",
        "activation_command":"source /opt/env.sh","nodes":1}


def test_batched_first_probe_and_keyed_a_b_a_cache(tmp_path):
    calls=[]
    def get(p):
        cached=rp.load_cached_preflight(tmp_path,profile=p)
        if cached and cached["cache_status"]=="ready": return cached
        def runner(argv,**kwargs):
            calls.append(argv)
            return SimpleNamespace(returncode=0,stdout=batch_output(p["partition"]),stderr="")
        result=rp.lightweight_preflight(p,runner)
        rp._store_cached_preflight(tmp_path,result)
        return result
    assert get(profile())["cache_status"]=="ready"
    assert len(calls)==1
    assert get(profile("other"))["cache_status"]=="ready"
    assert get(profile())["cache_status"]=="ready"
    assert len(calls)==2
    changed=profile()
    changed["engine_parameters"]={"ENCUT":700}
    assert get(changed)["cache_status"]=="ready"
    assert len(calls)==2
    rp.invalidate_preflight(tmp_path,"activation_failure",profile=profile())
    assert rp.load_cached_preflight(tmp_path,profile=profile())["cache_status"]=="invalidated"
    assert rp.load_cached_preflight(tmp_path,profile=profile("other"))["cache_status"]=="ready"


@pytest.mark.parametrize("output",["", "unframed success", "DFT_PREFLIGHT_V1 BEGIN scheduler_command\n"])
def test_missing_frames_fail_closed(output):
    result=rp.lightweight_preflight(profile(),lambda *a,**k:SimpleNamespace(returncode=0,stdout=output,stderr=""))
    assert result["cache_status"]!="ready"


def test_failed_activation_cannot_be_hidden_by_executable_success():
    result=rp.lightweight_preflight(profile(),lambda *a,**k:SimpleNamespace(returncode=0,stdout=batch_output(activation_rc=1),stderr=""))
    assert result["cache_status"]=="stale"
    assert result["invalidation_reason"]=="activation_failure"


def test_ready_cache_with_failed_evidence_is_rejected(tmp_path):
    result=rp.lightweight_preflight(profile(),lambda *a,**k:SimpleNamespace(returncode=0,stdout=batch_output(),stderr=""))
    result["checks"]["approved_activation"]["status"]="failed"
    with pytest.raises(rp.WorkflowError):
        rp._store_cached_preflight(tmp_path,result)


@pytest.mark.parametrize('activation_ok',[True,False])
def test_actual_bash_uses_one_activation_environment(tmp_path,activation_ok):
    import subprocess
    import shlex
    from pathlib import Path
    bash=Path('D:/1Softwares/Git/bin/bash.exe')
    if not bash.is_file():
        import shutil
        located=shutil.which('bash')
        if not located: pytest.skip('bash unavailable')
        bash=Path(located)
    activation=tmp_path/'activation.sh'
    activation.write_text('vasp_std() { :; }\n' if activation_ok else 'return 1\n')
    p=profile()
    p['activation_command']='source '+shlex.quote(activation.as_posix())
    calls=[]
    def runner(argv,**kwargs):
        calls.append(argv)
        prefix="sbatch() { :; }; sinfo() { printf 'compute|up\\n'; };\n"
        return subprocess.run([str(bash),'--noprofile','--norc','-c',prefix+argv[2]],capture_output=True,text=True,timeout=10)
    result=rp.lightweight_preflight(p,runner)
    assert len(calls)==1
    assert result['cache_status']==('ready' if activation_ok else 'stale')
    if not activation_ok:
        assert result['invalidation_reason']=='activation_failure'
        assert result['checks']['approved_executable']['status']=='failed'
