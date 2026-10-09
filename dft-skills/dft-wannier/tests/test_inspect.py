"""Synthetic adversarial cases; not a real-material fitting validation."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))


@pytest.fixture
def api():
    assert (SCRIPTS / "wannier_audit.py").is_file(), "read-only Wannier audit implementation is missing"
    import wannier_audit
    return wannier_audit


WIN = """num_wann = 2
num_bands = 3
mp_grid = 2 1 1
dis_win_min = -2
dis_win_max = 4
dis_froz_min = -1
dis_froz_max = 1
begin kpoints
0 0 0
0.5 0 0
end kpoints
"""
EIG = "1 1 -1\n2 1 0\n3 1 3\n1 2 -1\n2 2 0\n3 2 3\n"
WOUT = """| WANNIER90 |
| Release: 3.1.0 |
| Iter Delta Spread RMS Gradient Spread (Ang^2) Time |<-- CONV
1 4.0 3.0 0.25 0.1 <-- DIS
2 3.0 2.5 0.17 0.2 <-- DIS
<<< Disentanglement convergence criteria satisfied >>>
0 2.0 0.0 2.0 0.1 <-- CONV
1 -0.5 0.1 1.5 0.2 <-- CONV
<<< Wannierisation convergence criteria satisfied >>>
Final State
WF centre and spread 1 ( 0.0, 0.0, 0.0 ) 0.5
WF centre and spread 2 ( 1.0, 0.0, 0.0 ) 1.0
Sum of centres and spreads ( 1.0, 0.0, 0.0 ) 1.5
All done: wannier90 exiting
"""


def files(tmp_path, win=WIN, eig=EIG, wout=WOUT):
    paths = {}
    for suffix, content in (("win", win), ("eig", eig), ("wout", wout)):
        path = tmp_path / ("sample." + suffix)
        path.write_text(content, encoding="utf-8")
        paths[suffix] = path
    return paths


def test_win_case_comments_colons_quotes_and_projections(api):
    config = api.parse_win("NUM_WANN: 2 ! note\nnum_bands 3\nDis_Froz_Max=1D+0\nspinors = .TRUE.\nlabel='keep#!text'\nbegin projections\nB:pz\nend projections\n")
    assert config["parameters"]["num_wann"] == 2
    assert config["parameters"]["dis_froz_max"] == 1
    assert config["parameters"]["spinors"] is True
    assert config["parameters"]["label"] == "keep#!text"
    assert config["blocks"]["projections"] == ["B:pz"]
    assert config["sources"]["num_wann"] == [1]


@pytest.mark.parametrize("text", [
    "num_wann=2\nnum_wann=3", "num_wann=0", "num_bands=NaN",
    "dis_win_min=inf", "mp_grid=2 0 1", "begin projections\nB:pz",
    "begin kpoints\nend projections", "label='unclosed", "exclude_bands=3:x",
    "num_wann=2.5", "spinors=maybe", "begin kpoints\n0 0\nend kpoints",
])
def test_invalid_win_is_not_silently_accepted(api, text):
    with pytest.raises(api.InputError):
        api.parse_win(text)


def test_exclude_bands_ranges_are_normalized(api):
    cfg = api.parse_win("exclude_bands=1:3, 5-6, 8")
    assert cfg["parameters"]["exclude_bands"] == [1, 2, 3, 5, 6, 8]


@pytest.mark.parametrize("text", ["", "1 1 NaN", "1 1 inf", "0 1 2", "1 1 2\n1 1 2", "1 1 2 extra", "1 2"])
def test_bad_eig_rejected(api, text):
    with pytest.raises(api.InputError):
        api.parse_eig(text)


def test_eig_fortran_exponents(api):
    eig = api.parse_eig("2 1 1D+0\n1 1 -2.5d-1")
    assert eig == {1: {2: 1.0, 1: -0.25}}


def test_empty_log_is_unknown_and_exit_is_not_success(api):
    assert api.parse_wout("")["normal_termination"] is None
    assert api.parse_wout("Exiting Wannier90")["normal_termination"] is None
    assert api.parse_wout("Error: frozen space too large\nExiting Wannier90")["normal_termination"] is False


def test_error_overrides_success_in_same_run(api):
    log = api.parse_wout(WOUT + "\nError: write failed")
    assert log["normal_termination"] is False
    assert log["errors"][-1]["line"] > 1


def test_last_run_does_not_inherit_previous_success(api):
    log = api.parse_wout(WOUT + "\n| WANNIER90 |\n| Release: 3.1.0 |\nstarting\n")
    assert log["normal_termination"] is None
    assert log["localization_converged"] is None
    assert log["final_centres"] == []


def test_log_tables_and_final_state_not_all_iterations(api):
    text = WOUT.replace("Final State", "Initial State\nWF centre and spread 1 ( 9, 9, 9 ) 9\nFinal State")
    log = api.parse_wout(text, num_wann=2)
    assert log["omega_i_history"] == [3.0, 2.5]
    assert log["spread_history"] == [2.0, 1.5]
    assert len(log["final_centres"]) == 2
    assert log["final_state_complete"] is True
    assert log["disentanglement_converged"] is True
    assert log["localization_converged"] is True
    assert log["version"] == "3.1.0"
    assert log["spread_unit"] == "Ang^2"


def test_last_partial_final_state_is_not_replaced_with_old_good_state(api):
    log = api.parse_wout(WOUT + "\nFinal State\nWF centre and spread 1 (0,0,0) 0.1\n", num_wann=2)
    assert log["final_state_complete"] is False
    assert len(log["final_centres"]) == 1


def test_limit_is_separate_from_convergence(api):
    log = api.parse_wout("3 2.0 1.0 0.1 1.0 <-- DIS\nAll done", dis_num_iter=3)
    assert log["reached_dis_num_iter"] is True
    assert log["disentanglement_converged"] is None


def test_window_counts(api):
    report = api.check_windows(api.parse_win(WIN), api.parse_eig(EIG))
    assert report["status"] == "PASS"
    assert [r["n_frozen"] for r in report["per_k"]] == [2, 2]
    assert [r["n_outer"] for r in report["per_k"]] == [3, 3]


@pytest.mark.parametrize("win,eig,code", [
    (WIN.replace("dis_froz_max = 1", "dis_froz_max = 3"), EIG, "FROZEN_TOO_LARGE"),
    (WIN.replace("dis_win_max = 4", "dis_win_max = -0.5").replace("dis_froz_max = 1", "dis_froz_max = -0.5"), EIG, "OUTER_TOO_SMALL"),
    (WIN, EIG.replace("3 2 3\n", ""), "EIG_SHAPE"),
    (WIN, EIG.split("1 2")[0], "EIG_SHAPE"),
    (WIN.replace("dis_froz_min = -1", "dis_froz_min = -3"), EIG, "WINDOW_ORDER"),
    (WIN.replace("num_wann = 2", "num_wann = 4"), EIG, "MODEL_DIMENSION"),
])
def test_bad_windows_and_missing_k_bands_block(api, win, eig, code):
    result = api.check_windows(api.parse_win(win), api.parse_eig(eig))
    assert result["status"] == "FAIL"
    assert code in {x["code"] for x in result["issues"]}


def test_frozen_defaults_and_outer_defaults_are_explicit(api):
    cfg = api.parse_win("num_wann=2\nnum_bands=3\nmp_grid=2 1 1")
    result = api.check_windows(cfg, api.parse_eig(EIG))
    assert result["status"] == "PASS"
    assert result["per_k"][0]["n_frozen"] == 0
    assert result["window_sources"]["outer_max"] == "eigenvalue_max_default"


@pytest.mark.parametrize("setting", ["dis_froz_proj=true", "dis_spheres_num=1", "site_symmetry=true", "dis_proj_min=0.1"])
def test_special_modes_are_unknown_not_generic_pass(api, setting):
    result = api.check_windows(api.parse_win(WIN + setting + "\n"), api.parse_eig(EIG))
    assert result["status"] == "UNKNOWN"


def test_band_exclusions_require_explicit_space_and_no_double_exclusion(api):
    cfg = api.parse_win(WIN + "exclude_bands=1\n")
    assert api.check_windows(cfg, api.parse_eig(EIG))["status"] == "UNKNOWN"
    assert api.check_windows(cfg, api.parse_eig(EIG), band_space="effective")["status"] == "PASS"
    original = "".join(f"{b} {k} {e}\n" for k in (1, 2) for b, e in enumerate([-9, -1, 0, 3], 1))
    result = api.check_windows(cfg, api.parse_eig(original), band_space="original")
    assert result["status"] == "PASS"
    assert result["band_mapping"] == [{"original": 2, "effective": 1}, {"original": 3, "effective": 2}, {"original": 4, "effective": 3}]


def test_missing_expected_mesh_is_unknown(api):
    cfg = api.parse_win("num_wann=2\nnum_bands=3")
    assert api.check_windows(cfg, api.parse_eig(EIG))["status"] == "UNKNOWN"


def test_inspection_is_readonly_and_never_claims_fit_acceptance(api, tmp_path):
    paths = files(tmp_path)
    before = {p: p.read_bytes() for p in paths.values()}
    report = api.inspect(**paths)
    assert report["window_check"]["status"] == "PASS"
    assert report["decision"] == "NEEDS_AGENT"
    assert report["electronic_fit"] == "UNKNOWN"
    assert report["scientifically_accepted"] is None
    assert report["sources"]["win"]["sha256"] == hashlib.sha256(before[paths["win"]]).hexdigest()
    assert {p: p.read_bytes() for p in paths.values()} == before


def test_missing_explicit_file_is_reported(api, tmp_path):
    paths = files(tmp_path)
    report = api.inspect(win=paths["win"], wout=tmp_path / "missing.wout")
    assert report["decision"] == "NEEDS_AGENT"
    assert any(x["code"] == "MISSING_FILE" for x in report["issues"])


def test_cli_reports_json_and_refuses_existing_output(tmp_path):
    cli = SCRIPTS / "wannier_audit.py"
    assert cli.is_file(), "CLI is missing"
    paths = files(tmp_path)
    output = tmp_path / "report"
    cmd = [sys.executable, str(cli), "inspect", "--win", str(paths["win"]), "--eig", str(paths["eig"]), "--wout", str(paths["wout"]), "--output-dir", str(output)]
    result = subprocess.run(cmd, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["decision"] == "NEEDS_AGENT"
    assert (output / "report.md").is_file()
    before = (output / "report.json").read_bytes()
    again = subprocess.run(cmd, text=True, capture_output=True)
    assert again.returncode != 0
    assert (output / "report.json").read_bytes() == before


def test_cli_utf8_even_when_python_io_environment_uses_gbk(tmp_path):
    import os
    path = tmp_path / "样本.win"
    path.write_text(WIN, encoding="utf-8")
    env = {**os.environ, "PYTHONIOENCODING": "gbk"}
    result = subprocess.run([sys.executable, str(SCRIPTS / "wannier_audit.py"), "inspect", "--win", str(path)], capture_output=True, env=env)
    report = json.loads(result.stdout.decode("utf-8"))
    assert report["sources"]["win"]["path"] == str(path.resolve())
