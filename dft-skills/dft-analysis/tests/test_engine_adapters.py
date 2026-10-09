from __future__ import annotations

import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT.parent / "dft-contracts"))

from adapters import parse_quantum_espresso, parse_vasp  # noqa: E402
from dft_contracts import validate_document  # noqa: E402


FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_vasp_real_fixture_emits_result_contract() -> None:
    result = parse_vasp(FIXTURES / "vasp_scf")
    assert result["engine_version"].startswith("5.4.4")
    assert result["termination"]["normal"] is True
    assert result["convergence"]["electronic"] is True
    assert result["energy"]["total_eV"] == -18.44422599
    assert result["energy"]["per_atom_eV"] == -9.222112995
    assert result["final_structure"]["counts"] == [2]
    assert result["stress"]["tensor_voigt_GPa"][0] == 0.700625
    assert math.isclose(result["electronic_structure"]["band_gap_eV"], 1.3)
    assert result["electronic_structure"]["dos"]["spin_channels"] == 1
    assert validate_document("result-v1", result) == []


def test_qe_real_fixture_converts_native_units() -> None:
    result = parse_quantum_espresso(FIXTURES / "qe_scf")
    assert result["engine_version"] == "7.0"
    assert result["termination"]["normal"] is True
    assert result["convergence"]["electronic"] is True
    assert math.isclose(result["energy"]["total_eV"], -164.34717526 * 13.605693122994)
    assert result["forces"]["max_norm_eV_per_A"] > 0
    assert result["stress"]["tensor_GPa"][2][2] == 0.002
    assert len(result["electronic_structure"]["bands"]["bands"]) == 2
    assert result["electronic_structure"]["band_gap_eV"] is None
    assert validate_document("result-v1", result) == []
