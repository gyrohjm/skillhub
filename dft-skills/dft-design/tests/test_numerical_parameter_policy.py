from __future__ import annotations

from pathlib import Path


POLICY = Path(__file__).resolve().parents[1] / "references" / "numerical-parameter-policy.md"


def test_numerical_parameter_policy_is_present_and_engine_aware() -> None:
    text = POLICY.read_text(encoding="utf-8")

    for required in (
        "POTCAR",
        "ENMAX",
        "ecutwfc",
        "ecutrho",
        "ISMEAR",
        "SIGMA",
        "degauss",
        "reciprocal",
        "N_i",
        "convergence",
        "production",
    ):
        assert required in text


def test_numerical_parameter_policy_rejects_unreviewed_universal_defaults() -> None:
    text = POLICY.read_text(encoding="utf-8").lower()

    assert "universal default" in text
    assert "do not" in text
    assert "candidate" in text
    assert "evidence" in text
