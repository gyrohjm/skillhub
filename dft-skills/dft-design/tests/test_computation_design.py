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
    production = task_class == "production"
    return {
        "schema_version": 2,
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
        "convergence_studies": [
            {
                "id": "CV1",
                "parameter": "basis_cutoff",
                "candidate_values": [400, 500, 600],
                "fixed_conditions": ["same k mesh and occupations"],
                "target_observable_ids": ["O1"],
                "acceptance_rule": "change below 1 meV/atom",
                "selected_value": 600 if production else None,
            },
            {
                "id": "CV2",
                "parameter": "kpoints",
                "candidate_values": ["4x4x4", "6x6x6", "8x8x8"],
                "fixed_conditions": ["same cutoff and occupations"],
                "target_observable_ids": ["O1"],
                "acceptance_rule": "change below 1 meV/atom",
                "selected_value": "6x6x6" if production else None,
            },
            {
                "id": "CV3",
                "parameter": "occupations",
                "candidate_values": ["gaussian_0.05_eV", "tetrahedron"],
                "fixed_conditions": ["same cutoff and k mesh"],
                "target_observable_ids": ["O1"],
                "acceptance_rule": "energy ordering unchanged",
                "selected_value": "gaussian_0.05_eV" if production else None,
            },
        ],
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
        "engine_stage_envelopes": [{
            "matrix_id": "M1",
            "engine": "vasp",
            "structure_source": "approved structures",
            "parameter_policy": "reviewed explicit values",
            "kpoints_policy": "converged mesh",
            "pseudopotential_policy": {"Si": "Si", "C": "C"},
            "resource_profile": "nmg",
            "completion_gates": {"relax": "ionic convergence", "scf": "electronic convergence"},
            "parameter_selection": {
                "basis_cutoff": {
                    "status": "validated" if production else "candidate",
                    "method": "POTCAR ENMAX plus observable convergence",
                    "source_metadata": {"max_enmax_eV": 400, "labels": ["Si", "C"]},
                    "candidate_values": [400, 500, 600],
                    "units": "eV",
                    "fixed_conditions": ["same k mesh and occupations"],
                    "target_observable_ids": ["O1"],
                    "acceptance_rule": "change below 1 meV/atom",
                    "selected_value": 600 if production else None,
                    "evidence_refs": ["CV1"] if production else [],
                },
                "occupations": {
                    "status": "validated" if production else "candidate",
                    "method": "material class and stage plus convergence",
                    "source_metadata": {"material_class": "semiconductor", "stage": "scf"},
                    "candidate_values": ["gaussian_0.05_eV", "tetrahedron"],
                    "units": "eV",
                    "fixed_conditions": ["same cutoff and k mesh"],
                    "target_observable_ids": ["O1"],
                    "acceptance_rule": "energy ordering unchanged",
                    "selected_value": "gaussian_0.05_eV" if production else None,
                    "evidence_refs": ["CV3"] if production else [],
                },
                "kpoints": {
                    "status": "validated" if production else "candidate",
                    "method": "reciprocal spacing estimate plus convergence",
                    "source_metadata": {"target_spacing_per_A": 0.2, "centering": "gamma"},
                    "candidate_values": ["4x4x4", "6x6x6", "8x8x8"],
                    "units": "1/angstrom",
                    "fixed_conditions": ["same cutoff and occupations"],
                    "target_observable_ids": ["O1"],
                    "acceptance_rule": "change below 1 meV/atom",
                    "selected_value": "6x6x6" if production else None,
                    "evidence_refs": ["CV2"] if production else [],
                },
            },
            "engine_parameters": (
                {"ENCUT": 600, "ISMEAR": 0, "SIGMA": 0.05, "KPOINTS": "6x6x6"}
                if production else {}
            ),
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


def two_task_execution_plan() -> dict:
    return {
        "tasks": [
            {
                "task_slug": "p1_relax",
                "matrix_id": "M1",
                "stage": "relax",
                "engine": "vasp",
                "dependencies": [],
                "inputs": [
                    {
                        "name": "INCAR",
                        "mode": "static",
                        "source": "plans/mgb2/bulk/inputs/p1_relax/INCAR",
                    },
                    {
                        "name": "KPOINTS",
                        "mode": "static",
                        "source": "plans/mgb2/bulk/inputs/p1_relax/KPOINTS",
                    },
                    {
                        "name": "POSCAR",
                        "mode": "static",
                        "source": "plans/mgb2/bulk/inputs/p1_relax/POSCAR",
                    },
                    {
                        "name": "POTCAR",
                        "mode": "static",
                        "source": "plans/mgb2/bulk/inputs/p1_relax/POTCAR",
                    },
                ],
            },
            {
                "task_slug": "p2_scf",
                "matrix_id": "M1",
                "stage": "scf",
                "engine": "vasp",
                "dependencies": ["p1_relax"],
                "inputs": [
                    {
                        "name": "INCAR",
                        "mode": "static",
                        "source": "plans/mgb2/bulk/inputs/p2_scf/INCAR",
                    },
                    {
                        "name": "KPOINTS",
                        "mode": "static",
                        "source": "plans/mgb2/bulk/inputs/p2_scf/KPOINTS",
                    },
                    {
                        "name": "POTCAR",
                        "mode": "static",
                        "source": "plans/mgb2/bulk/inputs/p2_scf/POTCAR",
                    },
                    {
                        "name": "POSCAR",
                        "mode": "recipe",
                        "source_task": "p1_relax",
                        "artifact": "CONTCAR",
                    },
                ],
            },
        ]
    }


def valid_dsi_design() -> dict:
    design = valid_design("production")
    design["domain_pack"] = "defects-surfaces-interfaces"
    design["domain_metadata"] = {
        "defect_type": "vacancy",
        "charge_state": 0,
        "reference_cases": {"bulk_reference": "M_bulk"},
        "production_lock": {
            "supercell_size": "2x2x2",
            "k_mesh": "3x3x3",
            "ENCUT": 520,
            "smearing": "ISMEAR=0 SIGMA=0.05",
            "dipole_correction": "not_applicable for bulk neutral defect",
            "charge_state": 0,
            "chemical_potential": "Si-rich reference from M_bulk",
            "finite_size_correction": "not_applicable for neutral defect",
            "reference_structure": "M_bulk",
        },
    }
    design["controls"] = [
        {
            "id": "C1",
            "type": "baseline",
            "purpose": "bulk_reference control for defect formation energy",
            "fixed_or_varied": "fixed functional, ENCUT, k_mesh, smearing",
        }
    ]
    design["convergence_studies"] = [
        {
            "id": "CV1",
            "parameter": "ENCUT",
            "candidate_values": [420, 520, 600],
            "fixed_conditions": ["same supercell and k_mesh"],
            "target_observable_ids": ["O1"],
            "acceptance_rule": "formation energy changes below 0.02 eV",
            "selected_value": 520,
        },
        {
            "id": "CV2",
            "parameter": "k_mesh",
            "candidate_values": ["2x2x2", "3x3x3"],
            "fixed_conditions": ["same ENCUT"],
            "target_observable_ids": ["O1"],
            "acceptance_rule": "formation energy changes below 0.02 eV",
            "selected_value": "3x3x3",
        },
        {
            "id": "CV3",
            "parameter": "smearing",
            "candidate_values": ["ISMEAR=0 SIGMA=0.05", "ISMEAR=-5"],
            "fixed_conditions": ["same ENCUT and k_mesh"],
            "target_observable_ids": ["O1"],
            "acceptance_rule": "energy ordering unchanged",
            "selected_value": "ISMEAR=0 SIGMA=0.05",
        },
        {
            "id": "CV4",
            "parameter": "supercell_size",
            "candidate_values": ["2x2x2", "3x3x3"],
            "fixed_conditions": ["same defect charge_state"],
            "target_observable_ids": ["O1"],
            "acceptance_rule": "formation energy changes below 0.05 eV",
            "selected_value": "2x2x2",
        },
    ]
    design["calculation_matrix"][0].update({
        "id": "M_defect",
        "system_slug": "sic_bulk",
        "case_slug": "v_si_neutral",
        "purpose": "compute neutral vacancy formation energy",
        "variables": {"defect_type": "vacancy", "charge_state": 0},
        "fixed_parameters": {"reference_case": "M_bulk"},
        "stages": ["defect_relax", "static_energy", "bader"],
    })
    design["engine_stage_envelopes"][0]["matrix_id"] = "M_defect"
    return design


def write_project(project: Path, design: dict) -> None:
    (project / "calculations").mkdir(parents=True)
    (project / "AGENTS.md").write_text("# Project rules\n", encoding="utf-8")
    plan_root = project / "plans/mgb2/ref_struct"
    plan_root.mkdir(parents=True)
    (plan_root / "calculation_design.json").write_text(json.dumps(design), encoding="utf-8")
    sync = json.dumps(
        {"design_id": design["design_id"], "revision": design["revision"]},
        separators=(",", ":"),
    )
    (plan_root / "README.md").write_text(
        f"<!-- dft-design-sync: {sync} -->\n# Approved rationale\n",
        encoding="utf-8",
    )
    (plan_root / "history.jsonl").write_text("", encoding="utf-8")


def test_valid_design_and_missing_falsification() -> None:
    design = valid_design()
    assert cd.validate_design(design) == []
    assert cd.is_placeholder("待补充") is True
    broken = copy.deepcopy(design)
    del broken["hypotheses"][0]["falsification"]
    assert any("falsification" in error for error in cd.validate_design(broken))


def test_execution_plan_accepts_complete_production_task_tree() -> None:
    design = valid_design("production")
    design["execution_plan"] = two_task_execution_plan()

    assert cd.validate_execution_plan(design) == []


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda plan: plan["tasks"].__setitem__(1, {**plan["tasks"][1], "task_slug": "p1_relax"}), "duplicate"),
        (lambda plan: plan["tasks"][1]["dependencies"].__setitem__(0, "p9_missing"), "unknown dependency"),
        (
            lambda plan: (
                plan["tasks"][0]["dependencies"].append("p2_scf"),
                plan["tasks"][1]["dependencies"].append("p1_relax"),
            ),
            "cycle",
        ),
        (lambda plan: plan["tasks"][1].__setitem__("stage", "band"), "stage"),
        (lambda plan: plan["tasks"][0]["inputs"][0].__setitem__("source", "../INCAR"), "safe"),
    ],
)
def test_execution_plan_rejects_structural_errors(change, message: str) -> None:
    design = valid_design("production")
    design["execution_plan"] = two_task_execution_plan()
    change(design["execution_plan"])

    assert any(message in error.lower() for error in cd.validate_execution_plan(design))


