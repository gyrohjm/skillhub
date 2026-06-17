from __future__ import annotations

from pathlib import Path

from vwf import cli


def _result(**kw) -> dict:
    base = {"files_seen": [], "finished": True}
    base.update(kw)
    return base


# ---- plan_recovery: pure error_type -> action mapping --------------------

def test_oom_blocks() -> None:
    d = cli.plan_recovery(_result(error_type="OUT_OF_MEMORY"), {})
    assert d["action"] == "block"
    assert "memory" in d["recommendation"].lower()


def test_command_not_found_blocks() -> None:
    assert cli.plan_recovery(_result(error_type="COMMAND_NOT_FOUND"), {})["action"] == "block"


def test_numerical_failures_block() -> None:
    for et in ("ZHEGV_FAILED", "LAPACK_ERROR"):
        assert cli.plan_recovery(_result(error_type=et), {})["action"] == "block"


def test_zbrent_restarts_from_contcar() -> None:
    d = cli.plan_recovery(_result(error_type="ZBRENT_FAILED", files_seen=["CONTCAR"]), {})
    assert d["action"] == "restart_from_contcar"
    # No CONTCAR to continue from -> block.
    assert cli.plan_recovery(_result(error_type="ZBRENT_FAILED"), {})["action"] == "block"


def test_chgcar_read_failed_restages_when_source_declared() -> None:
    stage = {"inputs_from": [{"stage": "scf", "file": "CHGCAR", "link": True}]}
    assert cli.plan_recovery(_result(error_type="CHGCAR_READ_FAILED"), stage)["action"] == "restage_inputs"
    # No declared CHGCAR source -> block (flipping ICHARG is a scientific change).
    assert cli.plan_recovery(_result(error_type="CHGCAR_READ_FAILED"), {})["action"] == "block"


def test_time_limit() -> None:
    assert cli.plan_recovery(_result(error_type="TIME_LIMIT", files_seen=["CONTCAR"]), {})["action"] == "restart_from_contcar"
    assert cli.plan_recovery(_result(error_type="TIME_LIMIT"), {})["action"] == "resubmit"


def test_not_converged_relax_vs_static() -> None:
    relax = _result(converged=False, nsw=100, ibrion=2, files_seen=["CONTCAR"])
    assert cli.plan_recovery(relax, {})["action"] == "restart_from_contcar"
    static = _result(converged=False, nsw=0, ibrion=-1, files_seen=["WAVECAR"])
    assert cli.plan_recovery(static, {})["action"] == "block"


def test_allow_list_downgrades_to_block() -> None:
    stage = {"recovery_actions": []}  # nothing permitted
    d = cli.plan_recovery(_result(error_type="ZBRENT_FAILED", files_seen=["CONTCAR"]), stage)
    assert d["action"] == "block"
    assert "not allowed" in d["reason"]


# ---- try_stage_recovery: integration -------------------------------------

MIN_OUTCAR = "   number of ions     NIONS =      2\n   NSW    =    100\n   IBRION =      2\n"


def _failed_stage_dir(case: Path, vasp_out: str, *, contcar: str | None = None) -> Path:
    d = case / "relax"
    d.mkdir(parents=True, exist_ok=True)
    (d / "OUTCAR").write_text(MIN_OUTCAR, encoding="utf-8")
    (d / "vasp.out").write_text(vasp_out, encoding="utf-8")
    (d / "POSCAR").write_text("OLD-GEOMETRY", encoding="utf-8")
    if contcar is not None:
        (d / "CONTCAR").write_text(contcar, encoding="utf-8")
    return d


def test_classify_restart_archives_and_readies(tmp_path: Path) -> None:
    _failed_stage_dir(tmp_path, "ZBRENT: fatal error in bracketing!\n", contcar="NEW-GEOMETRY")
    stage = {"name": "relax", "path": "relax", "status": "failed", "auto_recover": True,
             "max_retries": 2, "retry_count": 0, "job_id": "123"}
    plan = {"auto_recover": True, "stages": [stage]}

    assert cli.try_stage_recovery(tmp_path, plan, stage, dry_run=False) is True
    assert stage["status"] == "ready"
    assert stage["retry_count"] == 1
    assert stage["last_recovery_action"] == "restart_from_contcar"
    assert "job_id" not in stage
    # CONTCAR became the new POSCAR; stale outputs archived out of the way.
    assert (tmp_path / "relax" / "POSCAR").read_text(encoding="utf-8") == "NEW-GEOMETRY"
    assert (tmp_path / "relax" / "recovery_attempts" / "attempt-1" / "OUTCAR").exists()
    assert not (tmp_path / "relax" / "OUTCAR").exists()


def test_classify_dry_run_changes_nothing(tmp_path: Path) -> None:
    _failed_stage_dir(tmp_path, "ZBRENT: fatal error in bracketing!\n", contcar="NEW-GEOMETRY")
    stage = {"name": "relax", "path": "relax", "status": "failed", "auto_recover": True,
             "max_retries": 2, "retry_count": 0}
    plan = {"auto_recover": True, "stages": [stage]}
    assert cli.try_stage_recovery(tmp_path, plan, stage, dry_run=True) is False
    assert stage["status"] == "failed"
    assert stage["retry_count"] == 0
    assert (tmp_path / "relax" / "POSCAR").read_text(encoding="utf-8") == "OLD-GEOMETRY"


def test_max_retries_blocks_idempotently(tmp_path: Path) -> None:
    _failed_stage_dir(tmp_path, "ZBRENT: fatal error in bracketing!\n", contcar="X")
    stage = {"name": "relax", "path": "relax", "status": "failed", "auto_recover": True,
             "max_retries": 1, "retry_count": 1}
    plan = {"auto_recover": True, "stages": [stage]}
    assert cli.try_stage_recovery(tmp_path, plan, stage, dry_run=False) is True   # transition -> blocked
    assert stage["status"] == "blocked"
    assert "max retries" in stage["blocked_reason"]
    assert cli.try_stage_recovery(tmp_path, plan, stage, dry_run=False) is False  # already blocked, no spam


def test_block_decision_is_idempotent(tmp_path: Path) -> None:
    _failed_stage_dir(tmp_path, "oom-kill event detected\n")
    stage = {"name": "relax", "path": "relax", "status": "failed", "auto_recover": True,
             "max_retries": 3, "retry_count": 0}
    plan = {"auto_recover": True, "stages": [stage]}
    assert cli.try_stage_recovery(tmp_path, plan, stage, dry_run=False) is True   # -> blocked (OOM)
    assert stage["status"] == "blocked"
    assert cli.try_stage_recovery(tmp_path, plan, stage, dry_run=False) is False  # same reason, no change


def test_legacy_command_strategy_still_runs(tmp_path: Path) -> None:
    d = tmp_path / "x"
    d.mkdir()
    stage = {"name": "x", "path": "x", "status": "failed", "auto_recover": True,
             "max_retries": 1, "retry_count": 0, "recovery_command": "true"}
    plan = {"auto_recover": True, "stages": [stage]}
    assert cli.try_stage_recovery(tmp_path, plan, stage, dry_run=False) is True
    assert stage["status"] == "ready"
    assert stage["retry_count"] == 1
    assert (d / "automation_recovery_1.out").exists()
