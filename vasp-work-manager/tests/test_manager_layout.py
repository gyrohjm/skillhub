from __future__ import annotations

import sys
from pathlib import Path

import pytest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import vwm_archive  # noqa: E402
import vwm_report  # noqa: E402


def test_managed_archive_destination_uses_system_and_case(tmp_path: Path) -> None:
    destination = vwm_archive.archive_destination(
        tmp_path / "archive",
        project="sic_test",
        task="sic_bulk.relax_pbe",
        stamp_value="20260619T120000Z",
        system_slug="sic_bulk",
        case_slug="relax_pbe",
    )
    assert destination == tmp_path / "archive" / "sic_bulk" / "relax_pbe" / "20260619T120000Z"


def test_managed_archive_destination_requires_both_valid_slugs(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="provided together"):
        vwm_archive.archive_destination(
            tmp_path,
            project="p",
            task="t",
            stamp_value="stamp",
            system_slug="sic_bulk",
        )
    with pytest.raises(ValueError, match="lowercase_snake_case"):
        vwm_archive.archive_destination(
            tmp_path,
            project="p",
            task="t",
            stamp_value="stamp",
            system_slug="SiC Bulk",
            case_slug="relax_pbe",
        )
    with pytest.raises(ValueError, match="project must use short English"):
        vwm_archive.archive_destination(
            tmp_path,
            project="中文项目",
            task="t",
            stamp_value="stamp",
            system_slug="sic_bulk",
            case_slug="relax_pbe",
        )


def test_legacy_archive_destination_remains_compatible(tmp_path: Path) -> None:
    destination = vwm_archive.archive_destination(
        tmp_path,
        project="legacy project",
        task="relax 001",
        stamp_value="stamp",
    )
    assert destination == tmp_path / "legacy-project" / "relax-001" / "stamp"


def test_markdown_project_summary_is_an_index(tmp_path: Path) -> None:
    output = tmp_path / "docs" / "project_summary.md"
    output.parent.mkdir()
    vwm_report.write_markdown(
        [
            {
                "task": "sic_bulk.relax_pbe",
                "task_state": "COMPLETED",
                "source_path": "/home/jmhe/projects/sic_test/calculations/sic_bulk/relax_pbe",
                "analysis_files": "analysis/plot_data/energy.dat; analysis/figures/relax.pdf",
                "archive_path": "/home/jmhe/projects/sic_test/archive/sic_bulk/relax_pbe/stamp",
                "review_status": "ACCEPTED",
                "notes": "Relaxed structure converged.",
            }
        ],
        output,
        "sic_test",
    )
    text = output.read_text(encoding="utf-8")
    assert text.startswith("# sic_test Project Summary")
    assert "sic_bulk.relax_pbe" in text
    assert "analysis/plot_data/energy.dat" in text
    assert "Relaxed structure converged." in text
