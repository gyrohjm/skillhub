"""Exact synthetic numeric contracts; no raw DFT parser or physical acceptance."""
import copy
import json
from pathlib import Path
import subprocess
import sys

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))


def compare(*args, **kwargs):
    assert (SCRIPTS / "wannier_bands.py").is_file(), "band comparator is not implemented"
    from wannier_bands import compare_bands
    return compare_bands(*args, **kwargs)


def dataset():
    return {"schema_version": 1, "units": "eV", "energy_reference": "scf-EF-v1", "system_id": "synthetic-structure-spin-v1", "kpoint_basis": "fractional", "sampling": "independent", "matching": "explicit_band_ids", "band_ids": ["a", "b"], "kpoints": [[0, 0, 0], [0.25, 0, 0]], "energies": [[-1, 1], [-0.5, 2]]}


def test_errors_use_reference_mask_and_explicit_band_mapping():
    ref = dataset()
    candidate = dataset()
    candidate["band_ids"] = ["b", "a"]
    candidate["energies"] = [[1.1, -0.98], [2.2, -0.54]]
    result = compare(ref, candidate, target_window=(-1, 1), mae_threshold_mev=60, max_threshold_mev=110)
    assert result["target_metrics"]["count"] == 3  # candidate 1.1 stays in reference-defined target
    assert result["target_metrics"]["mae_mev"] == pytest.approx(160 / 3)
    assert result["target_metrics"]["max_error_mev"] == pytest.approx(100)
    assert result["global_metrics"]["rmse_mev"] == pytest.approx((20**2 + 100**2 + 40**2 + 200**2)**0.5 / 2)
    assert result["threshold_check"] == "PASS_ON_SUPPLIED_DATA"
    assert result["scientifically_accepted"] is None


def test_no_automatic_energy_alignment_or_candidate_band_dropping():
    ref, candidate = dataset(), dataset()
    candidate["energies"] = [[x + 1 for x in row] for row in candidate["energies"]]
    result = compare(ref, candidate, target_window=(-1, 1), mae_threshold_mev=20, max_threshold_mev=40)
    assert result["threshold_check"] == "FAIL"
    assert result["target_metrics"]["mae_mev"] == pytest.approx(1000)


@pytest.mark.parametrize("key,value", [
    ("energy_reference", "other-EF"), ("system_id", "other-spin"), ("units", "Ry"),
    ("matching", "sorted_energies"), ("kpoint_basis", "cartesian"),
    ("band_ids", ["a", "a"]), ("band_ids", ["a"]),
    ("kpoints", [[0, 0, 0], [0.5, 0, 0]]),
    ("energies", [[-1, float("nan")], [-0.5, 2]]),
    ("energies", [[-1, 1]]), ("sampling", "unknown-mode"),
])
def test_invalid_comparisons_do_not_emit_misleading_metrics(key, value):
    candidate = dataset()
    candidate[key] = value
    with pytest.raises(ValueError):
        compare(dataset(), candidate, target_window=(-1, 1))


def test_thresholds_missing_or_empty_target_are_unknown():
    assert compare(dataset(), dataset(), target_window=(-1, 1))["threshold_check"] == "UNKNOWN"
    empty = compare(dataset(), dataset(), target_window=(5, 6), mae_threshold_mev=20, max_threshold_mev=40)
    assert empty["threshold_check"] == "UNKNOWN"
    assert empty["target_metrics"]["mae_mev"] is None


@pytest.mark.parametrize("target,mae,maxerr", [((1, -1), 1, 2), ((0, float("nan")), 1, 2), ((-1, 1), -1, 2), ((-1, 1), 1, float("inf"))])
def test_invalid_window_and_thresholds_rejected(target, mae, maxerr):
    with pytest.raises(ValueError):
        compare(dataset(), dataset(), target_window=target, mae_threshold_mev=mae, max_threshold_mev=maxerr)


def test_training_grid_or_path_does_not_become_independent_validation():
    ref, candidate = dataset(), dataset()
    ref["sampling"] = candidate["sampling"] = "high_symmetry_path"
    result = compare(ref, candidate, target_window=(-1, 1), mae_threshold_mev=1, max_threshold_mev=1)
    assert result["threshold_check"] == "PASS_ON_SUPPLIED_DATA"
    assert result["independent_validation"] is False
    assert result["decision"] == "NEEDS_AGENT"


def test_compare_cli_writes_traceable_reports_and_csv(tmp_path):
    for name in ("reference", "candidate"):
        (tmp_path / f"{name}.json").write_text(json.dumps(dataset()), encoding="utf-8")
    cmd = [sys.executable, "-X", "utf8", str(SCRIPTS / "wannier_audit.py"), "compare", "--reference", str(tmp_path / "reference.json"), "--candidate", str(tmp_path / "candidate.json"), "--target-window", "-1", "1", "--mae-threshold-mev", "10", "--max-threshold-mev", "20", "--output-dir", str(tmp_path / "report")]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["sources"]["reference"]["sha256"]
    assert (tmp_path / "report" / "errors.csv").is_file()
    assert (tmp_path / "report" / "report.md").is_file()
