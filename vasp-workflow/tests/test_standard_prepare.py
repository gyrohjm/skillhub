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


def write_sources(case_root: Path) -> Path:
    (case_root / "structure").mkdir(parents=True, exist_ok=True)
    (case_root / "structure" / "POSCAR.initial").write_text(POSCAR, encoding="utf-8")
    potcar = case_root / "POTCAR.Si"
    potcar.write_text("TITEL  = PAW_PBE Si 05Jan2001\n", encoding="utf-8")
    return potcar


def test_prepare_relax_and_review(tmp_path: Path) -> None:
    assert cli.main(["init-case", "--case-root", str(tmp_path)]) == 0
    potcar = write_sources(tmp_path)

    rc = cli.main([
        "prepare", "relax",
        "--case-root", str(tmp_path),
        "--potcar", str(potcar),
        "--encut", "520",
        "--kmesh", "8 8 8",
        "--profile", "nmg",
    ])
    assert rc == 0
    relax = tmp_path / "relax"
    assert (relax / "POSCAR").exists()
    incar = (relax / "INCAR").read_text(encoding="utf-8")
    assert "ENCUT = 520" in incar
    assert "EDIFF = 1E-6" in incar
    assert "EDIFFG = -0.01" in incar
    assert "NSW = 80" in incar
    assert "8 8 8" in (relax / "KPOINTS").read_text(encoding="utf-8")
    job = (relax / "job.sh").read_text(encoding="utf-8")
    assert "--ntasks-per-node=40" in job
    assert "#SBATCH -t" not in job
    assert 'cd "${SLURM_SUBMIT_DIR:-$(dirname "$0")}"' in job
    assert "module load intel_parallel" in job
    assert "module load vasp/6.4.2/avx512/orig" in job

    spec = json.loads((relax / "task_spec.json").read_text(encoding="utf-8"))
    assert spec["task_kind"] == "relax"
    assert spec["input_sources"]["POTCAR"].endswith("POTCAR.Si")
    assert spec["input_sources"]["POTCAR_functional"] == "PBE"
    assert spec["incar_defaults"]["built_in_defaults"]["NSW"] == 80
    assert spec["incar_defaults"]["defaulted"][:3] == ["EDIFF", "EDIFFG", "NSW"]
    assert spec["incar_defaults"]["ediff_policy"].startswith("relax EDIFF fixed at 1E-6")

    assert cli.main(["review", "submit", "--taskset", str(relax), "--approve"]) == 0
    review = (relax / "submission_review.dat").read_text(encoding="utf-8")
    assert "INCAR.complete_begin" in review
    assert "INCAR.default_source = built-in relax template defaults plus CLI overrides" in review
    assert "INCAR.built_in_defaults = EDIFF=1E-6 EDIFFG=-0.01 NSW=80" in review
    assert "INCAR.defaulted_keys = EDIFF EDIFFG NSW" in review
    assert "INCAR.ediff_policy = relax EDIFF fixed at 1E-6 by default" in review
    assert "POTCAR.functional = PBE" in review
    assert "POTCAR.user_choice_required = true" in review
    approval = json.loads((relax / "submission_approval.json").read_text(encoding="utf-8"))
    assert approval["approved"] is True
    assert approval["review_hash"] == cli.sha256_text(review)
    stage = {"path": "relax", "review_file": "submission_review.dat", "approval_file": "submission_approval.json"}
    assert cli.stage_has_approval(tmp_path, stage) is True

    with (relax / "INCAR").open("a", encoding="utf-8") as f:
        f.write("NELM = 120\n")
    assert cli.stage_has_approval(tmp_path, stage) is False


def test_prepare_relax_overrides_default_nsw(tmp_path: Path) -> None:
    potcar = write_sources(tmp_path)

    rc = cli.main([
        "prepare", "relax",
        "--case-root", str(tmp_path),
        "--potcar", str(potcar),
        "--encut", "520",
        "--kmesh", "2 2 2",
        "--nsw", "50",
    ])
    assert rc == 0
    relax = tmp_path / "relax"
    assert "NSW = 50" in (relax / "INCAR").read_text(encoding="utf-8")
    spec = json.loads((relax / "task_spec.json").read_text(encoding="utf-8"))
    assert spec["incar_defaults"]["overridden"] == [{"key": "NSW", "default": 80, "effective": 50}]

    assert cli.main(["review", "submit", "--taskset", str(relax)]) == 0
    review = (relax / "submission_review.dat").read_text(encoding="utf-8")
    assert "INCAR.overridden_keys = NSW:80->50" in review


