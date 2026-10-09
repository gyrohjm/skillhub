from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

import canonical_workflow as cw
import workflow_control as wc


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_vasp_inputs(task_root: Path) -> None:
    task_root.mkdir(parents=True, exist_ok=True)
    (task_root / "INCAR").write_text("ENCUT = 520\nNELM = 60\n", encoding="utf-8")
    (task_root / "KPOINTS").write_text(
        "automatic\n0\nGamma\n6 6 6\n0 0 0\n", encoding="utf-8"
    )
    (task_root / "POSCAR").write_text(
        "Mg B\n1.0\n1 0 0\n0 1 0\n0 0 1\nMg B\n1 2\nDirect\n"
        "0 0 0\n0 0 0.3\n0 0 0.7\n",
        encoding="utf-8",
    )
    (task_root / "POTCAR").write_text("TITEL = PAW_PBE Mg B\n", encoding="utf-8")
    (task_root / "job.sh").write_text("#!/usr/bin/env bash\nsrun vasp_std\n", encoding="utf-8")


def _workflow(
    task_root: Path,
    *,
    task_slug: str = "p2_scf",
    status: str = "prepared",
    dependencies: list[dict] | None = None,
    reconciliation_status: str = "synchronized",
    failure: dict | None = None,
) -> dict:
    files = []
    for name in ("INCAR", "KPOINTS", "POSCAR", "POTCAR"):
        path = task_root / name
        files.append(
            {
                "base": "task_root",
                "path": name,
                "name": name,
                "role": "engine_input",
                "mode": "static",
                "sha256": _sha256(path),
                "authority": "generated",
            }
        )
    document = {
        "schema_version": 2,
        "contract": "dft.workflow.v2",
        "composition_slug": "mgb2",
        "structure_slug": "bulk",
        "task_slug": task_slug,
        "status": status,
        "engine": "vasp",
        "updated_at": "2026-08-31T00:00:00Z",
        "stage": "scf",
        "design": {
            "design_id": "mgb2",
            "revision": 1,
            "approval_ref": "workspace_root:plans/mgb2/bulk/history.jsonl#mgb2:r0001",
            "baseline_parameter_hash": "a" * 64,
            "engine_parameters": {"ENCUT": 520},
        },
        "inputs": {"materialization": "static", "files": files},
        "input_authority": {name: "generated" for name in ("INCAR", "KPOINTS", "POSCAR", "POTCAR")},
        "dependencies": dependencies or [],
        "parameter_reconciliation": {
            "status": reconciliation_status,
            "changed_parameters": [],
            "affected_tasks": [],
        },
        "resource_profile": {"ref": "workspace_root:.dft/resource-profile.json", "overrides": {}},
        "attempts": [],
        "submission": {"state": "not_submitted", "allowed": False, "job_id": None},
        "completion": {
            "scheduler_complete": False,
            "artifact_complete": False,
            "scientifically_accepted": False,
        },
        "lineage": {"derived_from": None, "supersedes": None},
        "history": [{"at": "2026-08-31T00:00:00Z", "status": status}],
    }
    if failure is not None:
        document["failure"] = failure
    return document


def _write_workflow(task_root: Path, workflow: dict) -> Path:
    path = task_root / "workflow.json"
    path.write_text(json.dumps(workflow, indent=2) + "\n", encoding="utf-8")
    return path


def _dependent_case(tmp_path: Path) -> tuple[Path, Path]:
    structure = tmp_path / "calculations/mgb2/bulk"
    upstream = structure / "p1_relax"
    task_root = structure / "p2_scf"
    _write_vasp_inputs(task_root)
    _write_vasp_inputs(upstream)
    (upstream / "CONTCAR").write_text("complete geometry\n", encoding="utf-8")
    upstream_workflow = _workflow(upstream, task_slug="p1_relax", status="completed")
    upstream_workflow["completion"] = {
        "scheduler_complete": True,
        "artifact_complete": True,
        "scientifically_accepted": False,
    }
    upstream_workflow["artifacts"] = [
        {
            "name": "CONTCAR",
            "path": "CONTCAR",
            "sha256": _sha256(upstream / "CONTCAR"),
            "parseable": True,
        }
    ]
    _write_workflow(upstream, upstream_workflow)
    dependencies = [
        {
            "task_ref": "p1_relax",
            "required_artifacts": ["CONTCAR"],
            "gate_status": "awaiting_upstream",
        }
    ]
    task_workflow = _workflow(
        task_root,
        dependencies=dependencies,
        status="awaiting_upstream",
    )
    _write_workflow(task_root, task_workflow)
    return task_root, upstream


