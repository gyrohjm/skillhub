from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dft_contracts import capability_registry, sha256_json, validate_document  # noqa: E402


def minimal_workflow_v2() -> dict[str, Any]:
    return {
        "schema_version": 2,
        "contract": "dft.workflow.v2",
        "composition_slug": "mgb2",
        "structure_slug": "bulk",
        "task_slug": "p1_relax",
        "status": "prepared",
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
        "submission": {"state": "not_submitted", "allowed": False, "job_id": None},
        "completion": {
            "scheduler_complete": False,
            "artifact_complete": False,
            "scientifically_accepted": False,
        },
        "lineage": {"derived_from": None, "supersedes": None},
        "history": [],
    }


def test_capabilities_are_centralized_and_truthful() -> None:
    engines = capability_registry()["engines"]
    canonical_actions = ["initialize", "bind-approval", "reconcile", "gate", "submit"]
    assert engines["vasp"]["scientific_parse"] is True
    assert engines["vasp"]["canonical_layout_helper"] is True
    assert engines["vasp"]["canonical_actions"] == canonical_actions
    assert engines["vasp"]["legacy_submit"] is True
    assert engines["vasp"]["canonical_submit"] is True
    assert engines["quantum-espresso"]["prepare"] is False
    assert engines["quantum-espresso"]["canonical_layout_helper"] is True
    assert engines["quantum-espresso"]["canonical_actions"] == canonical_actions
    assert engines["quantum-espresso"]["legacy_submit"] is True
    assert engines["quantum-espresso"]["canonical_submit"] is True
    assert engines["cp2k"]["status"] == "contract-only"


def test_result_contract_and_canonical_hash() -> None:
    result = {
        "schema_version": 1,
        "contract": "dft.result.v1",
        "engine": "vasp",
        "engine_version": "6.4.2",
        "task_dir": "/case/energy/scf",
        "parser": {"name": "test", "version": "1"},
        "termination": {"normal": True, "status": "completed"},
        "convergence": {"electronic": True, "ionic": None},
        "source_files": [],
        "warnings": [],
        "confidence": "high",
    }
    assert validate_document("result-v1", result) == []
    assert sha256_json({"b": 2, "a": 1}) == sha256_json({"a": 1, "b": 2})


def test_task_spec_v2_requires_engine() -> None:
    errors = validate_document("task-spec-v2", {"schema_version": 2})
    assert any("engine" in error for error in errors)


def test_task_spec_migration_produces_valid_v2() -> None:
    sys.path.insert(0, str(ROOT / "migrations"))
    from migrate import task_spec_v1_to_v2

    migrated = task_spec_v1_to_v2({
        "schema_version": 1,
        "engine": "quantum-espresso",
        "backend": "qewf",
        "stage": "scf",
        "input_sha256": {"scf.in": "a" * 64},
    })
    assert validate_document("task-spec-v2", migrated) == []


def test_research_idea_contract_is_registered() -> None:
    errors = validate_document("research-idea-v1", {"schema_version": 1})
    assert any("portfolio_id" in error for error in errors)


def test_workflow_v2_requires_completion_and_valid_reconciliation_status() -> None:
    document = minimal_workflow_v2()
    assert validate_document("workflow-v2", document) == []

    missing_completion = minimal_workflow_v2()
    del missing_completion["completion"]
    assert any("completion" in error for error in validate_document("workflow-v2", missing_completion))

    invalid_reconciliation = minimal_workflow_v2()
    invalid_reconciliation["parameter_reconciliation"]["status"] = "not-a-status"
    assert any(
        "not-a-status" in error
        for error in validate_document("workflow-v2", invalid_reconciliation)
    )


def test_resource_profile_v1_is_registered() -> None:
    profile = {
        "schema_version": 1,
        "contract": "dft.resource-profile.v1",
        "cache_status": "ready",
        "checked_at": "2026-08-31T00:00:00+00:00",
        "checks": {
            "scheduler_command": {"status": "passed"},
            "target_partition": {"status": "passed"},
            "approved_activation": {"status": "passed"},
            "approved_executable": {"status": "passed"},
        },
        "invalidation_reason": None,
        "approved_profile": {
            "partition": "compute",
            "activation": "source env.sh",
            "executable": "vasp_std",
        },
    }
    assert validate_document("resource-profile-v1", profile) == []