def test_prepare_scf_defaults_to_tighter_ediff(tmp_path: Path) -> None:
    potcar = write_sources(tmp_path)
    (tmp_path / "relax").mkdir()
    (tmp_path / "relax" / "CONTCAR").write_text(POSCAR, encoding="utf-8")

    rc = cli.main([
        "prepare", "scf",
        "--case-root", str(tmp_path),
        "--potcar", str(potcar),
        "--encut", "520",
        "--kmesh", "12 12 12",
    ])
    assert rc == 0
    scf = tmp_path / "electronic" / "scf"
    incar = (scf / "INCAR").read_text(encoding="utf-8")
    assert "EDIFF = 1E-7" in incar
    assert "IBRION = -1" in incar
    assert "NSW = 0" in incar
    spec = json.loads((scf / "task_spec.json").read_text(encoding="utf-8"))
    assert spec["incar_defaults"]["built_in_defaults"]["EDIFF"] == "1E-7"
    assert spec["incar_defaults"]["ediff_policy"].startswith("SCF EDIFF fixed at 1E-7")

    assert cli.main(["review", "submit", "--taskset", str(scf)]) == 0
    review = (scf / "submission_review.dat").read_text(encoding="utf-8")
    assert "INCAR.default_source = built-in scf template defaults plus CLI overrides" in review
    assert "INCAR.built_in_defaults = EDIFF=1E-7 IBRION=-1 NSW=0" in review
    assert "INCAR.ediff_policy = SCF EDIFF fixed at 1E-7 by default" in review


def test_prepare_band_uses_fcc_path(tmp_path: Path) -> None:
    potcar = write_sources(tmp_path)
    (tmp_path / "relax").mkdir()
    (tmp_path / "relax" / "CONTCAR").write_text(POSCAR, encoding="utf-8")

    rc = cli.main([
        "prepare", "band",
        "--case-root", str(tmp_path),
        "--potcar", str(potcar),
        "--encut", "520",
        "--line-points", "16",
        "--source-poscar", str(tmp_path / "relax" / "CONTCAR"),
    ])
    assert rc == 0
    kpoints = (tmp_path / "electronic" / "band" / "KPOINTS").read_text(encoding="utf-8")
    assert "FCC path G-X-W-K-G-L-U-W-L-K" in kpoints
    assert "Line-mode" in kpoints
    spec = json.loads((tmp_path / "electronic" / "band" / "task_spec.json").read_text(encoding="utf-8"))
    assert spec["kpoints"]["band_path"] == "G-X-W-K-G-L-U-W-L-K"


def test_prepare_can_omit_slurm_time_limit(tmp_path: Path) -> None:
    potcar = write_sources(tmp_path)

    rc = cli.main([
        "prepare", "relax",
        "--case-root", str(tmp_path),
        "--potcar", str(potcar),
        "--encut", "520",
        "--kmesh", "2 2 2",
        "--time", "",
    ])
    assert rc == 0
    job = (tmp_path / "relax" / "job.sh").read_text(encoding="utf-8")
    assert "#SBATCH -t" not in job
    spec = json.loads((tmp_path / "relax" / "task_spec.json").read_text(encoding="utf-8"))
    assert spec["resources"]["time"] == ""


def test_prepare_phoenix_cpu_profile_matches_cluster_script(tmp_path: Path) -> None:
    potcar = write_sources(tmp_path)

    rc = cli.main([
        "prepare", "relax",
        "--case-root", str(tmp_path),
        "--potcar", str(potcar),
        "--encut", "520",
        "--kmesh", "2 2 2",
        "--profile", "phoenix",
    ])
    assert rc == 0
    relax = tmp_path / "relax"
    job = (relax / "job.sh").read_text(encoding="utf-8")
    assert "#SBATCH -N 1" in job
    assert "#SBATCH -n 112" in job
    assert "#SBATCH --ntasks-per-node=112" in job
    assert "#SBATCH -p Phoenix" in job
    assert "#SBATCH -q huge" in job
    assert "#SBATCH -t" not in job
    assert "module load intel_parallel" in job
    assert "module load vasp6.4.2-avx512" in job
    assert "unset I_MPI_PMI_LIBRARY" in job
    assert "srun vasp_std" in job

    assert cli.main(["review", "submit", "--taskset", str(relax)]) == 0
    review = (relax / "submission_review.dat").read_text(encoding="utf-8")
    assert "profile = phoenix" in review
    assert "qos = huge" in review
    assert "ntasks = 112" in review


def test_prepare_phoenix_g3_profile_records_gpu_resources(tmp_path: Path) -> None:
    potcar = write_sources(tmp_path)
    (tmp_path / "relax").mkdir()
    (tmp_path / "relax" / "CONTCAR").write_text(POSCAR, encoding="utf-8")

    rc = cli.main([
        "prepare", "scf",
        "--case-root", str(tmp_path),
        "--potcar", str(potcar),
        "--encut", "520",
        "--kmesh", "2 2 2",
        "--profile", "phoenix-gpu-g3",
    ])
    assert rc == 0
    scf = tmp_path / "electronic" / "scf"
    job = (scf / "job.sh").read_text(encoding="utf-8")
    assert "#SBATCH -p Phoenix-GPU" in job
    assert "#SBATCH -A nano" in job
    assert "#SBATCH -w g3" in job
    assert "#SBATCH --gres=gpu:h100:1" in job
    assert "#SBATCH --cpus-per-task=5" in job
    assert "module load nvhpc/22.9_mu" in job
    assert "module load cuda/12.1" in job
    assert "module load vasp6.3.2-gpu-mkl" in job
    assert "nvidia-smi" in job
    assert "mpirun -np $SLURM_NTASKS vasp_std" in job

    spec = json.loads((scf / "task_spec.json").read_text(encoding="utf-8"))
    assert spec["resources"]["account"] == "nano"
    assert spec["resources"]["nodelist"] == "g3"
    assert spec["resources"]["gres"] == "gpu:h100:1"

    assert cli.main(["review", "submit", "--taskset", str(scf)]) == 0
    review = (scf / "submission_review.dat").read_text(encoding="utf-8")
    assert "profile = phoenix-gpu-g3" in review
    assert "account = nano" in review
    assert "nodelist = g3" in review
    assert "gres = gpu:h100:1" in review


