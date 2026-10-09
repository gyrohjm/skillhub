from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STYLE = ROOT / "scripts" / "dftplot_style.py"
PLOT = ROOT / "scripts" / "dftplot_plot.py"

sys.path.insert(0, str(ROOT / "scripts"))
from dftplot_style import (  # noqa: E402
    AXIS_LABEL_SIZE,
    FONT_SIZE,
    LEGEND_SIZE,
    TITLE_SIZE,
    TICK_SIZE,
)


def test_house_style_uses_arial_and_28pt_for_visible_text() -> None:
    text = STYLE.read_text(encoding="utf-8")

    assert FONT_SIZE == AXIS_LABEL_SIZE == TITLE_SIZE == TICK_SIZE == LEGEND_SIZE == 28
    assert '"Arial"' in text


def test_plot_cli_requires_explicit_xy_range_plan(tmp_path: Path) -> None:
    dat = tmp_path / "dos.dat"
    dat.write_text(
        "# dftplot_dat_version = 1\n"
        "# engine = vasp\n"
        "# source = task_root:DOSCAR\n"
        "# units = energy:eV dos:states/eV\n"
        "# columns = energy_eV total_dos\n"
        "-1.0 0.1\n0.0 0.2\n1.0 0.1\n",
        encoding="utf-8",
    )
    output = tmp_path / "dos"

    missing_limits = subprocess.run(
        [sys.executable, str(PLOT), "dos", "--dat", str(dat), "--output", str(output)],
        check=False,
        text=True,
        capture_output=True,
    )
    assert missing_limits.returncode != 0
    assert "xlim" in missing_limits.stderr.lower()

    plotted = subprocess.run(
        [
            sys.executable,
            str(PLOT),
            "dos",
            "--dat",
            str(dat),
            "--output",
            str(output),
            "--xlim",
            "-2",
            "2",
            "--ylim",
            "0",
            "1",
        ],
        check=False,
        text=True,
        capture_output=True,
    )
    assert plotted.returncode == 0, plotted.stderr
    assert output.with_suffix(".png").is_file()
    assert output.with_suffix(".pdf").is_file()
