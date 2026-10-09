from __future__ import annotations

import copy
import json
import sys
from argparse import Namespace
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import computation_design as cd  # noqa: E402


def task_design(engine: str = "vasp") -> dict[str, Any]:
    if engine == "vasp":
        parameters = {"ENCUT": 520, "ISMEAR": 0, "SIGMA": 0.05, "KPOINTS": "6x6x6"}
        inputs = [
            {"name": "INCAR", "mode": "static", "source": "inputs/p1_scf/INCAR"},
            {"name": "KPOINTS", "mode": "static", "source": "inputs/p1_scf/KPOINTS"},
            {"name": "POSCAR", "mode": "static", "source": "inputs/p1_scf/POSCAR"},
            {"name": "POTCAR", "mode": "static", "source": "inputs/p1_scf/POTCAR"},
        ]
        job_script = "templates/vasp.sh"
    else:
        parameters = {
            "ecutwfc": 80,
            "ecutrho": 640,
            "occupations": "smearing",
            "degauss": 0.01,
            "KPOINTS": "6x6x1",
        }
        inputs = [
            {"name": "pw.in", "mode": "static", "source": "inputs/p1_scf/pw.in"},
            {"name": "Si.upf", "mode": "static", "source": "inputs/p1_scf/Si.upf"},
        ]
        job_script = "templates/qe.sh"

    return {
        "schema_version": 2,
        "design_id": "si_task",
        "revision": 1,
        "status": "ready_for_review",
        "design_mode": "task",
        "project_slug": "si_project",
        "title": "Si supplied-input task",
        "systems": [
            {
                "system_slug": "si_bulk",
                "model": "Si diamond",
                "structure_provenance": "inputs/p1_scf/POSCAR",
                "assumptions": [],
            }
        ],
        "calculation_matrix": [
            {
                "id": "M1",
                "class": "production",
                "system_slug": "si_bulk",
                "case_slug": "supplied_scf",
                "purpose": "Run the supplied input exactly",
                "variables": {},
                "fixed_parameters": parameters,
                "stages": ["scf"],
                "completion_gate": "engine normal termination",
            }
        ],
        "engine_stage_envelopes": [
            {
                "matrix_id": "M1",
                "engine": engine,
                "structure_source": "inputs/p1_scf/POSCAR",
                "parameter_policy": "use supplied values exactly",
                "kpoints_policy": "use supplied KPOINTS exactly",
                "pseudopotential_policy": "use supplied pseudopotential files exactly",
                "resource_profile": "approved-profile",
                "completion_gates": {"scf": "engine normal termination"},
                "parameter_selection": {
                    "basis_cutoff": {
                        "status": "user_specified",
                        "method": "value supplied by user",
                        "source_metadata": {"source": "user request", "file": "inputs/p1_scf"},
                        "selected_value": parameters["ENCUT"] if engine == "vasp" else parameters["ecutwfc"],
                        "units": "eV" if engine == "vasp" else "Ry",
                    },
                    "occupations": {
                        "status": "user_specified",
                        "method": "value supplied by user",
                        "source_metadata": {"source": "user request", "file": "inputs/p1_scf"},
                        "selected_value": {"ISMEAR": 0, "SIGMA": 0.05}
                        if engine == "vasp"
                        else "smearing",
                        "units": "dimensionless/engine setting",
                    },
                    "kpoints": {
                        "status": "user_specified",
                        "method": "value supplied by user",
                        "source_metadata": {"source": "user request", "file": "inputs/p1_scf"},
                        "selected_value": parameters["KPOINTS"],
                        "units": "mesh",
                    },
                },
                "engine_parameters": parameters,
            }
        ],
        "execution_plan": {
            "tasks": [
                {
                    "task_slug": "p1_scf",
                    "matrix_id": "M1",
                    "stage": "scf",
                    "engine": engine,
                    "dependencies": [],
                    "inputs": inputs,
                    "job_script": job_script,
                }
            ]
        },
        "stop_conditions": ["stop after the declared completion gate is met"],
        "pending_decisions": [],
    }


