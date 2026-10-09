from __future__ import annotations

import sys
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import dftplot_dat  # noqa: E402


def test_new_contract_requires_engine(tmp_path: Path) -> None:
    path = tmp_path / "new.dat"
    path.write_text(
        "# dftplot_dat_version = 1\n"
        "# source = mock\n"
        "# units = energy:eV\n"
        "# columns = index energy_eV\n"
        "1 -1.0\n",
        encoding="utf-8",
    )
    _meta, _rows, errors = dftplot_dat.parse_dat(path)
    assert any("engine" in error for error in errors)


def test_legacy_vaplot_contract_remains_valid(tmp_path: Path) -> None:
    path = tmp_path / "legacy.dat"
    path.write_text(
        "# vaplot_dat_version = 1\n"
        "# source = mock\n"
        "# units = energy:eV\n"
        "# columns = index energy_eV\n"
        "1 -1.0\n",
        encoding="utf-8",
    )
    _meta, _rows, errors = dftplot_dat.parse_dat(path)
    assert errors == []