def test_schema_v1_vasp_envelope_remains_readable() -> None:
    design = valid_design()
    design["schema_version"] = 1
    envelope = design.pop("engine_stage_envelopes")[0]
    design["vasp_stage_envelopes"] = [{
        "matrix_id": envelope["matrix_id"],
        "structure_source": envelope["structure_source"],
        "incar_policy": envelope["parameter_policy"],
        "kpoints_policy": envelope["kpoints_policy"],
        "potcar_labels": envelope["pseudopotential_policy"],
        "resource_profile": envelope["resource_profile"],
        "completion_gates": envelope["completion_gates"],
    }]
    assert cd.validate_design(design) == []
    assert cd.engine_envelopes(design)[0]["engine"] == "vasp"


def test_schema_v2_requires_known_engine() -> None:
    design = valid_design()
    design["engine_stage_envelopes"][0]["engine"] = "mystery-code"
    assert any(".engine must be one of" in error for error in cd.validate_design(design))


def test_schema_v2_requires_structured_parameter_selection() -> None:
    design = valid_design()
    del design["engine_stage_envelopes"][0]["parameter_selection"]
    assert any("parameter_selection is required" in error for error in cd.validate_design(design))

    incomplete = valid_design()
    del incomplete["engine_stage_envelopes"][0]["parameter_selection"]["kpoints"]["source_metadata"]
    assert any("parameter_selection.kpoints.source_metadata" in error for error in cd.validate_design(incomplete))


