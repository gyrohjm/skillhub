from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/design_change_request.py"


def workflow_v2() -> dict:
    return {
        "schema_version": 2,
        "contract": "dft.workflow.v2",
        "composition_slug": "mgb2",
        "structure_slug": "ref_struct",
        "task_slug": "p2_scf",
        "status": "completed",
        "engine": "quantum-espresso",
        "updated_at": "2026-08-31T10:00:00+00:00",
        "design": {
            "design_id": "mgb_sc",
            "revision": 3,
            "approval_ref": "workspace_root:plans/mgb2/ref_struct/history.jsonl#mgb_sc:r0003",
            "baseline_parameter_hash": "b" * 64,
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
        "submission": {"state": "completed", "allowed": True, "job_id": "12345"},
        "completion": {
            "scheduler_complete": True,
            "artifact_complete": True,
            "scientifically_accepted": False,
        },
        "lineage": {
            "derived_from": "workspace_root:calculations/mgb2/ref_struct/p1_relax/workflow.json",
            "supersedes": None,
        },
        "history": [],
    }


def test_change_request_uses_design_provenance_and_does_not_overwrite(tmp_path: Path) -> None:
    task_spec = {
        "design_provenance": {
            "scientific_design_approved": True,
            "design_id": "sic_computation",
            "design_revision": 2,
            "matrix_id": "M1",
            "design_sha256": "design-hash",
            "approval_sha256": "approval-hash",
        }
    }
    (tmp_path / "task_spec.json").write_text(json.dumps(task_spec), encoding="utf-8")
    command = [
        sys.executable,
        str(SCRIPT),
        "--case-root", str(tmp_path),
        "--verdict", "inconclusive",
        "--trigger", "decision threshold not resolved",
        "--proposed-change", "add a denser convergence point",
        "--scientific-reason", "current uncertainty overlaps the effect",
        "--evidence", str(tmp_path / "analysis/plot_data/result.dat"),
    ]
    assert subprocess.run(command, check=False).returncode == 0
    output = tmp_path / "analysis/reports/design_change_request.json"
    request = json.loads(output.read_text(encoding="utf-8"))
    assert request["source_design"]["revision"] == 2
    assert request["source_design"]["matrix_id"] == "M1"
    assert request["requested_action"] == "create_and_review_a_new_computation_design_revision"
    assert subprocess.run(command, check=False).returncode == 1


def test_change_request_rejects_unapproved_task(tmp_path: Path) -> None:
    (tmp_path / "task_spec.json").write_text(
        json.dumps({"design_provenance": {"scientific_design_approved": False}}),
        encoding="utf-8",
    )
    result = subprocess.run([
        sys.executable,
        str(SCRIPT),
        "--case-root", str(tmp_path),
        "--verdict", "falsified",
        "--trigger", "control failed",
        "--proposed-change", "replace model",
        "--scientific-reason", "baseline is invalid",
    ], check=False)
    assert result.returncode == 1


def test_change_request_uses_new_layout_workflow_with_relative_provenance(tmp_path: Path) -> None:
    structure_root = tmp_path / "calculations" / "mgb2" / "ref_struct"
    task_leaf = structure_root / "p2_scf"
    evidence = structure_root / "analysis" / "plot_data" / "dos.dat"
    task_leaf.mkdir(parents=True)
    evidence.parent.mkdir(parents=True)
    evidence.write_text("# data\n", encoding="utf-8")
    workflow = {
        "schema_version": 1,
        "contract": "dft.workflow.v1",
        "composition_slug": "mgb2",
        "structure_slug": "ref_struct",
        "task_slug": "p2_scf",
        "status": "completed",
        "engine": "quantum-espresso",
        "updated_at": "2026-08-19T10:00:00+08:00",
        "inputs": [],
        "design": {
            "scientific_design_approved": True,
            "design_id": "mgb_sc",
            "revision": 3,
            "matrix_id": "M2",
            "design_sha256": "d" * 64,
            "approval_sha256": "a" * 64,
        },
    }
    workflow_path = task_leaf / "workflow.json"
    workflow_path.write_text(json.dumps(workflow), encoding="utf-8")

    result = subprocess.run([
        sys.executable,
        str(SCRIPT),
        "--case-root", str(structure_root),
        "--workflow", str(workflow_path),
        "--verdict", "inconclusive",
        "--trigger", "DOS comparison is unresolved",
        "--proposed-change", "add a denser k mesh",
        "--scientific-reason", "the peak position is not converged",
        "--evidence", str(evidence),
    ], check=False)

    assert result.returncode == 0
    request = json.loads(
        (structure_root / "analysis" / "reports" / "design_change_request.json").read_text(
            encoding="utf-8"
        )
    )
    assert request["source_workflow"] == "structure_root:p2_scf/workflow.json"
    assert request["evidence_paths"] == "structure_root:analysis/plot_data/dos.dat".split()
    assert request["source_design"]["revision"] == 3


def test_failure_recovery_request_preserves_diagnosis_and_parameter_proposal(tmp_path: Path) -> None:
    (tmp_path / "task_spec.json").write_text(
        json.dumps(
            {
                "design_provenance": {
                    "scientific_design_approved": True,
                    "design_id": "mgb_sc",
                    "design_revision": 4,
                    "matrix_id": "M3",
                }
            }
        ),
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--case-root",
            str(tmp_path),
            "--verdict",
            "inconclusive",
            "--trigger",
            "SCF did not converge",
            "--proposed-change",
            "replan the SCF test with a smaller mixing beta",
            "--scientific-reason",
            "the current numerical stability gate was not met",
            "--failure-class",
            "numerical_convergence",
            "--diagnostic-summary",
            "QE reached the iteration limit without electronic convergence",
            "--acceptance-rule",
            "electronic convergence true within the approved iteration limit",
            "--parameter-change",
            "mixing_beta=0.3",
        ],
        check=False,
    )

    assert result.returncode == 0
    request = json.loads(
        (tmp_path / "analysis/reports/design_change_request.json").read_text(encoding="utf-8")
    )
    assert request["failure"]["class"] == "numerical_convergence"
    assert request["failure"]["diagnostic_summary"].startswith("QE reached")
    assert "approved iteration limit" in request["acceptance_rule"]
    assert request["parameter_changes"] == [{"name": "mixing_beta", "proposed": "0.3"}]
    assert request["handoff"] == ["dft-design", "dft-workflow"]
    assert request["submission_authorized"] is False


