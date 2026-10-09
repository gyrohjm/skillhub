from __future__ import annotations

import json
import hashlib
import subprocess
from pathlib import Path

import pytest

from qewf import cli


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_design_bundle(tmp_path: Path) -> Path:
    bundle = tmp_path / "design" / "r0001"
    bundle.mkdir(parents=True)
    design = {
        "schema_version": 2,
        "design_id": "mgb2_sc",
        "revision": 1,
        "status": "ready_for_review",
        "calculation_matrix": [{"id": "p4_d4", "stages": ["phonon_dfpt"]}],
        "engine_stage_envelopes": [{
            "matrix_id": "p4_d4",
            "engine": "quantum-espresso",
            "completion_gates": {"phonon_dfpt": "all QE programs complete"},
        }],
    }
    design_path = bundle / "calculation_design.json"
    plan_path = bundle / "computation_plan.md"
    design_path.write_text(json.dumps(design) + "\n", encoding="utf-8")
    plan_path.write_text("# approved P4 plan\n", encoding="utf-8")
    approval = {
        "schema_version": 1,
        "approval_type": "scientific_design",
        "status": "approved",
        "design_id": "mgb2_sc",
        "revision": 1,
        "scope": ["p4_d4"],
        "reviewer": "test",
        "approved_at": "2026-01-01T00:00:00Z",
        "design_file": design_path.name,
        "design_sha256": file_sha256(design_path),
        "computation_plan_file": plan_path.name,
        "computation_plan_sha256": file_sha256(plan_path),
    }
    approval_path = bundle / "approval.json"
    approval_path.write_text(json.dumps(approval) + "\n", encoding="utf-8")
    return approval_path


def make_task(tmp_path: Path, *, walltime: bool = False) -> Path:
    task = tmp_path / "p4disp"
    task.mkdir()
    (task / "scf.in").write_text(
        """&CONTROL
 calculation='scf'
 pseudo_dir='../pp'
/
&SYSTEM
 ecutwfc=90
 ecutrho=400
/
K_POINTS automatic
36 36 24 0 0 0
""",
        encoding="utf-8",
    )
    (task / "ph.in").write_text("&INPUTPH\n tr2_ph=1.0d-14\n ldisp=.true.\n nq1=4\n nq2=4\n nq3=4\n/\n", encoding="utf-8")
    pp = tmp_path / "pp"
    pp.mkdir()
    (pp / "Mg.UPF").write_text("PAW PBE Mg\n", encoding="utf-8")
    (tmp_path / "structure.json").write_text('{"cell": "approved"}\n', encoding="utf-8")
    time_line = "#SBATCH -t 01:00:00\n" if walltime else ""
    (task / "job.sh").write_text(
        """#!/bin/bash
#SBATCH -J p4disp
#SBATCH -p ExampleCPU
#SBATCH --qos=huge
#SBATCH -N 1
#SBATCH -n 112
"""
        + time_line
        + """module purge
module load example_compiler
module load qe/qe-7.0-avx512
srun --ntasks=112 pw.x -in scf.in > scf.out
srun --ntasks=112 ph.x -in ph.in > ph.out
""",
        encoding="utf-8",
    )
    return task


def register_args(task: Path) -> list[str]:
    approval = make_design_bundle(task.parent)
    return [
        "register", "--task-dir", str(task), "--task-id", "m2_p4disp",
        "--matrix-id", "p4_d4", "--stage", "phonon_dfpt", "--task-class", "validation",
        "--input", "scf.in", "--input", "ph.in", "--pseudo", "../pp/Mg.UPF",
        "--design-approval", str(approval), "--structure", "../structure.json",
        "--output", "scf.out", "--output", "ph.out", "--required-output", "mgb2.dyn0",
        "--cluster", "phoenix",
        "--remote-host", "phoenix", "--remote-dir", "/opt/example/p4disp",
        "--preapproved-by-workflow",
    ]


