"""Regression cases checked against W90 v3.1.0 input/output source formats."""
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from wannier_audit import InputError, check_windows, parse_eig, parse_win, parse_wout


def test_lone_frozen_min_is_invalid():
    cfg = parse_win("num_wann=1\nnum_bands=2\nmp_grid=1 1 1\ndis_froz_min=0\n")
    result = check_windows(cfg, parse_eig("1 1 0\n2 1 1\n"))
    assert result["status"] == "FAIL"
    assert "WINDOW_ORDER" in {x["code"] for x in result["issues"]}


def test_native_fatal_exit_and_following_diagnostic():
    result = parse_wout("| WANNIER90 |\nExiting.......\ndis_windows: More states in frozen window than target WFs\n")
    assert result["normal_termination"] is False
    assert any("dis_windows" in item["text"] for item in result["errors"])
    assert parse_wout("Exiting Wannier90")["normal_termination"] is None


def test_native_negative_convergence_marker():
    result = parse_wout("<<< Disentanglement convergence criteria not satisfied >>>\nAll done: wannier90 exiting\n")
    assert result["disentanglement_converged"] is False
    assert result["normal_termination"] is True


@pytest.mark.parametrize("key,value", [("dis_num_iter", 0), ("conv_window", 0), ("conv_window", -1), ("dis_conv_window", 0)])
def test_native_control_integer_domains(key, value):
    assert parse_win(f"{key}={value}")["parameters"][key] == value


def test_truncated_final_summary_is_not_complete():
    log = parse_wout("Final State\nWF centre and spread 1 (0,0,0) 0.5\nSum of centres and spreads", num_wann=1)
    assert log["final_state_complete"] is False


@pytest.mark.parametrize("text,expected", [("1 - 3, 5", [1, 2, 3, 5]), ("3:1", [1, 2, 3]), ("1 : 3; 6 - 5", [1, 2, 3, 5, 6])])
def test_native_range_notation(text, expected):
    assert parse_win(f"exclude_bands={text}")["parameters"]["exclude_bands"] == expected


def test_native_duplicate_excluded_band_is_invalid():
    with pytest.raises(InputError):
        parse_win("exclude_bands=1:3, 2")


def test_cycle_header_cannot_supply_final_state():
    log = parse_wout("Final State\nCycle:      1\nWF centre and spread 1 (0,0,0) 0.5\nSum of centres and spreads (0,0,0) 0.5\n", num_wann=1)
    assert log["final_state_complete"] is False
    assert log["final_centres"] == []
