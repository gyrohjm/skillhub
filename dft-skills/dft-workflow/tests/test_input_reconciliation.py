from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

import input_reconciliation as ir  # noqa: E402


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_hash(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _write_vasp_inputs(
    task_root: Path,
    *,
    encut: int = 520,
    nelm: int = 60,
    gga: str = "PE",
    comments: str = "",
    potcar_identity: str = "Mg B",
) -> None:
    task_root.mkdir(parents=True, exist_ok=True)
    (task_root / "INCAR").write_text(
        f"{comments}ENCUT = {encut}\nNELM = {nelm}\nGGA = {gga}\nISMEAR = 0\nSIGMA = 0.05\n",
        encoding="utf-8",
    )
    (task_root / "KPOINTS").write_text(
        "automatic\n0\nGamma\n6 6 6\n0 0 0\n",
        encoding="utf-8",
    )
    (task_root / "POSCAR").write_text(
        "Mg B\n1.0\n1 0 0\n0 1 0\n0 0 1\nMg B\n1 2\nDirect\n"
        "0 0 0\n0 0 0.3\n0 0 0.7\n",
        encoding="utf-8",
    )
    (task_root / "POTCAR").write_text(
        f"TITEL = PAW_PBE {potcar_identity}\n",
        encoding="utf-8",
    )


def _write_qe_input(task_root: Path, *, electron_maxstep: int = 100, ecutwfc: int = 60) -> None:
    task_root.mkdir(parents=True, exist_ok=True)
    (task_root / "scf.in").write_text(
        "&CONTROL\n"
        " calculation = 'scf',\n"
        "/\n"
        "&SYSTEM\n"
        f" ecutwfc = {ecutwfc}, ecutrho = 480, occupations = 'smearing',\n"
        " smearing = 'mv', degauss = 0.02, input_dft = 'PBE',\n"
        "/\n"
        "&ELECTRONS\n"
        f" conv_thr = 1.0d-8, electron_maxstep = {electron_maxstep}, mixing_beta = 0.7,\n"
        "/\n"
        "ATOMIC_SPECIES\n"
        "Mg 24.305 Mg.pbe-n-kjpaw_psl.1.0.0.UPF\n"
        "B 10.81 B.pbe-n-kjpaw_psl.1.0.0.UPF\n"
        "ATOMIC_POSITIONS crystal\n"
        "Mg 0.0 0.0 0.0\n"
        "B 0.0 0.0 0.3\n"
        "B 0.0 0.0 0.7\n"
        "K_POINTS automatic\n6 6 6 0 0 0\n",
        encoding="utf-8",
    )


def _workflow(
    task_root: Path,
    current: dict,
    *,
    state: str = "prepared",
    task_slug: str = "p1_scf",
    attempt_snapshot: dict | None = None,
) -> dict:
    parameters = copy.deepcopy(current["parameters"])
    files = [
        {
            "base": "task_root",
            "path": name,
            "name": name,
            "role": "engine_input",
            "mode": "static",
            "sha256": current["file_hashes"][name],
            "authority": "generated",
        }
        for name in sorted(current["file_hashes"])
    ]
    snapshot = {
        "parameters": copy.deepcopy(parameters),
        "file_semantics": copy.deepcopy(current["file_semantics"]),
        "file_hashes": copy.deepcopy(current["file_hashes"]),
        "parameter_hash": current["parameter_hash"],
    }
    return {
        "schema_version": 2,
        "contract": "dft.workflow.v2",
        "composition_slug": "mgb2",
        "structure_slug": "bulk",
        "task_slug": task_slug,
        "status": state,
        "engine": current["engine"],
        "updated_at": "2026-08-31T00:00:00Z",
        "stage": "scf",
        "design": {
            "design_id": "mgb2_calculation",
            "revision": 1,
            "approval_ref": "workspace_root:plans/mgb2/bulk/history.jsonl#mgb2_calculation:r0001",
            "baseline_parameter_hash": current["parameter_hash"],
            "matrix_id": "M1",
            "engine_parameters": copy.deepcopy(parameters),
        },
        "inputs": {"materialization": "static", "files": files},
        "input_authority": {name: "generated" for name in current["file_hashes"]},
        "parameter_reconciliation": {
            "status": "synchronized",
            "changed_parameters": [],
            "affected_tasks": [],
        },
        "input_snapshot": snapshot,
        "resource_profile": {"ref": "workspace_root:.dft/resource-profile.json#test", "overrides": {}},
        "attempts": (
            [
                {
                    "attempt_id": "attempt-001",
                    "reason": "submitted",
                    "snapshot": copy.deepcopy(attempt_snapshot or snapshot),
                    "job_id": "12345",
                }
            ]
            if attempt_snapshot is not None
            else []
        ),
        "submission": {
            "state": "not_submitted" if state in {"planned", "prepared"} else state,
            "allowed": state in {"submitted", "running", "completed"},
            "job_id": None if state in {"planned", "prepared"} else "12345",
        },
        "completion": {
            "scheduler_complete": state == "completed",
            "artifact_complete": state == "completed",
            "scientifically_accepted": False,
        },
        "lineage": {"derived_from": None, "supersedes": None},
        "history": [{"at": "2026-08-31T00:00:00Z", "status": state}],
    }


def _write_design(project: Path, *, engine: str, parameters: dict, revision: int = 1) -> Path:
    plan_root = project / "plans/mgb2/bulk"
    plan_root.mkdir(parents=True, exist_ok=True)
    design = {
        "schema_version": 2,
        "design_id": "mgb2_calculation",
        "revision": revision,
        "status": "ready_for_review",
        "project_slug": "mgb2",
        "title": "MgB2 calculation",
        "calculation_matrix": [{"id": "M1", "stages": ["scf", "band"], "class": "production"}],
        "engine_stage_envelopes": [
            {
                "matrix_id": "M1",
                "engine": engine,
                "engine_parameters": copy.deepcopy(parameters),
                "parameter_selection": {},
            }
        ],
        "execution_plan": {
            "tasks": [
                {"task_slug": "p1_scf", "matrix_id": "M1", "stage": "scf", "engine": engine},
                {"task_slug": "p2_band", "matrix_id": "M1", "stage": "band", "engine": engine, "dependencies": ["p1_scf"]},
            ]
        },
    }
    path = plan_root / "calculation_design.json"
    path.write_text(json.dumps(design, indent=2) + "\n", encoding="utf-8")
    (plan_root / "README.md").write_text(
        '<!-- dft-design-sync: {"design_id":"mgb2_calculation","revision":1} -->\n# Plan\n',
        encoding="utf-8",
    )
    (plan_root / "history.jsonl").write_text(
        json.dumps({"event_type": "scientific_design_approved", "event_id": "mgb2_calculation:r0001"}) + "\n",
        encoding="utf-8",
    )
    return path


def _make_vasp_task(tmp_path: Path, *, state: str = "prepared", with_descendant: bool = False):
    task_root = tmp_path / "calculations/mgb2/bulk/p1_scf"
    _write_vasp_inputs(task_root)
    current = ir.parse_current_inputs("vasp", task_root)
    design_path = _write_design(tmp_path, engine="vasp", parameters=current["parameters"])
    workflow = _workflow(
        task_root,
        current,
        state=state,
        attempt_snapshot=current if state in {"submitted", "running"} else None,
    )
    (task_root / "workflow.json").write_text(json.dumps(workflow, indent=2) + "\n", encoding="utf-8")
    if with_descendant:
        descendant = task_root.parent / "p2_band"
        descendant.mkdir(parents=True)
        descendant_workflow = _workflow(descendant, current, task_slug="p2_band")
        descendant_workflow["dependencies"] = [
            {"task_ref": "p1_scf", "required_artifacts": [], "gate_status": "awaiting_upstream"}
        ]
        (descendant / "workflow.json").write_text(
            json.dumps(descendant_workflow, indent=2) + "\n", encoding="utf-8"
        )
    return task_root, design_path, current


def _reconciliation_record_paths(task_root: Path, design_path: Path) -> list[Path]:
    return [
        task_root / "workflow.json",
        design_path,
        design_path.parent / "history.jsonl",
        design_path.parent / "README.md",
        task_root / "README.md",
        task_root.parent / "p2_band" / "workflow.json",
    ]


def _capture_bytes(paths: list[Path]) -> dict[Path, bytes | None]:
    return {path: path.read_bytes() if path.exists() else None for path in paths}


def _assert_bytes_unchanged(paths: list[Path], before: dict[Path, bytes | None]) -> None:
    assert _capture_bytes(paths) == before


def test_parse_current_inputs_normalizes_vasp_values_and_hashes(tmp_path: Path) -> None:
    task_root = tmp_path / "p1_scf"
    _write_vasp_inputs(task_root, nelm=120)

    current = ir.parse_current_inputs("vasp", task_root)

    assert current["parameters"]["NELM"] == 120
    assert current["parameters"]["ENCUT"] == 520
    assert current["parameters"]["KPOINTS"] == "6x6x6"
    assert current["file_hashes"]["INCAR"] == _sha256(task_root / "INCAR")
    assert current["file_semantics"]["POSCAR"]["species"] == ["Mg", "B"]


@pytest.mark.parametrize(
    ("engine", "name", "expected"),
    [
        ("vasp", "NELM", "L1"),
        ("vasp", "ENCUT", "L2"),
        ("vasp", "GGA", "L3"),
        ("vasp", "METAGGA", "L3"),
        ("vasp", "LHFCALC", "L3"),
        ("vasp", "ISPIN", "L3"),
        ("vasp", "MAGMOM", "L3"),
        ("vasp", "LSORBIT", "L3"),
        ("vasp", "LNONCOLLINEAR", "L3"),
        ("vasp", "NELECT", "L3"),
        ("vasp", "POSCAR", "L3"),
        ("vasp", "POTCAR", "L3"),
        ("quantum-espresso", "electron_maxstep", "L1"),
        ("quantum-espresso", "mixing_beta", "L1"),
        ("quantum-espresso", "ecutwfc", "L2"),
        ("quantum-espresso", "ecutrho", "L2"),
        ("quantum-espresso", "conv_thr", "L2"),
        ("quantum-espresso", "occupations", "L2"),
        ("quantum-espresso", "smearing", "L2"),
        ("quantum-espresso", "degauss", "L2"),
        ("quantum-espresso", "K_POINTS", "L2"),
        ("quantum-espresso", "input_dft", "L3"),
        ("quantum-espresso", "pseudopotential", "L3"),
        ("quantum-espresso", "species", "L3"),
        ("quantum-espresso", "positions", "L3"),
        ("quantum-espresso", "cell", "L3"),
        ("quantum-espresso", "spin", "L3"),
        ("quantum-espresso", "soc", "L3"),
        ("quantum-espresso", "charge", "L3"),
        ("quantum-espresso", "constraints", "L3"),
    ],
)
def test_classify_change_uses_engine_specific_levels(engine: str, name: str, expected: str) -> None:
    assert ir.classify_change(engine, name, "old", "new") == expected


def test_unknown_parameter_goes_to_agent_not_major_conflict() -> None:
    assert ir.classify_change("vasp", "UNRECOGNIZED_TAG", 1, 2) == "UNKNOWN"


def test_vasp_nelm_edit_is_adopted_without_approval(tmp_path: Path) -> None:
    task_root, design_path, _ = _make_vasp_task(tmp_path)
    incar = task_root / "INCAR"
    incar.write_text(incar.read_text(encoding="utf-8").replace("NELM = 60", "NELM = 120"), encoding="utf-8")

    result = ir.reconcile_task(task_root, design_path, write=True)

    assert result["status"] == "adopted"
    assert result["verdict"] == "ADVANCE"
    assert result["changed_parameters"] == [{"name": "NELM", "old": 60, "new": 120, "impact": "L1"}]
    workflow = json.loads((task_root / "workflow.json").read_text(encoding="utf-8"))
    design = json.loads(design_path.read_text(encoding="utf-8"))
    assert workflow["design"]["engine_parameters"]["NELM"] == 120
    assert design["engine_stage_envelopes"][0]["engine_parameters"]["NELM"] == 120
    assert design["revision"] == 2
    assert workflow["design"]["revision"] == design["revision"]
    assert workflow["design"]["baseline_parameter_hash"] == result["current_parameter_hash"]
    assert workflow["input_authority"]["INCAR"]["authority"] == "user_override"
    assert "user_parameter_override_adopted" in (tmp_path / "plans/mgb2/bulk/history.jsonl").read_text()


def test_vasp_encut_edit_propagates_and_marks_generated_descendant_stale(tmp_path: Path) -> None:
    task_root, design_path, _ = _make_vasp_task(tmp_path, with_descendant=True)
    incar = task_root / "INCAR"
    incar.write_text(incar.read_text(encoding="utf-8").replace("ENCUT = 520", "ENCUT = 600"), encoding="utf-8")

    result = ir.reconcile_task(task_root, design_path, write=True)

    assert result["status"] == "propagated"
    assert result["changed_parameters"] == [{"name": "ENCUT", "old": 520, "new": 600, "impact": "L2"}]
    descendant = json.loads(
        (tmp_path / "calculations/mgb2/bulk/p2_band/workflow.json").read_text(encoding="utf-8")
    )
    assert descendant["parameter_reconciliation"]["status"] == "propagated"
    assert "stale_due_to_upstream_parameter_change" in json.dumps(descendant)


@pytest.mark.parametrize("fail_at", [1, 3, 6])
def test_reconcile_commit_failure_rolls_back_all_planning_records(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fail_at: int
) -> None:
    task_root, design_path, _ = _make_vasp_task(tmp_path, with_descendant=True)
    incar = task_root / "INCAR"
    incar.write_text(
        incar.read_text(encoding="utf-8").replace("ENCUT = 520", "ENCUT = 600"),
        encoding="utf-8",
    )
    record_paths = _reconciliation_record_paths(task_root, design_path)
    before = _capture_bytes(record_paths)
    engine_inputs = [task_root / name for name in ("INCAR", "KPOINTS", "POSCAR", "POTCAR")]
    engine_before = _capture_bytes(engine_inputs)

    calls = 0
    original_commit = getattr(ir, "_commit_staged_file", None)

    def fail_during_commit(staged: Path, target: Path) -> None:
        nonlocal calls
        calls += 1
        if calls == fail_at:
            raise RuntimeError("injected commit failure")
        if original_commit is None:
            raise AssertionError("transaction commit hook was not called")
        original_commit(staged, target)

    monkeypatch.setattr(ir, "_commit_staged_file", fail_during_commit, raising=False)

    with pytest.raises(RuntimeError, match="injected commit failure"):
        ir.reconcile_task(task_root, design_path, write=True)

    assert calls >= fail_at
    _assert_bytes_unchanged(record_paths, before)
    _assert_bytes_unchanged(engine_inputs, engine_before)


def test_reconcile_staging_failure_leaves_all_records_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    task_root, design_path, _ = _make_vasp_task(tmp_path, with_descendant=True)
    incar = task_root / "INCAR"
    incar.write_text(
        incar.read_text(encoding="utf-8").replace("ENCUT = 520", "ENCUT = 600"),
        encoding="utf-8",
    )
    record_paths = _reconciliation_record_paths(task_root, design_path)
    before = _capture_bytes(record_paths)
    engine_inputs = [task_root / name for name in ("INCAR", "KPOINTS", "POSCAR", "POTCAR")]
    engine_before = _capture_bytes(engine_inputs)

    calls = 0
    original_stage = getattr(ir, "_stage_file", None)

    def fail_during_staging(path: Path, content: str) -> Path:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("injected staging failure")
        if original_stage is None:
            raise AssertionError("transaction staging hook was not called")
        return original_stage(path, content)

    monkeypatch.setattr(ir, "_stage_file", fail_during_staging, raising=False)

    with pytest.raises(RuntimeError, match="injected staging failure"):
        ir.reconcile_task(task_root, design_path, write=True)

    assert calls >= 2
    _assert_bytes_unchanged(record_paths, before)
    _assert_bytes_unchanged(engine_inputs, engine_before)


@pytest.mark.parametrize("name", ["GGA", "METAGGA", "LHFCALC", "ISPIN", "MAGMOM", "LSORBIT", "LNONCOLLINEAR", "NELECT"])
def test_vasp_major_changes_pause_branch_and_preserve_input(tmp_path: Path, name: str) -> None:
    task_root, design_path, _ = _make_vasp_task(tmp_path)
    original = (task_root / "INCAR").read_text(encoding="utf-8")
    (task_root / "INCAR").write_text(original + f"{name} = changed\n", encoding="utf-8")

    result = ir.reconcile_task(task_root, design_path, write=True)

    assert result["status"] == "major_conflict"
    assert result["verdict"] == "MAJOR_CONFLICT"
    assert (task_root / "INCAR").read_text(encoding="utf-8") == original + f"{name} = changed\n"
    workflow = json.loads((task_root / "workflow.json").read_text(encoding="utf-8"))
    assert workflow["status"] == "awaiting_user_decision"


def test_poscar_composition_order_and_potcar_identity_are_l3(tmp_path: Path) -> None:
    task_root, _, _ = _make_vasp_task(tmp_path)
    assert ir.classify_change("vasp", "POSCAR", ["Mg", "B"], ["B", "Mg"]) == "L3"
    assert ir.classify_change("vasp", "POTCAR", "Mg B", "Fe Co") == "L3"


def test_qe_local_and_propagating_changes_are_classified(tmp_path: Path) -> None:
    task_root = tmp_path / "qe"
    _write_qe_input(task_root)
    current = ir.parse_current_inputs("quantum-espresso", task_root, primary_input="scf.in")

    assert current["parameters"]["electron_maxstep"] == 100
    assert current["parameters"]["ecutwfc"] == 60
    assert current["parameters"]["KPOINTS"] == "6x6x6"
    assert ir.classify_change("quantum-espresso", "electron_maxstep", 100, 200) == "L1"
    assert ir.classify_change("quantum-espresso", "ecutwfc", 60, 80) == "L2"


def test_hash_only_comment_change_is_synchronized_and_refreshes_hash(tmp_path: Path) -> None:
    task_root, design_path, current = _make_vasp_task(tmp_path)
    old_hash = current["file_hashes"]["INCAR"]
    incar = task_root / "INCAR"
    incar.write_text("# user comment\n" + incar.read_text(encoding="utf-8"), encoding="utf-8")

    result = ir.reconcile_task(task_root, design_path, write=True)

    assert result["status"] == "synchronized"
    assert result["verdict"] == "ADVANCE"
    assert result["changed_parameters"] == []
    workflow = json.loads((task_root / "workflow.json").read_text(encoding="utf-8"))
    assert workflow["inputs"]["files"][0] or old_hash != _sha256(incar)
    incar_record = next(item for item in workflow["inputs"]["files"] if item["name"] == "INCAR")
    assert old_hash != incar_record["sha256"]
    assert incar_record["authority"] == "user_override"


def test_user_override_file_is_never_rewritten(tmp_path: Path) -> None:
    task_root, design_path, _ = _make_vasp_task(tmp_path)
    changed = (task_root / "INCAR").read_text(encoding="utf-8") + "# keep this\n"
    (task_root / "INCAR").write_text(changed, encoding="utf-8")

    ir.reconcile_task(task_root, design_path, write=True)

    assert (task_root / "INCAR").read_text(encoding="utf-8") == changed


@pytest.mark.parametrize("state", ["planned", "prepared"])
def test_mutable_states_adopt_l2_without_rereview(tmp_path: Path, state: str) -> None:
    task_root, design_path, _ = _make_vasp_task(tmp_path, state=state)
    incar = task_root / "INCAR"
    incar.write_text(incar.read_text(encoding="utf-8").replace("ENCUT = 520", "ENCUT = 600"), encoding="utf-8")

    result = ir.reconcile_task(task_root, design_path, write=True)

    assert result["status"] in {"adopted", "propagated"}
    assert result["verdict"] == "ADVANCE"


@pytest.mark.parametrize("state", ["submitted", "running"])
def test_submitted_or_running_change_is_pending_override_and_snapshot_stays_immutable(
    tmp_path: Path, state: str
) -> None:
    task_root, design_path, current = _make_vasp_task(tmp_path, state=state)
    attempt_snapshot = copy.deepcopy(current)
    workflow_before = json.loads((task_root / "workflow.json").read_text(encoding="utf-8"))
    incar = task_root / "INCAR"
    incar.write_text(incar.read_text(encoding="utf-8").replace("NELM = 60", "NELM = 120"), encoding="utf-8")

    result = ir.reconcile_task(task_root, design_path, write=True)

    assert result["status"] == "pending_override"
    workflow = json.loads((task_root / "workflow.json").read_text(encoding="utf-8"))
    assert workflow["attempts"][0]["snapshot"] == workflow_before["attempts"][0]["snapshot"]
    assert workflow["design"]["engine_parameters"] == workflow_before["design"]["engine_parameters"]
    assert workflow["parameter_reconciliation"]["status"] == "pending_override"
    assert workflow["pending_input_snapshot"]["parameters"]["NELM"] == 120
    assert attempt_snapshot["parameters"]["NELM"] == 60


def test_completed_change_requires_rerun_lineage_without_overwriting_source(tmp_path: Path) -> None:
    task_root, design_path, _ = _make_vasp_task(tmp_path, state="completed")
    before = (task_root / "workflow.json").read_bytes()
    incar = task_root / "INCAR"
    incar.write_text(incar.read_text(encoding="utf-8").replace("ENCUT = 520", "ENCUT = 600"), encoding="utf-8")

    result = ir.reconcile_task(task_root, design_path, write=True)

    assert result["status"] == "pending_override"
    assert result["rerun_required"] is True
    workflow = json.loads((task_root / "workflow.json").read_text(encoding="utf-8"))
    assert workflow["status"] == "completed"
    assert workflow["lineage"]["derived_from"] is None
    assert (task_root / "INCAR").read_text(encoding="utf-8").endswith("\n")
    assert before != (task_root / "workflow.json").read_bytes()


def test_reconcile_write_false_does_not_change_records(tmp_path: Path) -> None:
    task_root, design_path, _ = _make_vasp_task(tmp_path)
    (task_root / "INCAR").write_text(
        (task_root / "INCAR").read_text(encoding="utf-8").replace("NELM = 60", "NELM = 120"),
        encoding="utf-8",
    )
    workflow_before = (task_root / "workflow.json").read_bytes()
    design_before = design_path.read_bytes()

    result = ir.reconcile_task(task_root, design_path, write=False)

    assert result["status"] == "adopted"
    assert (task_root / "workflow.json").read_bytes() == workflow_before
    assert design_path.read_bytes() == design_before