def test_v2_change_request_uses_lineage_and_skips_repeated_submit_review(tmp_path: Path) -> None:
    structure_root = tmp_path / "calculations" / "mgb2" / "ref_struct"
    task_leaf = structure_root / "p2_scf"
    evidence = structure_root / "analysis" / "reports" / "unexpected.md"
    task_leaf.mkdir(parents=True)
    evidence.parent.mkdir(parents=True)
    evidence.write_text("falsified\n", encoding="utf-8")
    workflow_path = task_leaf / "workflow.json"
    workflow_path.write_text(json.dumps(workflow_v2(), indent=2) + "\n", encoding="utf-8")
    source_before = workflow_path.read_bytes()

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--case-root", str(structure_root),
            "--workflow", str(workflow_path),
            "--verdict", "falsified",
            "--trigger", "approved hypothesis was falsified",
            "--proposed-change", "rerun with a denser q mesh",
            "--scientific-reason", "the completed source result is scientifically unexpected",
            "--evidence", str(evidence),
            "--parameter-change", "q_mesh=12x12x12",
            "--acceptance-rule", "the revised q mesh resolves the observable",
        ],
        check=False,
    )

    assert result.returncode == 0
    request = json.loads(
        (structure_root / "analysis" / "reports" / "design_change_request.json").read_text(
            encoding="utf-8"
        )
    )
    assert workflow_path.read_bytes() == source_before
    assert request["source_workflow"] == "structure_root:p2_scf/workflow.json"
    assert request["source_workflow_contract"] == "dft.workflow.v2"
    assert request["source_workflow_schema_version"] == 2
    assert request["source_design"]["approval_ref"].endswith("#mgb_sc:r0003")
    assert request["source_design"]["baseline_parameter_hash"] == "b" * 64
    assert request["derived_from"] == workflow_v2()["lineage"]["derived_from"]
    assert request["lineage"]["derived_from"] == workflow_v2()["lineage"]["derived_from"]
    assert request["recovery_mode"] == "create_rerun_branch"
    assert request["submission_review_required"] is False
    assert request["requires_submission_review"] is False
    assert "submit review" not in request["requested_action"].lower()