def test_register_review_and_submit_records_job_id(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    task = make_task(tmp_path)
    assert cli.main(register_args(task)) == 0
    assert cli.main(["review", "--task-dir", str(task), "--approve"]) == 0

    spec = json.loads((task / "task_spec.json").read_text(encoding="utf-8"))
    assert spec["schema_version"] == 2
    assert spec["contract"] == "dft.task-spec.v2"
    assert spec["engine"] == "quantum-espresso"
    assert spec["backend"] == "qewf"
    assert spec["resources"]["walltime"] is None
    assert spec["input_sha256"]["scf.in"]
    assert spec["pseudopotential_sha256"]["../pp/Mg.UPF"]
    review_text = (task / "submission_review.dat").read_text(encoding="utf-8")
    assert "calculation: scf" in review_text
    assert "calculation: scf'\n  restart_mode" not in review_text

    def fake_run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        assert command[0] == "ssh"
        assert "sha256sum" in command[2]
        assert command[2].endswith("sbatch job.sh")
        return subprocess.CompletedProcess(command, 0, "Submitted batch job 12345\n", "")

    monkeypatch.setattr(cli.subprocess, "run", fake_run)
    assert cli.main(["submit", "--task-dir", str(task)]) == 0
    state = json.loads((task / "state.json").read_text(encoding="utf-8"))
    assert state["status"] == "submitted"
    assert state["job_id"] == "12345"
    submission = json.loads((task / "submission.json").read_text(encoding="utf-8"))
    assert submission["backend"] == "qewf"


def test_tamper_after_approval_blocks_submit(tmp_path: Path) -> None:
    task = make_task(tmp_path)
    assert cli.main(register_args(task)) == 0
    assert cli.main(["review", "--task-dir", str(task), "--approve"]) == 0
    (task / "scf.in").write_text("&CONTROL\n calculation='nscf'\n/\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        cli.main(["submit", "--task-dir", str(task), "--dry-run"])


def test_explicit_prebuilt_walltime_overrides_local_default(tmp_path: Path) -> None:
    task = make_task(tmp_path, walltime=True)
    assert cli.main(register_args(task)) == 0
    review = (task / "submission_review.dat").read_text()
    assert 'walltime: "01:00:00"' in review


def test_backend_registry_marks_qe_operational() -> None:
    import dft_backend

    item = dft_backend.report("quantum-espresso")["quantum-espresso"]
    assert item["status"] == "operational"
    assert item["helper"] == "python -m qewf"
    assert item["canonical_layout_helper"] is True
    assert item["canonical_actions"] == ["initialize", "bind-approval", "reconcile", "gate", "submit"]
    assert item["canonical_submit"] is True
    assert item["canonical_helper"] == "python scripts/canonical_workflow.py initialize"


def test_parse_distinguishes_workflow_completion_from_scientific_verdict(tmp_path: Path) -> None:
    task = make_task(tmp_path)
    assert cli.main(register_args(task)) == 0
    (task / "scf.out").write_text("Program PWSCF\nJOB DONE.\n", encoding="utf-8")
    (task / "ph.out").write_text("Program PHONON\nJOB DONE.\n", encoding="utf-8")
    (task / "mgb2.dyn0").write_text("dynamical matrix\n", encoding="utf-8")
    assert cli.main(["parse", "--task-dir", str(task), "--write"]) == 0
    report = json.loads((task / "parse.json").read_text(encoding="utf-8"))
    assert report["workflow_verdict"] == "completed"
    assert report["scientific_verdict"] == "not_evaluated"


def test_parse_detects_scheduler_fatal(tmp_path: Path) -> None:
    task = make_task(tmp_path)
    assert cli.main(register_args(task)) == 0
    state = json.loads((task / "state.json").read_text(encoding="utf-8"))
    state["job_id"] = "123"
    (task / "state.json").write_text(json.dumps(state) + "\n", encoding="utf-8")
    (task / "scf.out").write_text("JOB DONE.\n", encoding="utf-8")
    (task / "ph.out").write_text("starting phonon\n", encoding="utf-8")
    (task / "slurm-123.out").write_text("Error in routine fft_type_set (6)\nMPI_ABORT\n", encoding="utf-8")
    assert cli.main(["parse", "--task-dir", str(task), "--write"]) == 1
    report = json.loads((task / "parse.json").read_text(encoding="utf-8"))
    assert report["workflow_verdict"] == "failed"
    assert report["scheduler_log"]["fatal"]