def test_phonon_domain_contract_requires_method_specific_metadata() -> None:
    design = valid_design()
    design["domain_pack"] = "phonon-thermodynamics"
    design["domain_metadata"] = {
        "method": "finite_displacement",
        "supercell": [3, 3, 1],
        "displacement_distance_A": 0.01,
        "imaginary_frequency_tolerance_cm1": 5.0,
    }
    assert cd.validate_design(design) == []
    design["domain_metadata"]["supercell"] = [3, 0, 1]
    assert any("supercell" in error for error in cd.validate_design(design))


def test_neb_domain_contract_enforces_image_and_force_gates() -> None:
    design = valid_design()
    design["domain_pack"] = "migration-neb"
    design["domain_metadata"] = {
        "initial_state": "relax.initial",
        "final_state": "relax.final",
        "image_count": 5,
        "interpolation_method": "idpp",
        "climbing_image": True,
        "force_threshold_eV_per_A": 0.03,
    }
    assert cd.validate_design(design) == []


def test_production_approval_requires_verified_evidence_and_selected_values() -> None:
    design = valid_design("production")
    design["evidence"][0]["status"] = "pending"
    design["convergence_studies"][0]["selected_value"] = None
    errors = cd.approval_errors(design, ["M1"])
    assert any("verified evidence" in error for error in errors)
    assert any("selected convergence" in error for error in errors)


def test_production_approval_requires_validated_parameters_and_exact_engine_values() -> None:
    design = valid_design("production")
    envelope = design["engine_stage_envelopes"][0]
    envelope["parameter_selection"]["basis_cutoff"]["status"] = "candidate"
    envelope["parameter_selection"]["basis_cutoff"]["selected_value"] = None
    envelope["engine_parameters"] = {}

    errors = cd.approval_errors(design, ["M1"])

    assert any("basis_cutoff status must be validated" in error for error in errors)
    assert any("basis_cutoff selected_value" in error for error in errors)
    assert any("engine_parameters must contain exact" in error for error in errors)


