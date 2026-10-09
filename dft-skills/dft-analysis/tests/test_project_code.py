from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from init_project_code import initialize_template  # noqa: E402


def test_initialize_plotting_template_into_project_code(tmp_path: Path) -> None:
    (tmp_path / "calculations").mkdir(parents=True)
    (tmp_path / "AGENTS.md").write_text("# Project rules\n", encoding="utf-8")

    created = initialize_template(tmp_path, "plotting")

    target = tmp_path / "code/templates/plotting"
    assert target.joinpath("dftplot_plot.py").is_file()
    assert target.joinpath("dftplot_style.py").is_file()
    assert (tmp_path / "code/README.md").is_file()
    assert (tmp_path / "code/templates/README.md").is_file()
    assert target.joinpath("README.md").is_file()
    assert len(created) == 5


def test_initialize_template_does_not_overwrite_local_adaptation(tmp_path: Path) -> None:
    (tmp_path / "calculations").mkdir(parents=True)
    (tmp_path / "AGENTS.md").write_text("# Project rules\n", encoding="utf-8")
    target = tmp_path / "code/templates/plotting/dftplot_plot.py"
    target.parent.mkdir(parents=True)
    target.write_text("local adaptation\n", encoding="utf-8")

    initialize_template(tmp_path, "plotting")

    assert target.read_text(encoding="utf-8") == "local adaptation\n"
