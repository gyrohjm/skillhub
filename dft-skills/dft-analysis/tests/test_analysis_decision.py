from __future__ import annotations

import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from analysis_decision import (  # noqa: E402
    assess_completion,
    diagnose_failure,
    recommend_next_step,
)


def _workflow(status: str = "completed", scheduler_state: str = "COMPLETED") -> dict:
    return {
        "status": status,
        "task_slug": "p1_relax",
        "submission": {"scheduler_state": scheduler_state},
    }


def _result(*, normal: bool = True, status: str = "completed", electronic=True, ionic=True) -> dict:
    return {
        "termination": {"normal": normal, "status": status},
        "convergence": {"electronic": electronic, "ionic": ionic},
    }


def _workflow_v2(
    *,
    status: str = "completed",
    scheduler_state: str = "COMPLETED",
    artifact_complete: bool = True,
    scientifically_accepted: bool = False,
) -> dict:
    return {
        "schema_version": 2,
        "contract": "dft.workflow.v2",
        "composition_slug": "mgb2",
        "structure_slug": "bulk",
        "task_slug": "p1_relax",
        "status": status,
        "engine": "vasp",
        "updated_at": "2026-08-31T00:00:00+00:00",
        "design": {
            "design_id": "mgb2",
            "revision": 1,
            "approval_ref": "workspace_root:plans/mgb2/bulk/history.jsonl#mgb2:r0001",
            "baseline_parameter_hash": "a" * 64,
        },
        "inputs": {"materialization": "static", "files": []},
        "dependencies": [],
        "input_authority": {},
        "parameter_reconciliation": {
            "status": "synchronized",
            "changed_parameters": [],
            "affected_tasks": [],
        },
        "resource_profile": {"ref": "workspace_root:.dft/resource-profile.json", "overrides": {}},
        "attempts": [],
        "submission": {"state": scheduler_state.lower(), "scheduler_state": scheduler_state, "job_id": "12345"},
        "completion": {
            "scheduler_complete": scheduler_state == "COMPLETED",
            "artifact_complete": artifact_complete,
            "scientifically_accepted": scientifically_accepted,
        },
        "lineage": {
            "derived_from": "workspace_root:calculations/mgb2/bulk/p1_relax/workflow.json",
            "supersedes": None,
        },
        "history": [],
    }


def test_completion_requires_scheduler_engine_and_stage_convergence() -> None:
    decision = assess_completion(_workflow(), _result(), stage="relax")

    assert decision["status"] == "completed"
    assert decision["accepted"] is True
    assert decision["checks"] == {
        "workflow_completed": True,
        "scheduler_completed": True,
        "normal_termination": True,
        "electronic_convergence": True,
        "ionic_convergence": True,
    }


def test_v1_completion_keeps_legacy_result_keys_and_adds_separate_dimensions() -> None:
    decision = assess_completion(_workflow(), _result(), stage="relax")

    assert decision["status"] == "completed"
    assert decision["accepted"] is True
    assert decision["completion"] == {
        "scheduler_complete": True,
        "artifact_complete": True,
        "scientifically_accepted": False,
    }


def test_missing_scheduler_state_is_inconclusive_not_success() -> None:
    decision = assess_completion(
        {"status": "completed", "task_slug": "p2_scf", "submission": {}},
        _result(ionic=None),
        stage="scf",
    )

    assert decision["accepted"] is False
    assert decision["status"] == "inconclusive"
    assert "scheduler terminal state is missing" in decision["reasons"]


def test_failed_runtime_is_classified_and_routed_without_submission() -> None:
    decision = diagnose_failure(
        _workflow(status="failed", scheduler_state="FAILED"),
        _result(normal=False, status="failed", electronic=False, ionic=None),
        {"slurm-123.out": "OUT OF MEMORY: oom-kill event detected"},
    )

    assert decision["failure_class"] == "scheduler_resource"
    assert decision["next_owner"] == "dft-workflow"
    assert decision["submission_authorized"] is False
    assert decision["evidence"]


def test_numerical_failure_routes_parameter_change_to_design() -> None:
    decision = diagnose_failure(
        _workflow(status="failed", scheduler_state="COMPLETED"),
        _result(normal=False, status="failed", electronic=False, ionic=None),
        {"pwscf.out": "convergence NOT achieved after 100 iterations"},
    )

    assert decision["failure_class"] == "numerical_convergence"
    assert decision["next_owner"] == "dft-design"
    assert decision["requires_design_revision"] is True


def test_recommendation_preserves_design_then_workflow_gate() -> None:
    recommendation = recommend_next_step(
        "numerical_convergence",
        parameter_changes=[{"name": "mixing_beta", "proposed": 0.3}],
        acceptance_rule="electronic convergence true within the approved iteration limit",
    )

    assert recommendation["owner"] == "dft-design"
    assert recommendation["handoff"] == ["dft-design", "dft-workflow"]
    assert recommendation["submission_authorized"] is False
    assert recommendation["parameter_changes"][0]["name"] == "mixing_beta"
    assert "approved iteration limit" in recommendation["acceptance_rule"]


def test_v2_completion_keeps_scheduler_artifact_and_science_separate() -> None:
    workflow = _workflow_v2(scientifically_accepted=True)
    result = _result()
    result["artifacts"] = [{"path": "OUTCAR", "status": "complete"}]
    result["scientific_verdict"] = "supported"

    decision = assess_completion(workflow, result, stage="relax")

    assert decision["completion"] == {
        "scheduler_complete": True,
        "artifact_complete": True,
        "scientifically_accepted": True,
    }
    assert decision["status"] == "completed"
    assert decision["accepted"] is True
    assert decision["recovery_mode"] == "none"


