from __future__ import annotations

import copy
import json
import sys
from argparse import Namespace
from pathlib import Path

import pytest


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import computation_design as cd  # noqa: E402


def valid_design(task_class: str = "exploratory") -> dict:
    return {
        "schema_version": 1,
        "design_id": "sic_computation",
        "revision": 1,
        "status": "ready_for_review",
        "project_slug": "sic_project",
        "title": "SiC computation",
        "research_questions": [{"id": "Q1", "question": "Which model is stable?"}],
        "hypotheses": [{"id": "H1", "statement": "Model A is stable", "falsification": "Model B is lower"}],
        "systems": [{"system_slug": "sic_bulk", "model": "bulk", "structure_provenance": "DOI", "assumptions": []}],
        "observables": [{
            "id": "O1",
            "hypothesis_ids": ["H1"],
            "quantity": "energy difference",
            "decision_rule": "A is lower by more than 1 meV/atom",
            "uncertainty_target": "1 meV/atom",
        }],
        "controls": [{"id": "C1", "type": "baseline", "purpose": "compare B", "fixed_or_varied": "fixed settings"}],
        "convergence_studies": [{
            "id": "CV1",
            "parameter": "ENCUT",
            "candidate_values": [400, 500, 600],
            "fixed_conditions": ["same k mesh"],
            "target_observable_ids": ["O1"],
            "acceptance_rule": "change below 1 meV/atom",
            "selected_value": 600 if task_class == "production" else None,
        }],
        "validation_checks": [{"id": "V1", "type": "literature", "reference": "doi:example", "acceptance_rule": "within 2%"}],
        "calculation_matrix": [{
            "id": "M1",
            "class": task_class,
            "system_slug": "sic_bulk",
            "case_slug": "stability_test",
            "hypothesis_ids": ["H1"],
            "purpose": "compare structures",
            "variables": {"model": ["A", "B"]},
            "fixed_parameters": {"functional": "PBE"},
            "stages": ["relax", "scf"],
            "observable_ids": ["O1"],
            "completion_gate": "both structures converged",
        }],
        "vasp_stage_envelopes": [{
            "matrix_id": "M1",
            "structure_source": "approved structures",
            "incar_policy": "reviewed explicit values",
            "kpoints_policy": "converged mesh",
            "potcar_labels": {"Si": "Si", "C": "C"},
            "resource_profile": "nmg",
            "completion_gates": {"relax": "ionic convergence", "scf": "electronic convergence"},
        }],
        "evidence": [{
            "id": "E1",
            "claim": "PBE baseline",
            "source": "doi:example",
            "kind": "primary_source",
            "status": "verified" if task_class == "production" else "pending",
            "supports": ["H1"],
        }],
        "uncertainty_budget": ["1 meV/atom numerical"],
        "resource_budget": {"task_count": 4, "compute": "100 core-hours", "storage": "1 GB"},
        "stop_conditions": ["stop after decision threshold is resolved"],
        "pending_decisions": [],
    }


def write_project(project: Path, design: dict) -> None:
    (project / "docs/plans").mkdir(parents=True)
    (project / "docs/plans/calculation_design.json").write_text(json.dumps(design), encoding="utf-8")
    (project / "docs/plans/computation_plan.md").write_text("# Approved rationale\n", encoding="utf-8")


def test_valid_design_and_missing_falsification() -> None:
    design = valid_design()
    assert cd.validate_design(design) == []
    assert cd.is_placeholder("待补充") is True
    broken = copy.deepcopy(design)
    del broken["hypotheses"][0]["falsification"]
    assert any("falsification" in error for error in cd.validate_design(broken))


def test_production_approval_requires_verified_evidence_and_selected_values() -> None:
    design = valid_design("production")
    design["evidence"][0]["status"] = "pending"
    design["convergence_studies"][0]["selected_value"] = None
    errors = cd.approval_errors(design, ["M1"])
    assert any("verified evidence" in error for error in errors)
    assert any("selected convergence" in error for error in errors)


def test_approve_verify_tamper_and_no_overwrite(tmp_path: Path) -> None:
    write_project(tmp_path, valid_design("production"))
    args = Namespace(project=tmp_path, reviewer="researcher", scope=["M1"])
    assert cd.cmd_approve(args) == 0
    approval = tmp_path / "docs/records/design_reviews/sic_computation/r0001/approval.json"
    cd.verify_approval(approval)
    with pytest.raises(cd.DesignError, match="cannot be overwritten"):
        cd.cmd_approve(args)
    snapshot = approval.parent / "calculation_design.json"
    snapshot.write_text(snapshot.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(cd.DesignError, match="hash does not match"):
        cd.verify_approval(approval)


def test_bootstrap_is_non_overwriting(tmp_path: Path) -> None:
    (tmp_path / "docs/plans").mkdir(parents=True)
    plan = tmp_path / "docs/plans/computation_plan.md"
    plan.write_text("keep me\n", encoding="utf-8")
    args = Namespace(project=tmp_path, project_slug="existing_project", dry_run=False, apply=True)
    assert cd.cmd_bootstrap(args) == 0
    assert plan.read_text(encoding="utf-8") == "keep me\n"
    design = json.loads((tmp_path / "docs/plans/calculation_design.json").read_text(encoding="utf-8"))
    assert design["project_slug"] == "existing_project"
    assert (tmp_path / "docs/records/design_reviews").is_dir()
