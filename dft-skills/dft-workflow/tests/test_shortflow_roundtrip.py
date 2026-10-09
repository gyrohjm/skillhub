"""Cross-package task-mode draft, real approval, and selected-template roundtrip."""
import json
import sys
from pathlib import Path
from argparse import Namespace
import pytest
import canonical_workflow as cw
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "dft-design" / "tests"))
from test_task_mode_20260910 import task_design
from test_canonical_workflow import base_project, resource_document, vasp_profile, qe_profile, write_vasp_inputs


@pytest.mark.parametrize("engine,script", [("vasp","vasp.sh"),("quantum-espresso","qe.sh")])
@pytest.mark.parametrize("template", [False,True])
@pytest.mark.parametrize("layout", ["legacy", "routes"])
def test_task_mode_draft_approval_roundtrip(tmp_path, monkeypatch, engine, script, template, layout):
    root = base_project(tmp_path)
    design = task_design(engine)
    design["execution_plan"]["tasks"][0].pop("job_script")
    source = root / "inputs/p1_scf"
    if engine == "vasp":
        write_vasp_inputs(source)
        (source / "INCAR").write_text("ENCUT=520\nISMEAR=0\nSIGMA=0.05\n")
        profile = vasp_profile()
    else:
        source.mkdir(parents=True)
        (source / "pw.in").write_text("&CONTROL\n calculation='scf',\n/\n&SYSTEM\n ecutwfc=80, ecutrho=640, occupations='smearing', degauss=0.01, nat=1, ntyp=1,\n/\nATOMIC_SPECIES\nSi 28.085 Si.upf\nCELL_PARAMETERS angstrom\n3 0 0\n0 3 0\n0 0 3\nATOMIC_POSITIONS crystal\nSi 0 0 0\nK_POINTS automatic\n6 6 1 0 0 0\n")
        (source / "Si.upf").write_text("supplied-test-pseudopotential")
        profile = qe_profile()
        import copy
        dependent=copy.deepcopy(design['execution_plan']['tasks'][0])
        dependent.update(task_slug='p2_band',stage='band',dependencies=['p1_scf'])
        design['calculation_matrix'][0]['stages'].append('band')
        design['engine_stage_envelopes'][0]['completion_gates']['band']='engine normal termination'
        dependent['inputs'][0]={'name':'pw.in','mode':'recipe','source_task':'p1_scf','artifact':'next.in'}
        design['execution_plan']['tasks'].append(dependent)
    selected = "#!/bin/bash\n#SBATCH --partition=compute\n# supplied template\ntrue\n"
    if template:
        (root / "templates").mkdir()
        (root / "templates" / script).write_text(selected)
        for task in design["execution_plan"]["tasks"]:
            task["job_script"] = "templates/" + script
        for field in ("launch_template","nodes","ntasks_per_node","cpus_per_task"):
            profile.pop(field, None)  # full supplied script does not need renderer-only fields
    resource_document(root, {"approved-profile":profile})
    route = None
    if layout == "routes":
        from dft_contracts.project import init_project, register_route
        init_project(root, "routes")
        route = register_route(root, "sample/benchmark", "si", "bulk")
        design_path = route / "docs/calculation_design.json"
        for task in design['execution_plan']['tasks']:
            task['directory'] = '03_scf/reference' if task['task_slug']=='p1_scf' else '05_band'
    else:
        design_path = root / "plans/si/bulk/calculation_design.json"
    design_path.parent.mkdir(parents=True, exist_ok=True)
    design_path.write_text(json.dumps(design))
    leaves = cw.initialize_workflow_tree(root,"si","bulk",design_path=design_path,draft=True,
                                         route=str(route.relative_to(root)) if route else None)
    if route:
        assert leaves[0] == route / '03_scf/reference'
    leaf=leaves[0]
    assert all((item/script).is_file() for item in leaves)
    if engine=='quantum-espresso':
        assert not (leaves[1]/'pw.in').exists()
    assert (leaf / script).is_file()
    if template:
        assert (leaf / script).read_text() == selected
    before = {p:p.read_bytes() for p in leaf.iterdir() if p.name not in {"workflow.json","README.md"}}
    cd = cw._load_design_verifier()
    args = Namespace(project=route or root,composition_slug="si",structure_slug="bulk",
        design=design_path,reviewer="test-user",scope=["M1"],note="approve supplied parameters")
    sync = json.dumps({"design_id":design["design_id"],"revision":design["revision"]})
    (design_path.parent / ("plan.md" if route else "README.md")).write_text(f"<!-- dft-design-sync: {sync} -->\n# Task\n")
    (design_path.parent / "history.jsonl").write_text("")
    # Use the real approval CLI implementation, not a fabricated event.
    assert cd.cmd_approve(args) == 0
    history = design_path.parent / "history.jsonl"
    events = [json.loads(line) for line in history.read_text().splitlines() if line.strip()]
    event = events[-1]
    cw.bind_approval(root,"si","bulk",history_path=history,event_id=event["event_id"],
                     route=str(route.relative_to(root)) if route else None)
    assert all(p.read_bytes() == data for p,data in before.items())
    w = json.loads((leaf / "workflow.json").read_text())
    assert w["status"] == "prepared"
    assert w["job"]["script"] == "task_root:" + script
    assert w["completion"]["scientifically_accepted"] is False
    assert "Not approved" not in ((route / "03_scf" if route else leaf) / "README.md").read_text()
    approved = event["design_snapshot"]["engine_stage_envelopes"][0]["parameter_selection"]
    assert all(item["status"] == "user_specified" for item in approved.values())
    if engine=='quantum-espresso':
        import resource_preflight as rp
        from types import SimpleNamespace
        (leaf/'next.in').write_bytes((leaf/'pw.in').read_bytes())
        w['status']='completed'
        w['completion'].update(scheduler_complete=True,artifact_complete=True,scientifically_accepted=True)
        w['result']['artifacts']={'next.in':{'path':'next.in','sha256':cw.sha256_file(leaf/'next.in')}}
        (leaf/'workflow.json').write_text(json.dumps(w))
        child=leaves[1]
        child_profile=cw._submission_profile(json.loads((child/'workflow.json').read_text()))
        monkeypatch.setattr(rp,'load_cached_preflight',lambda *a,**k:{'cache_status':'ready','approved_profile':child_profile})
        calls=[]
        def runner(argv,**kwargs):
            calls.append(argv)
            return SimpleNamespace(returncode=0,stdout='12345\n' if argv[0]=='sbatch' else '',stderr='')
        assert cw.submit_task(child,runner=runner)=='12345'
        assert (child/'pw.in').read_bytes()==(leaf/'next.in').read_bytes()
        assert len([item for item in calls if item[0]=='sbatch'])==1