def test_scheduler_completion_alone_never_implies_artifact_or_science() -> None:
    workflow = _workflow_v2(artifact_complete=False, scientifically_accepted=False)
    result = {"termination": {}, "convergence": {}}

    decision = assess_completion(workflow, result, stage="scf")

    assert decision["completion"] == {
        "scheduler_complete": True,
        "artifact_complete": False,
        "scientifically_accepted": False,
    }
    assert decision["accepted"] is False
    assert decision["status"] == "inconclusive"


@pytest.mark.parametrize(
    "artifact_record",
    [
        {"path": "OUTCAR"},
        {"path": "OUTCAR", "status": "unknown"},
        {"path": "OUTCAR", "sha256": "a" * 64},
    ],
)
def test_unvalidated_artifact_record_does_not_establish_v2_completion(artifact_record: dict) -> None:
    workflow = _workflow_v2()
    workflow["completion"].pop("artifact_complete")
    result = _result()
    result["artifacts"] = [artifact_record]

    decision = assess_completion(workflow, result, stage="relax")

    assert decision["completion"]["artifact_complete"] is False
    assert decision["status"] == "inconclusive"
    assert decision["accepted"] is False


def test_explicit_artifact_completion_accepts_an_unvalidated_inventory() -> None:
    workflow = _workflow_v2(artifact_complete=True)
    result = _result()
    result["artifacts"] = [{"path": "OUTCAR"}]

    decision = assess_completion(workflow, result, stage="relax")

    assert decision["completion"]["artifact_complete"] is True
    assert decision["status"] == "completed"


def test_v2_without_artifact_completion_or_inventory_does_not_use_v1_fallback() -> None:
    workflow = _workflow_v2()
    workflow["completion"].pop("artifact_complete")

    decision = assess_completion(workflow, _result(), stage="relax")

    assert decision["completion"]["artifact_complete"] is False
    assert decision["status"] == "inconclusive"


def test_falsified_complete_result_stays_completed_and_creates_rerun_branch() -> None:
    workflow = _workflow_v2(scientifically_accepted=False)
    result = _result()
    result["artifacts"] = [{"path": "OUTCAR", "status": "complete"}]
    result["scientific_verdict"] = "falsified"

    decision = assess_completion(workflow, result, stage="relax")

    assert decision["status"] == "completed"
    assert decision["completion"] == {
        "scheduler_complete": True,
        "artifact_complete": True,
        "scientifically_accepted": False,
    }
    assert decision["accepted"] is False
    assert decision["recovery_mode"] == "create_rerun_branch"
    assert decision["derived_from"] == workflow["lineage"]["derived_from"]
    assert "engine failure" not in " ".join(decision["reasons"]).lower()


def test_nested_falsified_hypothesis_uses_scientific_rerun_path() -> None:
    workflow = _workflow_v2(scientifically_accepted=False)
    result = _result()
    result["artifacts"] = [{"path": "OUTCAR", "status": "complete"}]
    result["hypothesis"] = {"verdict": "falsified"}

    decision = assess_completion(workflow, result, stage="relax")

    assert decision["status"] == "completed"
    assert decision["completion"]["scientifically_accepted"] is False
    assert decision["recovery_mode"] == "create_rerun_branch"


def test_nested_hypothesis_status_falsified_is_not_an_engine_failure() -> None:
    workflow = _workflow_v2(scientifically_accepted=False)
    result = _result()
    result["artifacts"] = [{"path": "OUTCAR", "status": "complete"}]
    result["hypothesis"] = {"status": "falsified"}

    decision = assess_completion(workflow, result, stage="relax")

    assert decision["status"] == "completed"
    assert decision["recovery_mode"] == "create_rerun_branch"


def test_recognized_technical_failure_recommends_same_leaf_retry() -> None:
    decision = diagnose_failure(
        _workflow_v2(status="failed", scheduler_state="OUT_OF_MEMORY", artifact_complete=False),
        _result(normal=False, status="failed", electronic=False, ionic=None),
        {"slurm.out": "OUT OF MEMORY: oom-kill event detected"},
    )

    assert decision["recovery_mode"] == "retry_in_place"
    assert decision["derived_from"] is None


def test_recognized_numerical_failure_without_parameter_change_retries_in_place() -> None:
    decision = diagnose_failure(
        _workflow_v2(status="failed", scheduler_state="FAILED", artifact_complete=False),
        _result(normal=False, status="failed", electronic=False, ionic=None),
        {"vasp.out": "SCF failed before convergence was achieved"},
    )

    assert decision["failure_class"] == "numerical_convergence"
    assert decision["recovery_mode"] == "retry_in_place"


def test_scheduler_failure_state_is_technical_evidence_without_log_text() -> None:
    decision = diagnose_failure(
        _workflow_v2(status="failed", scheduler_state="TIMEOUT", artifact_complete=False),
        None,
        {},
    )

    assert decision["failure_class"] == "scheduler_resource"
    assert decision["recovery_mode"] == "retry_in_place"


def test_scientific_parameter_change_recommends_rerun_with_lineage() -> None:
    recommendation = recommend_next_step(
        "numerical_convergence",
        parameter_changes=[{"name": "ENCUT", "old": 520, "new": 600, "impact": "L2"}],
        workflow=_workflow_v2(),
    )

    assert recommendation["recovery_mode"] == "create_rerun_branch"
    assert recommendation["derived_from"] == "workspace_root:calculations/mgb2/bulk/p1_relax/workflow.json"