def test_calculation_design_execution_plan_is_optional() -> None:
    legacy_design = {
        "schema_version": 2,
        "design_id": "mgb2",
        "revision": 1,
        "status": "approved",
        "systems": [],
        "observables": [],
        "calculation_matrix": [],
        "engine_stage_envelopes": [],
    }
    assert validate_document("calculation-design-v2", legacy_design) == []
    with_execution_plan = dict(legacy_design)
    with_execution_plan["execution_plan"] = {
        "tasks": [
            {
                "task_slug": "p1_relax",
                "matrix_id": "M1",
                "stage": "relax",
                "engine": "vasp",
                "dependencies": [],
                "inputs": [],
            }
        ]
    }
    assert validate_document("calculation-design-v2", with_execution_plan) == []


def test_workflow_v1_to_v2_preserves_inputs_and_does_not_mutate_source() -> None:
    import copy

    sys.path.insert(0, str(ROOT / "migrations"))
    from migrate import workflow_v1_to_v2

    source = {
        "schema_version": 1,
        "contract": "dft.workflow.v1",
        "composition_slug": "mgb2",
        "structure_slug": "bulk",
        "task_slug": "p1_relax",
        "status": "prepared",
        "engine": "vasp",
        "updated_at": "2026-08-31T00:00:00+00:00",
        "design": {"design_id": "mgb2", "revision": 1},
        "inputs": [
            {
                "base": "task_root",
                "path": "INCAR",
                "role": "engine_input",
                "sha256": "b" * 64,
            }
        ],
        "submission": {
            "state": "completed",
            "job_id": "12345",
            "approval_status": "approved",
        },
        "result": {"accepted": True},
        "legacy_unknown": {"nested": ["preserve-me"]},
    }
    original = copy.deepcopy(source)

    migrated = workflow_v1_to_v2(source)

    assert source == original
    assert migrated["schema_version"] == 2
    assert migrated["contract"] == "dft.workflow.v2"
    assert migrated["inputs"]["materialization"] == "static"
    assert migrated["inputs"]["files"] == source["inputs"]
    assert migrated["dependencies"] == []
    assert migrated["input_authority"] == {}
    assert migrated["attempts"] == []
    assert migrated["completion"] == {
        "scheduler_complete": True,
        "artifact_complete": False,
        "scientifically_accepted": False,
    }
    assert migrated["submission"]["state"] == "completed"
    assert migrated["submission"]["job_id"] == "12345"
    assert migrated["legacy_unknown"] == source["legacy_unknown"]


def test_workflow_v1_to_v2_normalizes_legacy_submission_states() -> None:
    sys.path.insert(0, str(ROOT / "migrations"))
    from migrate import workflow_v1_to_v2

    for legacy_state, expected_state in (
        ("not_approved", "not_submitted"),
        ("NOT_APPROVED", "not_submitted"),
        ("COMPLETED", "completed"),
        ("complete", "completed"),
        ("future_scheduler_state", "unknown"),
    ):
        source = {
            "schema_version": 1,
            "contract": "dft.workflow.v1",
            "composition_slug": "mgb2",
            "structure_slug": "bulk",
            "task_slug": "p1_relax",
            "status": "prepared",
            "engine": "vasp",
            "updated_at": "2026-08-31T00:00:00+00:00",
            "design": {"design_id": "mgb2", "revision": 1},
            "inputs": [],
            "submission": {"state": legacy_state},
        }

        assert validate_document("workflow-v1", source) == []
        migrated = workflow_v1_to_v2(source)

        assert migrated["submission"]["state"] == expected_state
        assert validate_document("workflow-v2", migrated) == []
        assert migrated["completion"]["scientifically_accepted"] is False