def research_design_with_unvalidated_values() -> dict[str, Any]:
    design = task_design()
    design["design_mode"] = "research"
    design.update(
        {
            "research_questions": [{"id": "Q1", "question": "Which protocol supports the claim?"}],
            "hypotheses": [
                {
                    "id": "H1",
                    "statement": "The supplied protocol is adequate",
                    "falsification": "The convergence threshold is exceeded",
                }
            ],
            "observables": [
                {
                    "id": "O1",
                    "hypothesis_ids": ["H1"],
                    "quantity": "total energy",
                    "decision_rule": "change below 1 meV/atom",
                    "uncertainty_target": "1 meV/atom",
                }
            ],
            "controls": [{"id": "C1", "type": "baseline", "purpose": "reference", "fixed_or_varied": "fixed"}],
            "convergence_studies": [
                {
                    "id": "CV1",
                    "parameter": "basis_cutoff",
                    "candidate_values": [400, 520],
                    "fixed_conditions": ["same kpoints"],
                    "target_observable_ids": ["O1"],
                    "acceptance_rule": "change below 1 meV/atom",
                    "selected_value": 520,
                },
                {
                    "id": "CV2",
                    "parameter": "occupations",
                    "candidate_values": ["gaussian", "tetrahedron"],
                    "fixed_conditions": ["same cutoff"],
                    "target_observable_ids": ["O1"],
                    "acceptance_rule": "ordering unchanged",
                    "selected_value": "gaussian",
                },
                {
                    "id": "CV3",
                    "parameter": "kpoints",
                    "candidate_values": ["4x4x4", "6x6x6"],
                    "fixed_conditions": ["same cutoff"],
                    "target_observable_ids": ["O1"],
                    "acceptance_rule": "change below 1 meV/atom",
                    "selected_value": "6x6x6",
                },
            ],
            "validation_checks": [
                {"id": "V1", "type": "independent_reference", "reference": "doi:example", "acceptance_rule": "within 2%"}
            ],
            "evidence": [
                {
                    "id": "E1",
                    "claim": "reference protocol",
                    "source": "doi:example",
                    "kind": "primary_source",
                    "status": "verified",
                    "supports": ["H1"],
                }
            ],
            "uncertainty_budget": ["1 meV/atom numerical"],
            "resource_budget": {"task_count": 1, "compute": "approved", "storage": "bounded"},
        }
    )
    design["calculation_matrix"][0].update({"hypothesis_ids": ["H1"], "observable_ids": ["O1"]})
    for category, study_id in (("basis_cutoff", "CV1"), ("occupations", "CV2"), ("kpoints", "CV3")):
        entry = design["engine_stage_envelopes"][0]["parameter_selection"][category]
        entry.update(
            {
                "status": "candidate",
                "candidate_values": [entry["selected_value"]],
                "fixed_conditions": ["same user supplied settings"],
                "target_observable_ids": ["O1"],
                "acceptance_rule": "the study threshold is met",
                "evidence_refs": [study_id],
            }
        )
    return design


def write_task_project(project: Path, design: dict[str, Any]) -> Path:
    (project / "calculations").mkdir(parents=True)
    (project / "AGENTS.md").write_text("# Project rules\n", encoding="utf-8")
    plan_root = project / "plans/si/bulk"
    plan_root.mkdir(parents=True)
    design_path = plan_root / "calculation_design.json"
    design_path.write_text(json.dumps(design), encoding="utf-8")
    sync = json.dumps({"design_id": design["design_id"], "revision": design["revision"]}, separators=(",", ":"))
    (plan_root / "README.md").write_text(f"<!-- dft-design-sync: {sync} -->\n# Task\n", encoding="utf-8")
    (plan_root / "history.jsonl").write_text("", encoding="utf-8")
    return design_path


def test_task_mode_accepts_minimal_exact_vasp_and_qe_designs() -> None:
    assert cd.validate_design(task_design("vasp")) == []
    assert cd.validate_design(task_design("quantum-espresso")) == []


def test_task_mode_rejects_malformed_mode_and_missing_execution_essentials() -> None:
    malformed = task_design()
    malformed["design_mode"] = "routine"
    assert any("design_mode" in error for error in cd.validate_design(malformed))

    missing = task_design()
    del missing["engine_stage_envelopes"][0]["engine_parameters"]
    missing["engine_stage_envelopes"][0]["structure_source"] = ""
    missing["execution_plan"]["tasks"][0]["inputs"][0].pop("source")
    missing["stop_conditions"] = []
    errors = cd.validate_design(missing)
    assert any("engine_parameters" in error for error in errors)
    assert any("structure_source" in error for error in errors)
    assert any("stop_conditions" in error for error in errors)
    assert any("source" in error for error in errors)


def test_task_mode_rejects_dangling_execution_dependency() -> None:
    design = task_design()
    design["execution_plan"]["tasks"][0]["dependencies"] = ["p9_missing"]

    errors = cd.validate_execution_plan(design)

    assert any("unknown dependency" in error for error in errors)


def test_task_mode_user_specified_parameters_can_be_approved_without_research_evidence() -> None:
    design = task_design()

    assert cd.approval_errors(design, ["M1"]) == []
    assert "scientifically_accepted" not in design
    assert all(
        entry["status"] == "user_specified"
        and "selected_value" in entry
        and entry["method"]
        and entry["source_metadata"]
        for entry in design["engine_stage_envelopes"][0]["parameter_selection"].values()
    )


