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

POSCAR_SIC = """SiC primitive
1.0
0.0 2.7 2.7
2.7 0.0 2.7
2.7 2.7 0.0
Si C
1 1
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


def write_potcar_root(root: Path, labels: list[str]) -> None:
    for label in labels:
        directory = root / label
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "POTCAR").write_text(f"TITEL  = PAW_PBE {label} test\n", encoding="utf-8")


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
    assert (relax / "POSCAR-ini").exists()
    assert (relax / "POSCAR-ini").read_text(encoding="utf-8") == POSCAR
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
    assert spec["input_sources"]["job.sh"].endswith("assets/templates/jobvasp.sh")
    assert spec["incar_defaults"]["built_in_defaults"]["NSW"] == 80
    assert spec["incar_defaults"]["defaulted"][:3] == ["EDIFF", "EDIFFG", "NSW"]
    assert spec["incar_defaults"]["ediff_policy"].startswith("relax EDIFF fixed at 1E-6")

    assert cli.main(["review", "submit", "--taskset", str(relax), "--approve"]) == 0
    review = (relax / "submission_review.dat").read_text(encoding="utf-8")
    assert "INCAR.complete_begin" in review
    assert "POSCAR-ini.sha256 =" in review
    assert "POSCAR-ini.restart_rule = keep this initial geometry backup" in review
    assert "INCAR.default_source = built-in relax template defaults plus CLI overrides" in review
    assert "INCAR.built_in_defaults = EDIFF=1E-6 EDIFFG=-0.01 NSW=80" in review
    assert "INCAR.defaulted_keys = EDIFF EDIFFG NSW" in review
    assert "INCAR.ediff_policy = relax EDIFF fixed at 1E-6 by default" in review
    assert "POTCAR.functional = PBE" in review
    assert "POTCAR.user_choice_required = true" in review
    assert "job.sh.source = " in review
    assert "assets/templates/jobvasp.sh" in review
    approval = json.loads((relax / "submission_approval.json").read_text(encoding="utf-8"))
    assert approval["approved"] is True
    assert approval["review_hash"] == cli.sha256_text(review)
    stage = {"path": "relax", "review_file": "submission_review.dat", "approval_file": "submission_approval.json"}
    assert cli.stage_has_approval(tmp_path, stage) is True

    with (relax / "INCAR").open("a", encoding="utf-8") as f:
        f.write("NELM = 120\n")
    assert cli.stage_has_approval(tmp_path, stage) is False


def test_stage_has_workflow_preapproval_without_stage_approval(tmp_path: Path) -> None:
    stage_dir = tmp_path / "electronic" / "scf"
    stage_dir.mkdir(parents=True)
    for name, text in {
        "POSCAR": "RELAXED\n",
        "INCAR": "IBRION = -1\nNSW = 0\n",
        "KPOINTS": "Gamma\n",
        "POTCAR": "safe-test-potcar\n",
        "job.sh": "#!/bin/bash\n",
    }.items():
        (stage_dir / name).write_text(text, encoding="utf-8")
    resources = {"nodes": 1, "ntasks": 1, "profile": "generic"}
    cli.atomic_write_json(stage_dir / "task_spec.json", {
        "resources": resources,
        "input_hashes": cli.standard_hashes(stage_dir),
        "resource_hash": cli.resource_hash(resources, 1),
    })
    review_text = "scf review from initial workflow envelope\n"
    (stage_dir / "submission_review.dat").write_text(review_text, encoding="utf-8")

    stage = {
        "path": "electronic/scf",
        "review_file": "submission_review.dat",
        "preapproved_by_workflow": True,
    }
    assert cli.stage_has_approval(tmp_path, stage) is True

    stage["workflow_preapproved_review_hash"] = "not-the-current-review"
    assert cli.stage_has_approval(tmp_path, stage) is False
    stage["workflow_preapproved_review_hash"] = cli.sha256_text(review_text)
    assert cli.stage_has_approval(tmp_path, stage) is True

    with (stage_dir / "INCAR").open("a", encoding="utf-8") as f:
        f.write("NELM = 120\n")
    assert cli.stage_has_approval(tmp_path, stage) is False


def test_prepare_records_stage_from_symlinks(tmp_path: Path) -> None:
    assert cli.main(["init-case", "--case-root", str(tmp_path)]) == 0
    potcar = write_sources(tmp_path)
    (tmp_path / "relax" / "CONTCAR").write_text(POSCAR, encoding="utf-8")
    scf = tmp_path / "electronic" / "scf"
    scf.mkdir(parents=True, exist_ok=True)
    (scf / "CHGCAR").write_text("CHARGE\n", encoding="utf-8")
    (scf / "WAVECAR").write_text("WAVE\n", encoding="utf-8")

    rc = cli.main([
        "prepare", "band",
        "--case-root", str(tmp_path),
        "--potcar", str(potcar),
        "--encut", "520",
        "--stage-from", str(scf / "CHGCAR") + ":CHGCAR:link",
        "--stage-from", str(scf / "WAVECAR") + ":WAVECAR:link",
    ])
    assert rc == 0
    band = tmp_path / "electronic" / "band"
    assert (band / "CHGCAR").is_symlink()
    assert (band / "WAVECAR").is_symlink()
    spec = json.loads((band / "task_spec.json").read_text(encoding="utf-8"))
    assert [record["mode"] for record in spec["stage_from"]] == ["symlink", "symlink"]

    assert cli.main(["review", "submit", "--taskset", str(band)]) == 0
    review = (band / "submission_review.dat").read_text(encoding="utf-8")
    assert "[stage_from]" in review
    assert "CHGCAR -> CHGCAR (symlink; explicit --stage-from)" in review
    assert "WAVECAR -> WAVECAR (symlink; explicit --stage-from)" in review


def test_prepare_band_auto_links_existing_scf_restart_files(tmp_path: Path) -> None:
    potcar = write_sources(tmp_path)
    (tmp_path / "relax").mkdir()
    (tmp_path / "relax" / "CONTCAR").write_text(POSCAR, encoding="utf-8")
    scf = tmp_path / "electronic" / "scf"
    scf.mkdir(parents=True, exist_ok=True)
    (scf / "CHGCAR").write_text("CHARGE\n", encoding="utf-8")
    (scf / "WAVECAR").write_text("WAVE\n", encoding="utf-8")

    rc = cli.main([
        "prepare", "band",
        "--case-root", str(tmp_path),
        "--potcar", str(potcar),
        "--encut", "520",
        "--source-poscar", str(tmp_path / "relax" / "CONTCAR"),
    ])
    assert rc == 0
    band = tmp_path / "electronic" / "band"
    assert (band / "CHGCAR").is_symlink()
    assert (band / "WAVECAR").is_symlink()
    spec = json.loads((band / "task_spec.json").read_text(encoding="utf-8"))
    assert [record["origin"] for record in spec["stage_from"]] == ["automatic scf link", "automatic scf link"]


def test_init_case_can_derive_cluster_case_root(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(cli, "DEFAULT_CLUSTER_CASE_ROOT", tmp_path)

    rc = cli.main([
        "init-case",
        "--cluster", "phoenix",
        "--project-slug", "proj",
        "--system-slug", "sic_bulk",
        "--case-slug", "relax_pbe",
    ])
    assert rc == 0
    case_root = tmp_path / "proj" / "calculations" / "sic_bulk" / "relax_pbe"
    workflow = json.loads((case_root / "workflow.json").read_text(encoding="utf-8"))
    assert workflow["case_root"] == str(case_root)
    assert workflow["project_slug"] == "proj"
    assert workflow["system_slug"] == "sic_bulk"
    assert workflow["case_slug"] == "relax_pbe"
    assert workflow["cluster"] == "phoenix"
    assert workflow["case_root_source"] == "derived from project/system/case default cluster layout"


def test_prepare_auto_resolves_multielement_potcar(tmp_path: Path) -> None:
    case_root = tmp_path / "case"
    (case_root / "structure").mkdir(parents=True)
    (case_root / "structure" / "POSCAR.initial").write_text(POSCAR_SIC, encoding="utf-8")
    pot_root = tmp_path / "pot"
    write_potcar_root(pot_root, ["Si", "C"])

    rc = cli.main([
        "prepare", "relax",
        "--case-root", str(case_root),
        "--potcar-root", str(pot_root),
        "--encut", "520",
        "--kmesh", "2 2 2",
    ])
    assert rc == 0
    relax = case_root / "relax"
    potcar = (relax / "POTCAR").read_text(encoding="utf-8")
    assert "PAW_PBE Si test" in potcar
    assert "PAW_PBE C test" in potcar
    spec = json.loads((relax / "task_spec.json").read_text(encoding="utf-8"))
    assert spec["input_sources"]["POTCAR_resolution"] == "auto"
    assert spec["input_sources"]["POTCAR_root"] == str(pot_root)
    assert [item["element"] for item in spec["POTCAR_components"]] == ["Si", "C"]

    assert cli.main(["review", "submit", "--taskset", str(relax)]) == 0
    review = (relax / "submission_review.dat").read_text(encoding="utf-8")
    assert "POTCAR.resolution = auto" in review
    assert "[potcar_components]" in review
    assert "element:Si label:Si" in review
    assert "element:C label:C" in review


def test_prepare_auto_resolves_potcar_label_override(tmp_path: Path) -> None:
    case_root = tmp_path / "case"
    (case_root / "structure").mkdir(parents=True)
    (case_root / "structure" / "POSCAR.initial").write_text(POSCAR, encoding="utf-8")
    pot_root = tmp_path / "pot"
    write_potcar_root(pot_root, ["Si_GW"])

    rc = cli.main([
        "prepare", "relax",
        "--case-root", str(case_root),
        "--potcar-root", str(pot_root),
        "--potcar-label", "Si=Si_GW",
        "--encut", "520",
        "--kmesh", "2 2 2",
    ])
    assert rc == 0
    spec = json.loads((case_root / "relax" / "task_spec.json").read_text(encoding="utf-8"))
    assert spec["POTCAR_components"][0]["element"] == "Si"
    assert spec["POTCAR_components"][0]["label"] == "Si_GW"


def test_prepare_auto_potcar_missing_or_ambiguous_does_not_write_task(tmp_path: Path) -> None:
    case_root = tmp_path / "case"
    (case_root / "structure").mkdir(parents=True)
    (case_root / "structure" / "POSCAR.initial").write_text(POSCAR, encoding="utf-8")
    pot_root = tmp_path / "pot"
    pot_root.mkdir()

    rc = cli.main([
        "prepare", "relax",
        "--case-root", str(case_root),
        "--potcar-root", str(pot_root),
        "--encut", "520",
        "--kmesh", "2 2 2",
    ])
    assert rc == 1
    assert not (case_root / "relax").exists()

    write_potcar_root(pot_root / "a", ["Si"])
    write_potcar_root(pot_root / "b", ["Si"])
    rc = cli.main([
        "prepare", "relax",
        "--case-root", str(case_root),
        "--potcar-root", str(pot_root),
        "--encut", "520",
        "--kmesh", "2 2 2",
    ])
    assert rc == 1
    assert not (case_root / "relax").exists()


def test_profile_default_potcar_roots() -> None:
    assert cli.default_potcar_root("nmg") == Path("/home/jmhe/app/pot")
    assert cli.default_potcar_root("phoenix") == Path("/home/jmhe/app/pot_database")
    assert cli.default_potcar_root("phoenix-gpu-a100") == Path("/home/jmhe/app/pot_database")
    assert cli.default_potcar_root("phoenix-gpu-g3") == Path("/home/jmhe/app/pot_database")
    assert cli.default_potcar_root("generic") is None


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


def test_prepare_relax_magnetic_vdw_preset_is_grouped_and_reviewed(tmp_path: Path) -> None:
    potcar = write_sources(tmp_path)

    rc = cli.main([
        "prepare", "relax",
        "--case-root", str(tmp_path),
        "--potcar", str(potcar),
        "--incar-preset", "magnetic-vdw-relax",
        "--kmesh", "2 2 2",
    ])
    assert rc == 0
    relax = tmp_path / "relax"
    incar = (relax / "INCAR").read_text(encoding="utf-8")
    assert "# --- global ---" in incar
    assert "# --- electronic ---" in incar
    assert "# --- ionic ---" in incar
    assert "# --- output ---" in incar
    assert "ENCUT = 520" in incar
    assert "ISPIN = 2" in incar
    assert "MAGMOM = 0.05 -0.05 0.05 -0.05 0.05 -0.05 0.05 -0.05" in incar
    assert "NCORE = 14" in incar
    assert "IVDW = 12" in incar
    assert "NSW = 100" in incar
    assert "ISIF = 2" in incar

    spec = json.loads((relax / "task_spec.json").read_text(encoding="utf-8"))
    assert spec["input_sources"]["INCAR"] == "built-in relax INCAR preset magnetic-vdw-relax with CLI parameters"
    assert spec["incar_defaults"]["built_in_defaults"]["MAGMOM"].startswith("0.05 -0.05")
    assert spec["incar_defaults"]["magmom_review"].startswith("MAGMOM count")

    assert cli.main(["review", "submit", "--taskset", str(relax)]) == 0
    review = (relax / "submission_review.dat").read_text(encoding="utf-8")
    assert "INCAR.default_source = built-in magnetic-vdw-relax preset grouped by global/electronic/ionic/output" in review
    assert "INCAR.magmom_review = MAGMOM count and order must match POSCAR element/site order before submit" in review


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
    assert relax["preapproved_by_workflow"] is False
    scf = plan["stages"][1]
    assert scf["name"] == "scf"
    assert scf["incar_defaults"]["EDIFF"] == "1E-7"
    assert scf["scf_ediff_policy"] == "fixed at 1E-7 by default; changes require review envelope approval"
    assert scf["preapproved_by_workflow"] is False


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
