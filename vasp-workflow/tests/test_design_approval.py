from __future__ import annotations

import json
from pathlib import Path

from vwf import cli


POSCAR = """Si primitive
1.0
0.0 2.7 2.7
2.7 0.0 2.7
2.7 2.7 0.0
Si
2
Direct
0.0 0.0 0.0
0.25 0.25 0.25
"""


def write_inputs(case_root: Path) -> Path:
    (case_root / "structure").mkdir(parents=True)
    (case_root / "structure/POSCAR.initial").write_text(POSCAR, encoding="utf-8")
    potcar = case_root / "POTCAR.Si"
    potcar.write_text("TITEL = PAW_PBE Si test\n", encoding="utf-8")
    return potcar


def write_approval(root: Path, stages: list[str] | None = None) -> Path:
    review = root / "sic_computation/r0001"
    review.mkdir(parents=True)
    design = {
        "schema_version": 1,
        "design_id": "sic_computation",
        "revision": 1,
        "status": "ready_for_review",
        "calculation_matrix": [{
            "id": "M1",
            "class": "production",
            "system_slug": "sic_bulk",
            "case_slug": "stability_case",
            "stages": stages or ["relax", "scf"],
        }],
    }
    design_path = review / "calculation_design.json"
    plan_path = review / "computation_plan.md"
    design_path.write_text(json.dumps(design), encoding="utf-8")
    plan_path.write_text("# Scientific rationale\n", encoding="utf-8")
    approval = {
        "schema_version": 1,
        "approval_type": "scientific_design",
        "status": "approved",
        "design_id": "sic_computation",
        "revision": 1,
        "scope": ["M1"],
        "reviewer": "researcher",
        "approved_at": "2026-06-20T00:00:00Z",
        "design_file": design_path.name,
        "design_sha256": cli.sha256_file(design_path),
        "computation_plan_file": plan_path.name,
        "computation_plan_sha256": cli.sha256_file(plan_path),
    }
    approval_path = review / "approval.json"
    approval_path.write_text(json.dumps(approval), encoding="utf-8")
    return approval_path


def test_prepare_records_verified_design_provenance(tmp_path: Path) -> None:
    case_root = tmp_path / "case"
    potcar = write_inputs(case_root)
    approval = write_approval(tmp_path / "reviews")

    rc = cli.main([
        "prepare", "relax",
        "--case-root", str(case_root),
        "--potcar", str(potcar),
        "--encut", "520",
        "--design-approval", str(approval),
        "--design-task", "M1",
    ])
    assert rc == 0
    spec = json.loads((case_root / "relax/task_spec.json").read_text(encoding="utf-8"))
    provenance = spec["design_provenance"]
    assert provenance["scientific_design_approved"] is True
    assert provenance["design_id"] == "sic_computation"
    assert provenance["design_revision"] == 1
    assert provenance["matrix_id"] == "M1"
    snapshot = case_root / "design/sic_computation/r0001"
    assert (snapshot / "approval.json").is_file()
    workflow = json.loads((case_root / "workflow.json").read_text(encoding="utf-8"))
    assert workflow["scientific_designs"][0]["matrix_id"] == "M1"

    assert cli.main(["review", "submit", "--taskset", str(case_root / "relax")]) == 0
    review = (case_root / "relax/submission_review.dat").read_text(encoding="utf-8")
    assert "[scientific_design]" in review
    assert "approved = true" in review
    assert "matrix_id = M1" in review
    assert "scientific_design_approval_does_not_authorize_sbatch = true" in review


def test_invalid_design_hash_or_stage_blocks_before_task_creation(tmp_path: Path) -> None:
    case_root = tmp_path / "case"
    potcar = write_inputs(case_root)
    approval = write_approval(tmp_path / "reviews", stages=["scf"])
    rc = cli.main([
        "prepare", "relax",
        "--case-root", str(case_root),
        "--potcar", str(potcar),
        "--design-approval", str(approval),
        "--design-task", "M1",
    ])
    assert rc == 1
    assert not (case_root / "relax/task_spec.json").exists()

    design_path = approval.parent / "calculation_design.json"
    design_path.write_text(design_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    rc = cli.main([
        "prepare", "scf",
        "--case-root", str(case_root),
        "--source-poscar", str(case_root / "structure/POSCAR.initial"),
        "--potcar", str(potcar),
        "--design-approval", str(approval),
        "--design-task", "M1",
    ])
    assert rc == 1
    assert not (case_root / "electronic/scf/task_spec.json").exists()


def test_unapproved_legacy_prepare_is_marked_exploratory(tmp_path: Path) -> None:
    case_root = tmp_path / "case"
    potcar = write_inputs(case_root)
    assert cli.main([
        "prepare", "relax",
        "--case-root", str(case_root),
        "--potcar", str(potcar),
        "--encut", "520",
    ]) == 0
    spec = json.loads((case_root / "relax/task_spec.json").read_text(encoding="utf-8"))
    assert spec["design_provenance"]["status"] == "exploratory_untracked"
    assert spec["design_provenance"]["scientific_design_approved"] is False
