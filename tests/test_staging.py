from __future__ import annotations

import json
from pathlib import Path

from vwf import cli


def _stage(name: str, path: str, status: str = "planned", **extra) -> dict:
    s = {"name": name, "path": path, "status": status, "depends_on": []}
    s.update(extra)
    return s


def test_stage_inputs_copies_and_is_idempotent(tmp_path: Path) -> None:
    (tmp_path / "relax").mkdir()
    (tmp_path / "relax" / "CONTCAR").write_text("RELAXED-GEOMETRY", encoding="utf-8")
    relax = _stage("relax", "relax", status="done")
    scf = _stage("scf", "electronic/scf", depends_on=["relax"],
                 inputs_from=[{"stage": "relax", "file": "CONTCAR", "to": "POSCAR"}])
    by_name = {"relax": relax, "scf": scf}

    res = cli.stage_inputs(tmp_path, scf, by_name, dry_run=False)
    assert res["changed"] is True
    assert res["missing"] == []
    poscar = tmp_path / "electronic" / "scf" / "POSCAR"
    assert poscar.read_text(encoding="utf-8") == "RELAXED-GEOMETRY"
    manifest = json.loads((tmp_path / "electronic" / "scf" / "staged_inputs.json").read_text(encoding="utf-8"))
    assert manifest["records"][0]["to"].endswith("POSCAR")
    assert "sha256" in manifest["records"][0]  # small file -> hashed for provenance

    # Second run: destination already current -> no change.
    res2 = cli.stage_inputs(tmp_path, scf, by_name, dry_run=False)
    assert res2["changed"] is False
    assert res2["staged"] == []


def test_stage_inputs_missing_required(tmp_path: Path) -> None:
    relax = _stage("relax", "relax", status="done")  # no CONTCAR written
    scf = _stage("scf", "electronic/scf", depends_on=["relax"],
                 inputs_from=[{"stage": "relax", "file": "CONTCAR", "to": "POSCAR"}])
    res = cli.stage_inputs(tmp_path, scf, {"relax": relax, "scf": scf}, dry_run=False)
    assert res["changed"] is False
    assert res["missing"] and "CONTCAR" in res["missing"][0]


def test_stage_inputs_optional_missing_is_skipped(tmp_path: Path) -> None:
    relax = _stage("relax", "relax", status="done")
    scf = _stage("scf", "electronic/scf", depends_on=["relax"],
                 inputs_from=[{"stage": "relax", "file": "CHGCAR", "optional": True}])
    res = cli.stage_inputs(tmp_path, scf, {"relax": relax, "scf": scf}, dry_run=False)
    assert res["changed"] is False
    assert res["missing"] == []


def test_stage_inputs_link(tmp_path: Path) -> None:
    (tmp_path / "electronic" / "scf").mkdir(parents=True)
    (tmp_path / "electronic" / "scf" / "CHGCAR").write_text("CHARGE-DENSITY", encoding="utf-8")
    scf = _stage("scf", "electronic/scf", status="done")
    band = _stage("band", "electronic/band", depends_on=["scf"],
                  inputs_from=[{"stage": "scf", "file": "CHGCAR", "link": True}])
    res = cli.stage_inputs(tmp_path, band, {"scf": scf, "band": band}, dry_run=False)
    assert res["changed"] is True
    linked = tmp_path / "electronic" / "band" / "CHGCAR"
    assert linked.is_symlink()
    assert linked.read_text(encoding="utf-8") == "CHARGE-DENSITY"
    # Idempotent for links too.
    assert cli.stage_inputs(tmp_path, band, {"scf": scf, "band": band}, dry_run=False)["changed"] is False


def _write_plan(case_root: Path, plan: dict) -> Path:
    path = cli.automation_plan_path(case_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    cli.atomic_write_json(path, plan)
    return path


def test_tick_stages_then_promotes(tmp_path: Path) -> None:
    (tmp_path / "relax").mkdir()
    (tmp_path / "relax" / "CONTCAR").write_text("RELAXED", encoding="utf-8")
    plan = {
        "schema_version": 1, "auto_submit": False, "auto_recover": False,
        "stages": [
            {"name": "relax", "depends_on": [], "path": "relax", "status": "done"},
            {"name": "scf", "depends_on": ["relax"], "path": "electronic/scf", "status": "planned",
             "review_file": "submission_review.dat", "approval_file": "submission_approval.json",
             "inputs_from": [{"stage": "relax", "file": "CONTCAR", "to": "POSCAR"}]},
        ],
    }
    plan_path = _write_plan(tmp_path, plan)

    rc = cli.main(["automation", "tick", "--case-root", str(tmp_path)])
    assert rc == 0
    assert (tmp_path / "electronic" / "scf" / "POSCAR").read_text(encoding="utf-8") == "RELAXED"
    saved = json.loads(plan_path.read_text(encoding="utf-8"))
    scf = {s["name"]: s for s in saved["stages"]}["scf"]
    assert scf["status"] == "ready"


def test_tick_dry_run_does_not_write(tmp_path: Path) -> None:
    (tmp_path / "relax").mkdir()
    (tmp_path / "relax" / "CONTCAR").write_text("RELAXED", encoding="utf-8")
    plan = {
        "schema_version": 1, "auto_submit": False, "auto_recover": False,
        "stages": [
            {"name": "relax", "depends_on": [], "path": "relax", "status": "done"},
            {"name": "scf", "depends_on": ["relax"], "path": "electronic/scf", "status": "planned",
             "inputs_from": [{"stage": "relax", "file": "CONTCAR", "to": "POSCAR"}]},
        ],
    }
    plan_path = _write_plan(tmp_path, plan)

    rc = cli.main(["automation", "tick", "--case-root", str(tmp_path), "--dry-run"])
    assert rc == 0
    assert not (tmp_path / "electronic" / "scf" / "POSCAR").exists()
    saved = json.loads(plan_path.read_text(encoding="utf-8"))
    scf = {s["name"]: s for s in saved["stages"]}["scf"]
    assert scf["status"] == "planned"  # dry run must not persist promotion