def test_prepare_phoenix_a100_profile_can_target_g2(tmp_path: Path) -> None:
    potcar = write_sources(tmp_path)
    (tmp_path / "relax").mkdir()
    (tmp_path / "relax" / "CONTCAR").write_text(POSCAR, encoding="utf-8")

    rc = cli.main([
        "prepare", "scf",
        "--case-root", str(tmp_path),
        "--potcar", str(potcar),
        "--encut", "520",
        "--kmesh", "2 2 2",
        "--profile", "phoenix-gpu-a100",
        "--nodelist", "g2",
    ])
    assert rc == 0
    scf = tmp_path / "electronic" / "scf"
    job = (scf / "job.sh").read_text(encoding="utf-8")
    assert "#SBATCH -p Phoenix-GPU" in job
    assert "#SBATCH -A nano" in job
    assert "#SBATCH -w g2" in job
    assert "#SBATCH --gres=gpu:a100:1" in job
    assert "#SBATCH --cpus-per-task=8" in job
    assert "module load vasp6.3.2-gpu-mkl" in job

    spec = json.loads((scf / "task_spec.json").read_text(encoding="utf-8"))
    assert spec["resources"]["nodelist"] == "g2"
    assert spec["resources"]["gres"] == "gpu:a100:1"


def test_automation_plan_records_relax_defaults(tmp_path: Path) -> None:
    assert cli.main(["automation", "init", "--case-root", str(tmp_path)]) == 0
    plan = json.loads(cli.automation_plan_path(tmp_path).read_text(encoding="utf-8"))
    relax = plan["stages"][0]
    assert relax["name"] == "relax"
    assert relax["incar_defaults"]["EDIFF"] == "1E-6"
    assert relax["incar_defaults"]["EDIFFG"] == "-0.01"
    assert relax["incar_defaults"]["NSW"] == 80
    assert relax["relax_ediff_policy"] == "fixed at 1E-6 by default; changes require review envelope approval"
    assert relax["relax_ediffg_policy"] == "fixed at -0.01 by default; changes require review envelope approval"
    scf = plan["stages"][1]
    assert scf["name"] == "scf"
    assert scf["incar_defaults"]["EDIFF"] == "1E-7"
    assert scf["scf_ediff_policy"] == "fixed at 1E-7 by default; changes require review envelope approval"


def test_tick_writes_review_queue_on_block(tmp_path: Path) -> None:
    plan = {
        "schema_version": 1,
        "auto_submit": True,
        "auto_recover": False,
        "stages": [
            {
                "name": "relax",
                "depends_on": [],
                "path": "relax",
                "status": "ready",
                "submit_command": "sbatch job.sh",
                "review_file": "submission_review.dat",
                "approval_file": "submission_approval.json",
            }
        ],
    }
    cli.atomic_write_json(cli.automation_plan_path(tmp_path), plan)

    assert cli.main(["automation", "tick", "--case-root", str(tmp_path)]) == 0
    saved = json.loads(cli.automation_plan_path(tmp_path).read_text(encoding="utf-8"))
    assert saved["stages"][0]["status"] == "blocked"
    queue = tmp_path / "automation" / "review_queue.jsonl"
    assert queue.exists()
    assert "missing review" in queue.read_text(encoding="utf-8")


def test_fd_queue_stage_status(tmp_path: Path) -> None:
    taskset = tmp_path / "phonon" / "fd" / "fd-001"
    state = {
        "jobs": {
            "disp-001": {"status": "done"},
            "disp-002": {"status": "done"},
        }
    }
    cli.atomic_write_json(taskset / cli.STATE_NAME, state)
    stage = {"name": "fd", "kind": "phonon-fd-worker-queue", "path": "phonon/fd/fd-001"}
    assert cli.stage_complete(tmp_path, stage) is True
    assert cli.stage_failed(tmp_path, stage) is False

    state["jobs"]["disp-002"]["status"] = "failed"
    cli.atomic_write_json(taskset / cli.STATE_NAME, state)
    assert cli.stage_complete(tmp_path, stage) is False
    assert cli.stage_failed(tmp_path, stage) is True
