from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/domain_dsi.py"
VALIDATOR = ROOT / "scripts/dftplot_dat.py"


def validate_dat(path: Path) -> None:
    assert subprocess.run([sys.executable, str(VALIDATOR), "validate", str(path)], check=False).returncode == 0


def test_domain_dsi_energy_report_and_dat(tmp_path: Path) -> None:
    result = subprocess.run([
        sys.executable,
        str(SCRIPT),
        "energy",
        "--case-root", str(tmp_path),
        "--analysis-type", "formation_energy",
        "--value", "1.25",
        "--verdict", "supported",
    ], check=False)
    assert result.returncode == 0
    dat = tmp_path / "analysis/plot_data/formation_energy.dat"
    report = tmp_path / "analysis/reports/formation_energy.md"
    assert dat.is_file()
    assert report.is_file()
    validate_dat(dat)
    assert "hypothesis_verdict: `supported`" in report.read_text(encoding="utf-8")


def test_domain_dsi_bader_and_chgdiff_outputs_validate(tmp_path: Path) -> None:
    assert subprocess.run([
        sys.executable,
        str(SCRIPT),
        "bader",
        "--case-root", str(tmp_path),
        "--charge", "1=6.1",
        "--charge", "2=3.9",
        "--verdict", "inconclusive",
    ], check=False).returncode == 0
    validate_dat(tmp_path / "analysis/plot_data/bader_charge.dat")

    assert subprocess.run([
        sys.executable,
        str(SCRIPT),
        "chgdiff",
        "--case-root", str(tmp_path),
        "--point", "0.0=0.01",
        "--point", "1.0=-0.02",
        "--verdict", "falsified",
    ], check=False).returncode == 0
    validate_dat(tmp_path / "analysis/plot_data/charge_density_difference.dat")


def test_empty_canonical_analysis_tree_does_not_hide_numbered_products(tmp_path: Path) -> None:
    (tmp_path / "analysis/plot_data").mkdir(parents=True)
    legacy = tmp_path / "9analysis"
    legacy.mkdir()
    (legacy / "existing-result.dat").write_text("legacy\n", encoding="utf-8")

    result = subprocess.run([
        sys.executable,
        str(SCRIPT),
        "energy",
        "--case-root", str(tmp_path),
        "--analysis-type", "formation_energy",
        "--value", "1.25",
        "--verdict", "supported",
    ], check=False)

    assert result.returncode == 0
    assert (legacy / "plot_data/formation_energy.dat").is_file()
    assert not (tmp_path / "analysis/plot_data/formation_energy.dat").exists()


def test_domain_dsi_rejects_bad_pair_without_traceback(tmp_path: Path) -> None:
    result = subprocess.run([
        sys.executable,
        str(SCRIPT),
        "bader",
        "--case-root", str(tmp_path),
        "--charge", "bad",
        "--verdict", "inconclusive",
    ], check=False, text=True, stderr=subprocess.PIPE)
    assert result.returncode == 1
    assert "[error]" in result.stderr
    assert "Traceback" not in result.stderr