def test_complete_parseable_dependency_artifacts_advance(tmp_path: Path) -> None:
    task_root, _ = _dependent_case(tmp_path)

    result = wc.evaluate_dependencies(task_root)

    assert result["verdict"] == "ADVANCE"
    assert result["reasons"] == []
    assert result["evidence"] == [{"task_ref": "p1_relax", "artifact": "CONTCAR", "status": "complete"}]


def test_completed_dependency_with_no_required_artifacts_can_advance(tmp_path: Path) -> None:
    task_root, _ = _dependent_case(tmp_path)
    workflow_path = task_root / "workflow.json"
    workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
    workflow["dependencies"][0]["required_artifacts"] = []
    workflow_path.write_text(json.dumps(workflow, indent=2) + "\n", encoding="utf-8")

    result = wc.evaluate_dependencies(task_root)

    assert result["verdict"] == "ADVANCE"
    assert result["evidence"] == []


def test_dependency_gate_does_not_mutate_user_inputs_or_workflow(tmp_path: Path) -> None:
    task_root, _ = _dependent_case(tmp_path)
    (task_root / "INCAR").write_text("# user override\nENCUT = 600\nNELM = 60\n", encoding="utf-8")
    input_before = (task_root / "INCAR").read_bytes()
    workflow_before = (task_root / "workflow.json").read_bytes()

    wc.evaluate_dependencies(task_root)

    assert (task_root / "INCAR").read_bytes() == input_before
    assert (task_root / "workflow.json").read_bytes() == workflow_before


@pytest.mark.parametrize(
    ("mutator", "expected_status"),
    [
        (lambda upstream: (upstream / "CONTCAR").unlink(), "missing"),
        (lambda upstream: (upstream / "CONTCAR").write_text("", encoding="utf-8"), "empty"),
        (
            lambda upstream: (upstream / "CONTCAR").write_text("changed geometry\n", encoding="utf-8"),
            "hash_mismatch",
        ),
    ],
)
def test_incomplete_dependency_evidence_needs_agent(tmp_path: Path, mutator, expected_status: str) -> None:
    task_root, upstream = _dependent_case(tmp_path)
    mutator(upstream)

    result = wc.evaluate_dependencies(task_root)

    assert result["verdict"] == "NEEDS_AGENT"
    assert result["evidence"][0]["status"] == expected_status
    assert result["reasons"]


def test_scheduler_completion_alone_never_advances_dependency_gate(tmp_path: Path) -> None:
    task_root, upstream = _dependent_case(tmp_path)
    workflow_path = upstream / "workflow.json"
    upstream_workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
    upstream_workflow["completion"] = {
        "scheduler_complete": True,
        "artifact_complete": False,
        "scientifically_accepted": False,
    }
    workflow_path.write_text(json.dumps(upstream_workflow, indent=2) + "\n", encoding="utf-8")

    result = wc.evaluate_dependencies(task_root)

    assert result["verdict"] == "NEEDS_AGENT"
    assert result["evidence"][0]["status"] == "upstream_artifact_incomplete"


def test_upstream_unresolved_l3_reconciliation_is_a_major_conflict(tmp_path: Path) -> None:
    task_root, upstream = _dependent_case(tmp_path)
    workflow_path = upstream / "workflow.json"
    upstream_workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
    upstream_workflow["parameter_reconciliation"]["status"] = "major_conflict"
    workflow_path.write_text(json.dumps(upstream_workflow, indent=2) + "\n", encoding="utf-8")

    result = wc.evaluate_dependencies(task_root)

    assert result["verdict"] == "MAJOR_CONFLICT"
    assert result["evidence"][0]["status"] == "major_conflict"


