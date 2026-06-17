from __future__ import annotations

import json
from pathlib import Path

from vwf import cli
from vwf.parse import parse_task_dir


FORCE_BLOCK = """ POSITION                                       TOTAL-FORCE (eV/Angst)
 -----------------------------------------------------------------------------------
      0.00000      0.00000      0.00000         0.001000      0.000000      0.000000
      1.00000      1.00000      1.00000        -0.001000      0.000000      0.000000
 -----------------------------------------------------------------------------------
"""

ENERGY_LINES = """  free  energy   TOTEN  =       -10.00000000 eV
  energy  without entropy=      -10.05000000  energy(sigma->0) =      -10.10000000
 E-fermi :   5.1234     XC(G=0):  -1.0
"""


def _outcar(*, nsw: int, ibrion: int, ionic: str, electronic: str, finished: bool) -> str:
    parts = [
        "   number of ions     NIONS =      2",
        f"   NSW    =    {nsw}    number of steps for ionic update",
        f"   IBRION =      {ibrion}    ionic relaxation method",
        FORCE_BLOCK,
        ENERGY_LINES,
    ]
    if electronic:
        parts.append(electronic)
    if ionic:
        parts.append(ionic)
    if finished:
        parts.append(" Voluntary context switches:         1234")
    return "\n".join(parts) + "\n"


OSZICAR = """DAV:   1    -0.1000000000E+02   -0.10E+02
DAV:   2    -0.1010000000E+02   -0.10E-04
       1 F= -.10000000E+02 E0= -.10100000E+02  d E =-.10E+02
"""

REACHED = " reached required accuracy - stopping structural energy minimisation"
NOT_REACHED = " aborting loop: not reached required accuracy - trying to continue"
EDIFF = "- aborting loop because EDIFF is reached"


def _write(task_dir: Path, outcar: str, oszicar: str = OSZICAR, vasp_out: str | None = None) -> Path:
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "OUTCAR").write_text(outcar, encoding="utf-8")
    (task_dir / "OSZICAR").write_text(oszicar, encoding="utf-8")
    if vasp_out is not None:
        (task_dir / "vasp.out").write_text(vasp_out, encoding="utf-8")
    return task_dir


def test_converged_relax(tmp_path: Path) -> None:
    d = _write(tmp_path / "relax", _outcar(nsw=100, ibrion=2, ionic=REACHED, electronic=EDIFF, finished=True))
    r = parse_task_dir(d)
    assert r["status"] == "CONVERGED"
    assert r["converged"] is True
    assert r["converged_ionic"] is True
    assert r["finished"] is True
    assert r["final_energy"] == -10.0
    assert r["e0_energy"] == -10.1
    assert abs(r["e0_energy_per_atom"] - (-5.05)) < 1e-9
    assert abs(r["max_force"] - 0.001) < 1e-9
    assert r["nions"] == 2


def test_not_converged_relax(tmp_path: Path) -> None:
    # Finished cleanly (timing line present) but never reached accuracy.
    d = _write(tmp_path / "relax", _outcar(nsw=100, ibrion=2, ionic=NOT_REACHED, electronic="", finished=True))
    r = parse_task_dir(d)
    assert r["status"] == "NOT_CONVERGED"
    assert r["converged"] is False
    assert r["converged_ionic"] is False
    assert r["finished"] is True


def test_static_scf_converged(tmp_path: Path) -> None:
    # NSW=0 / IBRION=-1: electronic convergence alone decides the verdict.
    d = _write(tmp_path / "scf", _outcar(nsw=0, ibrion=-1, ionic="", electronic=EDIFF, finished=True))
    r = parse_task_dir(d)
    assert r["status"] == "CONVERGED"
    assert r["converged"] is True
    assert r["converged_electronic"] is True


def test_crash_is_error(tmp_path: Path) -> None:
    # Partial OUTCAR (no energy) plus a ZBRENT crash in vasp.out.
    outcar = "   number of ions     NIONS =      2\n   NSW    =    100\n   IBRION =      2\n"
    d = _write(tmp_path / "relax", outcar, oszicar="", vasp_out="ZBRENT: fatal error in bracketing!\n")
    r = parse_task_dir(d)
    assert r["error_type"] == "ZBRENT_FAILED"
    assert r["status"] == "ERROR"


def test_missing_dir(tmp_path: Path) -> None:
    r = parse_task_dir(tmp_path / "nope")
    assert r["status"] == "ERROR"
    assert r["error_type"] == "TASK_DIR_MISSING"


def test_stage_complete_requires_convergence(tmp_path: Path) -> None:
    stage = {"path": "relax", "completion_files": ["OUTCAR"], "require_convergence": True,
             "detect_failure_from_parse": True}
    # Converged -> complete, not failed.
    _write(tmp_path / "relax", _outcar(nsw=100, ibrion=2, ionic=REACHED, electronic=EDIFF, finished=True))
    assert cli.stage_complete(tmp_path, stage) is True
    assert cli.stage_failed(tmp_path, stage) is False


def test_stage_failed_on_finished_not_converged(tmp_path: Path) -> None:
    stage = {"path": "relax", "completion_files": ["OUTCAR"], "require_convergence": True,
             "detect_failure_from_parse": True}
    _write(tmp_path / "relax", _outcar(nsw=100, ibrion=2, ionic=NOT_REACHED, electronic="", finished=True))
    assert cli.stage_complete(tmp_path, stage) is False
    assert cli.stage_failed(tmp_path, stage) is True


def test_parse_cli_json_and_write(tmp_path: Path, capsys) -> None:
    d = _write(tmp_path / "relax", _outcar(nsw=100, ibrion=2, ionic=REACHED, electronic=EDIFF, finished=True))
    rc = cli.main(["parse", "--task-dir", str(d), "--json", "--write"])
    assert rc == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["status"] == "CONVERGED"
    written = json.loads((d / "parse_result.json").read_text(encoding="utf-8"))
    assert written["converged"] is True