def test_task_mode_user_specified_parameters_ignore_unrelated_pending_evidence() -> None:
    design = research_design_with_unvalidated_values()
    design["design_mode"] = "task"
    selection = design["engine_stage_envelopes"][0]["parameter_selection"]
    for entry in selection.values():
        entry["status"] = "user_specified"
    for evidence in design["evidence"]:
        evidence["status"] = "pending"

    assert cd.validate_design(design) == []
    assert cd.approval_errors(design, ["M1"]) == []


def test_task_mode_accepts_mixed_user_specified_and_validated_parameters() -> None:
    design = research_design_with_unvalidated_values()
    design["design_mode"] = "task"
    selection = design["engine_stage_envelopes"][0]["parameter_selection"]
    selection["basis_cutoff"]["status"] = "validated"
    selection["occupations"]["status"] = "user_specified"
    selection["kpoints"]["status"] = "user_specified"

    assert cd.validate_design(design) == []
    assert cd.approval_errors(design, ["M1"]) == []


def test_task_mode_validated_parameter_requires_referenced_evidence_to_be_verified() -> None:
    design = research_design_with_unvalidated_values()
    design["design_mode"] = "task"
    selection = design["engine_stage_envelopes"][0]["parameter_selection"]
    selection["basis_cutoff"]["status"] = "validated"
    selection["basis_cutoff"]["evidence_refs"] = ["CV1", "E1"]
    selection["occupations"]["status"] = "user_specified"
    selection["kpoints"]["status"] = "user_specified"
    for evidence in design["evidence"]:
        evidence["status"] = "pending"

    errors = cd.approval_errors(design, ["M1"])

    assert any(
        "basis_cutoff requires referenced evidence to be verified" in error
        for error in errors
    )


def test_task_mode_validated_parameter_requires_selected_referenced_convergence() -> None:
    design = research_design_with_unvalidated_values()
    design["design_mode"] = "task"
    selection = design["engine_stage_envelopes"][0]["parameter_selection"]
    selection["basis_cutoff"]["status"] = "validated"
    selection["occupations"]["status"] = "user_specified"
    selection["kpoints"]["status"] = "user_specified"
    design["convergence_studies"][0]["selected_value"] = None

    errors = cd.approval_errors(design, ["M1"])

    assert any(
        "basis_cutoff requires referenced convergence studies to have selected values" in error
        for error in errors
    )


def test_task_mode_validated_parameter_still_requires_evidence() -> None:
    design = research_design_with_unvalidated_values()
    design["design_mode"] = "task"
    entry = design["engine_stage_envelopes"][0]["parameter_selection"]["basis_cutoff"]
    entry["status"] = "validated"
    entry["evidence_refs"] = []

    errors = cd.validate_design(design)

    assert any("evidence_refs must not be empty when status is validated" in error for error in errors)


def test_research_mode_still_rejects_unvalidated_production_parameters() -> None:
    design = research_design_with_unvalidated_values()

    errors = cd.approval_errors(design, ["M1"])

    assert any("parameter_selection.basis_cutoff status must be validated" in error for error in errors)
    assert any("parameter_selection.occupations status must be validated" in error for error in errors)
    assert any("parameter_selection.kpoints status must be validated" in error for error in errors)

    legacy = copy.deepcopy(design)
    del legacy["design_mode"]
    assert any("status must be validated" in error for error in cd.approval_errors(legacy, ["M1"]))


def test_task_mode_cli_validate_approve_render_and_verify_roundtrip(tmp_path: Path, capsys: Any) -> None:
    design = task_design()
    design_path = write_task_project(tmp_path, design)

    assert cd.cmd_validate(Namespace(design=design_path)) == 0
    assert cd.cmd_render(Namespace(design=design_path)) == 0
    rendered = capsys.readouterr().out
    assert "si_task" in rendered
    assert "| Design mode | `task` |" in rendered
    assert "research_questions" not in rendered

    approve_args = Namespace(
        project=tmp_path,
        composition_slug="si",
        structure_slug="bulk",
        reviewer="researcher",
        scope=["M1"],
    )
    assert cd.cmd_approve(approve_args) == 0
    history_path = tmp_path / "plans/si/bulk/history.jsonl"
    event = json.loads(history_path.read_text(encoding="utf-8").splitlines()[0])
    assert event["event_type"] == "scientific_design_approved"
    assert event["design_snapshot"]["design_mode"] == "task"
    cd.verify_approval(history_path, event["event_id"])