def test_recognized_scheduler_failure_retries_in_place(tmp_path: Path) -> None:
    task_root = tmp_path / "task"
    _write_vasp_inputs(task_root)
    _write_workflow(
        task_root,
        _workflow(
            task_root,
            failure={"category": "scheduler", "error_type": "TIME_LIMIT", "message": "wall time"},
        ),
    )

    result = wc.evaluate_dependencies(task_root)

    assert result["verdict"] == "RETRY_IN_PLACE"
    assert any("TIME_LIMIT" in reason for reason in result["reasons"])


def test_unresolved_l3_reconciliation_is_major_conflict(tmp_path: Path) -> None:
    task_root = tmp_path / "task"
    _write_vasp_inputs(task_root)
    _write_workflow(
        task_root,
        _workflow(task_root, reconciliation_status="major_conflict"),
    )

    result = wc.evaluate_dependencies(task_root)

    assert result["verdict"] == "MAJOR_CONFLICT"
    assert any("L3" in reason or "major" in reason.lower() for reason in result["reasons"])


@pytest.mark.parametrize(
    "verdict",
    ["ADVANCE", "RETRY_IN_PLACE", "CREATE_RERUN", "REQUEST_PARAMETER_REVISION", "MAJOR_CONFLICT"],
)
def test_agent_decision_accepts_only_exact_verdicts_and_records_evidence(
    tmp_path: Path, verdict: str
) -> None:
    task_root = tmp_path / "task"
    _write_vasp_inputs(task_root)
    _write_workflow(task_root, _workflow(task_root))
    decision = {"verdict": verdict, "reason": "reviewed evidence", "evidence": [{"source": "report"}]}

    result = wc.record_agent_decision(task_root, decision)

    assert result["verdict"] == verdict
    assert result["reason"] == decision["reason"]
    assert result["evidence"] == decision["evidence"]
    recorded = json.loads((task_root / "workflow.json").read_text(encoding="utf-8"))
    assert recorded["agent_decision"]["verdict"] == verdict
    assert recorded["agent_decision"]["reason"] == decision["reason"]
    assert recorded["agent_decision"]["evidence"] == decision["evidence"]


def test_parameter_revision_agent_decision_sets_awaiting_user_decision(tmp_path: Path) -> None:
    task_root = tmp_path / "task"
    _write_vasp_inputs(task_root)
    _write_workflow(task_root, _workflow(task_root))

    wc.record_agent_decision(
        task_root,
        {
            "verdict": "REQUEST_PARAMETER_REVISION",
            "reason": "the approved model no longer applies",
            "evidence": [{"source": "parameter-reconciliation", "level": "L3"}],
        },
    )

    recorded = json.loads((task_root / "workflow.json").read_text(encoding="utf-8"))
    assert recorded["status"] == "awaiting_user_decision"
    assert recorded["submission"]["allowed"] is False


def test_awaiting_user_decision_remains_a_major_gate(tmp_path: Path) -> None:
    task_root = tmp_path / "task"
    _write_vasp_inputs(task_root)
    _write_workflow(task_root, _workflow(task_root))
    wc.record_agent_decision(
        task_root,
        {
            "verdict": "REQUEST_PARAMETER_REVISION",
            "reason": "L3 model change needs user choice",
            "evidence": [{"source": "reconciliation", "impact": "L3"}],
        },
    )

    result = wc.evaluate_dependencies(task_root)

    assert result["verdict"] == "MAJOR_CONFLICT"


def test_agent_cannot_bypass_an_unresolved_major_conflict(tmp_path: Path) -> None:
    task_root = tmp_path / "task"
    _write_vasp_inputs(task_root)
    _write_workflow(task_root, _workflow(task_root, reconciliation_status="major_conflict"))

    with pytest.raises(wc.WorkflowControlError, match="major conflict"):
        wc.record_agent_decision(
            task_root,
            {
                "verdict": "ADVANCE",
                "reason": "try to bypass L3",
                "evidence": [{"source": "agent"}],
            },
        )