def test_cmd_validate_requires_compact_plan_files_and_synced_readme(tmp_path: Path) -> None:
    design = valid_design()
    write_project(tmp_path, design)
    plan_root = tmp_path / "plans/mgb2/ref_struct"
    args = Namespace(design=plan_root / "calculation_design.json")

    assert cd.cmd_validate(args) == 0

    (plan_root / "history.jsonl").unlink()
    assert cd.cmd_validate(args) == 1

    (plan_root / "history.jsonl").write_text("", encoding="utf-8")
    stale = json.dumps({"design_id": design["design_id"], "revision": 2}, separators=(",", ":"))
    (plan_root / "README.md").write_text(
        f"<!-- dft-design-sync: {stale} -->\n# stale\n",
        encoding="utf-8",
    )
    assert cd.cmd_validate(args) == 1


def test_dsi_domain_pack_validates_required_references_and_locks() -> None:
    design = valid_dsi_design()
    assert cd.validate_design(design) == []

    missing_reference = copy.deepcopy(design)
    missing_reference["domain_metadata"]["reference_cases"] = {}
    assert any("bulk_reference" in error for error in cd.validate_design(missing_reference))

    missing_lock = copy.deepcopy(design)
    del missing_lock["domain_metadata"]["production_lock"]["chemical_potential"]
    assert any("chemical_potential" in error for error in cd.validate_design(missing_lock))

    missing_convergence = copy.deepcopy(design)
    missing_convergence["convergence_studies"] = [
        item for item in missing_convergence["convergence_studies"] if item["parameter"] != "supercell_size"
    ]
    assert any("supercell_size" in error for error in cd.validate_design(missing_convergence))


def test_approve_appends_one_history_event_and_detects_tampering(tmp_path: Path) -> None:
    write_project(tmp_path, valid_design("production"))
    args = Namespace(
        project=tmp_path,
        composition_slug="mgb2",
        structure_slug="ref_struct",
        reviewer="researcher",
        scope=["M1"],
    )
    assert cd.cmd_approve(args) == 0
    history = tmp_path / "plans/mgb2/ref_struct/history.jsonl"
    lines = history.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    event = json.loads(lines[0])
    assert event["event_id"] == "sic_computation:r0001"
    assert event["event_type"] == "scientific_design_approved"
    assert event["scope"] == ["M1"]
    cd.verify_approval(history, event["event_id"])
    with pytest.raises(cd.DesignError, match="cannot be overwritten"):
        cd.cmd_approve(args)
    event["design_snapshot"]["title"] = "tampered"
    history.write_text(json.dumps(event) + "\n", encoding="utf-8")
    with pytest.raises(cd.DesignError, match="hash does not match"):
        cd.verify_approval(history, event["event_id"])


def test_bootstrap_is_non_overwriting(tmp_path: Path) -> None:
    (tmp_path / "calculations").mkdir(parents=True)
    (tmp_path / "AGENTS.md").write_text("# Project rules\n", encoding="utf-8")
    plan_root = tmp_path / "plans/mgb2/ref_struct"
    plan_root.mkdir(parents=True)
    plan = plan_root / "README.md"
    plan.write_text("keep me\n", encoding="utf-8")
    args = Namespace(
        project=tmp_path,
        project_slug="existing_project",
        composition_slug="mgb2",
        structure_slug="ref_struct",
        dry_run=False,
        apply=True,
    )
    assert cd.cmd_bootstrap(args) == 0
    assert plan.read_text(encoding="utf-8") == "keep me\n"
    design = json.loads((plan_root / "calculation_design.json").read_text(encoding="utf-8"))
    assert design["project_slug"] == "existing_project"
    assert {item.name for item in plan_root.iterdir()} == {
        "README.md",
        "calculation_design.json",
        "history.jsonl",
    }
    assert not (tmp_path / "docs/records/design_reviews").exists()
    assert not (tmp_path / "plans/README.md").exists()
    assert not (tmp_path / "plans/mgb2/README.md").exists()
    assert not (tmp_path / "docs/plans").exists()


def test_apply_engine_parameter_overrides_returns_revised_design_without_mutating_source() -> None:
    design = valid_design("production")

    revised = cd.apply_engine_parameter_overrides(design, "M1", {"ENCUT": 650})

    assert revised is not design
    assert revised["revision"] == design["revision"] + 1
    assert revised["engine_stage_envelopes"][0]["engine_parameters"]["ENCUT"] == 650
    assert design["engine_stage_envelopes"][0]["engine_parameters"]["ENCUT"] == 600
