from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dft_contracts import validate_document  # noqa: E402


def minimal_task_design() -> dict[str, Any]:
    parameter_selection = {
        category: {
            "status": "user_specified",
            "method": "user supplied",
            "source_metadata": {"source": "user request"},
            "selected_value": value,
        }
        for category, value in {
            "basis_cutoff": 520,
            "occupations": {"ISMEAR": 0, "SIGMA": 0.05},
            "kpoints": "6x6x6",
        }.items()
    }
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
                "structure_provenance": "inputs/POSCAR",
                "assumptions": [],
            }
        ],
        "calculation_matrix": [
            {
                "id": "M1",
                "class": "production",
                "system_slug": "si_bulk",
                "case_slug": "supplied_scf",
                "purpose": "run supplied values",
                "variables": {},
                "fixed_parameters": {"ENCUT": 520},
                "stages": ["scf"],
                "completion_gate": "normal termination",
            }
        ],
        "engine_stage_envelopes": [
            {
                "matrix_id": "M1",
                "engine": "vasp",
                "structure_source": "inputs/POSCAR",
                "parameter_policy": "exact user values",
                "kpoints_policy": "exact user values",
                "pseudopotential_policy": "exact user values",
                "resource_profile": "approved-profile",
                "completion_gates": {"scf": "normal termination"},
                "parameter_selection": parameter_selection,
                "engine_parameters": {"ENCUT": 520, "ISMEAR": 0, "SIGMA": 0.05, "KPOINTS": "6x6x6"},
            }
        ],
        "execution_plan": {
            "tasks": [
                {
                    "task_slug": "p1_scf",
                    "matrix_id": "M1",
                    "stage": "scf",
                    "engine": "vasp",
                    "dependencies": [],
                    "inputs": [{"name": "POSCAR", "mode": "static", "source": "inputs/POSCAR"}],
                    "job_script": "templates/vasp.sh",
                }
            ]
        },
        "stop_conditions": ["stop after normal termination"],
        "pending_decisions": [],
    }


def test_calculation_design_schema_supports_task_mode_minimum_and_job_script() -> None:
    assert validate_document("calculation-design-v2", minimal_task_design()) == []


def test_calculation_design_schema_rejects_malformed_task_mode() -> None:
    design = minimal_task_design()
    design["design_mode"] = "routine"

    errors = validate_document("calculation-design-v2", design)

    assert errors
    assert any("design_mode" in error for error in errors)


def test_calculation_design_schema_accepts_validated_task_parameter_with_evidence_fields() -> None:
    design = minimal_task_design()
    entry = design["engine_stage_envelopes"][0]["parameter_selection"]["basis_cutoff"]
    entry.update(
        {
            "status": "validated",
            "candidate_values": [520],
            "units": "eV",
            "fixed_conditions": ["same kpoints"],
            "target_observable_ids": ["O1"],
            "acceptance_rule": "change below threshold",
            "evidence_refs": ["CV1"],
        }
    )

    assert validate_document("calculation-design-v2", design) == []


def test_calculation_design_schema_requires_task_execution_essentials() -> None:
    design = minimal_task_design()
    del design["execution_plan"]
    del design["stop_conditions"]
    del design["engine_stage_envelopes"][0]["engine_parameters"]

    errors = validate_document("calculation-design-v2", design)

    assert errors
    assert any("execution_plan" in error for error in errors)
    assert any("stop_conditions" in error for error in errors)
    assert any("engine_parameters" in error for error in errors)


def test_calculation_design_schema_requires_task_input_source_or_recipe() -> None:
    design = minimal_task_design()
    design["execution_plan"]["tasks"][0]["inputs"][0].pop("source")

    errors = validate_document("calculation-design-v2", design)

    assert errors