@pytest.mark.parametrize(
    "decision",
    [
        {"verdict": "advance", "reason": "wrong case", "evidence": [{"source": "x"}]},
        {"verdict": "ADVANCE", "reason": "", "evidence": [{"source": "x"}]},
        {"verdict": "ADVANCE", "reason": "missing evidence"},
        {"verdict": "ADVANCE", "reason": "empty evidence", "evidence": []},
    ],
)
def test_agent_decision_rejects_non_exact_or_unsubstantiated_records(tmp_path: Path, decision: dict) -> None:
    task_root = tmp_path / "task"
    _write_vasp_inputs(task_root)
    _write_workflow(task_root, _workflow(task_root))

    with pytest.raises(wc.WorkflowControlError):
        wc.record_agent_decision(task_root, decision)


def test_archive_attempt_copies_only_replaceable_files_and_records_manifest(tmp_path: Path) -> None:
    task_root = tmp_path / "task"
    _write_vasp_inputs(task_root)
    (task_root / "slurm-123.out").write_text("scheduler stdout\n", encoding="utf-8")
    (task_root / "slurm-123.err").write_text("scheduler stderr\n", encoding="utf-8")
    (task_root / "OUTCAR").write_text("completed engine output\n", encoding="utf-8")
    (task_root / "CONTCAR").write_text("completed geometry\n", encoding="utf-8")
    (task_root / "README.md").write_text("do not snapshot this", encoding="utf-8")
    _write_workflow(task_root, _workflow(task_root))
    source_before = {
        path.name: path.read_bytes()
        for path in (task_root / "INCAR", task_root / "job.sh")
    }
    workflow_before = (task_root / "workflow.json").read_bytes()

    attempt = wc.archive_attempt(task_root, "repair scheduler launch")

    assert attempt.name == "attempt-001"
    assert (attempt / "manifest.json").is_file()
    manifest = json.loads((attempt / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["attempt_id"] == "attempt-001"
    assert manifest["reason"] == "repair scheduler launch"
    archived_paths = {item["path"] for item in manifest["files"]}
    assert {"INCAR", "KPOINTS", "POSCAR", "POTCAR", "job.sh", "slurm-123.out", "slurm-123.err", "workflow.json"} <= archived_paths
    assert not (attempt / "OUTCAR").exists()
    assert not (attempt / "CONTCAR").exists()
    assert not (attempt / "README.md").exists()
    assert {name: (task_root / name).read_bytes() for name in source_before} == source_before
    assert (attempt / "workflow.json").read_bytes() == workflow_before

    recorded = json.loads((task_root / "workflow.json").read_text(encoding="utf-8"))
    assert recorded["attempts"][-1]["attempt_id"] == "attempt-001"
    assert recorded["attempts"][-1]["snapshot"]["files"]["INCAR"]["sha256"] == _sha256(task_root / "INCAR")


def test_archive_attempt_uses_next_free_index_without_overwriting(tmp_path: Path) -> None:
    task_root = tmp_path / "task"
    _write_vasp_inputs(task_root)
    _write_workflow(task_root, _workflow(task_root))

    first = wc.archive_attempt(task_root, "first repair")
    first_manifest_before = (first / "manifest.json").read_bytes()
    second = wc.archive_attempt(task_root, "second repair")

    assert first.name == "attempt-001"
    assert second.name == "attempt-002"
    assert (first / "manifest.json").read_bytes() == first_manifest_before


def test_archive_attempt_respects_attempts_recorded_in_workflow(tmp_path: Path) -> None:
    task_root = tmp_path / "task"
    _write_vasp_inputs(task_root)
    workflow = _workflow(task_root)
    workflow["attempts"] = [
        {
            "attempt_id": "attempt-001",
            "reason": "already archived",
            "snapshot": {},
        }
    ]
    _write_workflow(task_root, workflow)

    attempt = wc.archive_attempt(task_root, "new repair")

    assert attempt.name == "attempt-002"


def test_archive_attempt_rejects_missing_declared_current_input_without_mutation(tmp_path: Path) -> None:
    task_root = tmp_path / "task"
    _write_vasp_inputs(task_root)
    workflow = _workflow(task_root)
    workflow["inputs"]["files"][0]["path"] = "MISSING_INCAR"
    workflow_before = json.dumps(workflow, indent=2) + "\n"
    _write_workflow(task_root, workflow)

    with pytest.raises(wc.WorkflowControlError, match="missing.*declared"):
        wc.archive_attempt(task_root, "must not archive an incomplete snapshot")

    assert not (task_root / "attempts").exists()
    assert (task_root / "workflow.json").read_text(encoding="utf-8") == workflow_before


def test_unsafe_declared_input_path_is_rejected(tmp_path: Path) -> None:
    task_root = tmp_path / "task"
    _write_vasp_inputs(task_root)
    workflow = _workflow(task_root)
    workflow["inputs"]["files"][0]["path"] = "../outside/INCAR"
    _write_workflow(task_root, workflow)

    with pytest.raises(wc.WorkflowControlError, match="unsafe"):
        wc.archive_attempt(task_root, "must not escape task leaf")


def test_completed_rerun_branch_copies_inputs_not_outputs_and_preserves_source_bytes(tmp_path: Path) -> None:
    task_root = tmp_path / "calculations/mgb2/bulk/p1_scf"
    _write_vasp_inputs(task_root)
    (task_root / "OUTCAR").write_text("completed output\n", encoding="utf-8")
    (task_root / "CONTCAR").write_text("completed geometry\n", encoding="utf-8")
    (task_root / "slurm-123.out").write_text("scheduler stdout\n", encoding="utf-8")
    (task_root / "slurm-123.err").write_text("scheduler stderr\n", encoding="utf-8")
    workflow = _workflow(task_root, task_slug="p1_scf", status="completed")
    workflow["task_uuid"] = "a90c9b81-21e0-4e73-935c-52e82773560f"
    workflow["completion"] = {
        "scheduler_complete": True,
        "artifact_complete": True,
        "scientifically_accepted": False,
    }
    _write_workflow(task_root, workflow)
    source_files = [path for path in task_root.iterdir() if path.is_file()]
    source_before = {path.relative_to(task_root): path.read_bytes() for path in source_files}

    rerun = wc.create_rerun_branch(
        task_root,
        "unexpected magnetic ordering",
        [{"name": "ISPIN", "old": 1, "new": 2, "impact": "L3"}],
    )

    assert rerun.name == "rerun_001"
    assert (rerun / "INCAR").read_bytes() == (task_root / "INCAR").read_bytes()
    assert (rerun / "job.sh").read_bytes() == (task_root / "job.sh").read_bytes()
    for output_name in ("OUTCAR", "CONTCAR", "slurm-123.out", "slurm-123.err"):
        assert not (rerun / output_name).exists()
    rerun_workflow = json.loads((rerun / "workflow.json").read_text(encoding="utf-8"))
    from uuid import UUID
    assert UUID(rerun_workflow["task_uuid"])
    assert rerun_workflow["task_uuid"] != workflow["task_uuid"]
    assert rerun_workflow["lineage"]["derived_from_uuid"] == workflow["task_uuid"]
    assert rerun_workflow["status"] == "prepared"
    assert rerun_workflow["submission"] == {
        "state": "not_submitted",
        "allowed": False,
        "job_id": None,
    }
    assert rerun_workflow["completion"] == {
        "scheduler_complete": False,
        "artifact_complete": False,
        "scientifically_accepted": False,
    }
    assert rerun_workflow["attempts"] == []
    assert rerun_workflow["lineage"]["derived_from"]
    assert rerun_workflow["rerun"]["reason"] == "unexpected magnetic ordering"
    assert rerun_workflow["rerun"]["parameter_changes"][0]["name"] == "ISPIN"
    assert {path.relative_to(task_root): path.read_bytes() for path in task_root.iterdir() if path.is_file()} == source_before


def test_rerun_branch_uses_next_free_sibling_and_rejects_nonterminal_source(tmp_path: Path) -> None:
    task_root = tmp_path / "calculations/mgb2/bulk/p1_scf"
    _write_vasp_inputs(task_root)
    _write_workflow(task_root, _workflow(task_root, task_slug="p1_scf", status="completed"))

    first = wc.create_rerun_branch(task_root, "first", [])
    second = wc.create_rerun_branch(task_root, "second", [])

    assert first.name == "rerun_001"
    assert second.name == "rerun_002"
    with pytest.raises(wc.WorkflowControlError, match="completed, inconclusive or failed"):
        wc.create_rerun_branch(first, "nested source is prepared", [])


def test_rerun_branch_rejects_missing_declared_current_input_without_mutation(tmp_path: Path) -> None:
    task_root = tmp_path / "calculations/mgb2/bulk/p1_scf"
    _write_vasp_inputs(task_root)
    workflow = _workflow(task_root, task_slug="p1_scf", status="completed")
    workflow["completion"] = {
        "scheduler_complete": True,
        "artifact_complete": True,
        "scientifically_accepted": False,
    }
    workflow["inputs"]["files"][0]["path"] = "MISSING_INCAR"
    _write_workflow(task_root, workflow)
    workflow_before = (task_root / "workflow.json").read_bytes()

    with pytest.raises(wc.WorkflowControlError, match="missing.*declared"):
        wc.create_rerun_branch(task_root, "must not branch an incomplete snapshot", [])

    assert not (task_root.parent / "rerun_001").exists()
    assert (task_root / "workflow.json").read_bytes() == workflow_before


def test_rerun_requires_an_explicit_terminal_status(tmp_path: Path) -> None:
    task_root = tmp_path / "task"
    _write_vasp_inputs(task_root)
    workflow = _workflow(task_root, status="prepared")
    workflow["completion"] = {
        "scheduler_complete": True,
        "artifact_complete": True,
        "scientifically_accepted": False,
    }
    workflow["submission"]["state"] = "completed"
    _write_workflow(task_root, workflow)

    with pytest.raises(wc.WorkflowControlError, match="completed, inconclusive or failed"):
        wc.create_rerun_branch(task_root, "status must be explicit", [])


def test_canonical_workflow_exposes_task4_dependency_gate(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    expected = {"verdict": "ADVANCE", "reasons": [], "evidence": []}
    calls: list[Path] = []

    def fake_gate(task_root: Path) -> dict:
        calls.append(task_root)
        return expected

    monkeypatch.setattr(cw, "_evaluate_dependencies", fake_gate)

    assert cw.evaluate_dependencies(tmp_path) == expected
    assert calls == [tmp_path]


def test_route_rerun_is_nested_preserves_evidence_and_clears_selection(tmp_path):
    from dft_contracts.project import init_project, register_route
    from dft_contracts.lifecycle import screen
    root = tmp_path / 'project'
    root.mkdir()
    init_project(root)
    route = register_route(root, 'sample/benchmark', 'mgb2', 'bulk')
    leaf = route / '03_scf'
    _write_vasp_inputs(leaf)
    w = _workflow(leaf, task_slug='03_scf', status='completed')
    w['task_uuid'] = '00000000-0000-4000-8000-000000000001'
    w['management'] = {'disposition': 'selected', 'selection_key': 'reference'}
    _write_workflow(leaf, w)
    (leaf / 'OUTCAR').write_text('original decisive output')
    original = {p.name: p.read_bytes() for p in leaf.iterdir() if p.is_file()}
    rerun = wc.create_rerun_branch(leaf, 'Parameter change documented in plan', [{'name':'ENCUT','old':520,'new':600}])
    assert rerun == leaf / 'revisions/rerun_001'
    assert all((leaf / name).read_bytes() == content for name,content in original.items())
    newer = json.loads((rerun / 'workflow.json').read_text())
    assert newer['task_uuid'] != w['task_uuid']
    assert newer['lineage']['derived_from_uuid'] == w['task_uuid']
    assert 'management' not in newer
    assert newer['completion']['scientifically_accepted'] is False
    assert not (rerun / 'OUTCAR').exists()
    assert (rerun / 'INCAR').read_bytes() == (leaf / 'INCAR').read_bytes()  # candidate, not silently changed parameters
    with pytest.raises(cw.WorkflowError, match='do not implement'):
        cw._check_rerun_inputs(rerun, newer)
    (rerun / 'INCAR').write_text('ENCUT = 600\nNELM = 60\n')
    cw._check_rerun_inputs(rerun, newer)
    record = next(r for r in screen(root) if r['path'] == str(leaf.relative_to(root)))
    assert not record['archive_candidate'] and str(rerun.relative_to(root)) in record['dependents']
