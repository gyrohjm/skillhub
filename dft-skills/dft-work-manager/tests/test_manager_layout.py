from __future__ import annotations

import sys
from pathlib import Path

import pytest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import vwm_archive  # noqa: E402
import vwm_ledger  # noqa: E402
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
                "source_path": "/opt/example/projects/sic_test/calculations/sic_bulk/relax_pbe",
                "analysis_files": "analysis/plot_data/energy.dat; analysis/figures/relax.pdf",
                "archive_path": "/opt/example/projects/sic_test/archive/sic_bulk/relax_pbe/stamp",
                "review_status": "ACCEPTED",
                "design_summary": "sic_computation / 2 / M1",
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
    assert "sic_computation / 2 / M1" in text
    assert "Relaxed structure converged." in text


def test_design_files_are_classified_and_manifested(tmp_path: Path) -> None:
    source = tmp_path / "source"
    design_dir = source / "design/sic_computation/r0001"
    design_dir.mkdir(parents=True)
    (design_dir / "calculation_design.json").write_text("{}\n", encoding="utf-8")
    (design_dir / "computation_plan.md").write_text("# Plan\n", encoding="utf-8")
    (source / "task_spec.json").write_text(
        '{"design_provenance":{"design_id":"sic_computation","design_revision":1,"matrix_id":"M1"}}',
        encoding="utf-8",
    )
    selected = vwm_archive.collect(source, include_large=False)
    categories = {item["relpath"]: item["category"] for item in selected}
    assert categories["design/sic_computation/r0001/calculation_design.json"] == "scientific_design"
    copied = vwm_archive.copy_selected(selected, source, tmp_path / "archive")
    manifest = vwm_archive.write_archive_files(
        source=source,
        dest=tmp_path / "archive",
        project="sic_project",
        task="sic_bulk.relax",
        system_slug="sic_bulk",
        case_slug="relax",
        cluster="nmg",
        task_state="COMPLETED",
        review_status="ACCEPTED",
        notes=None,
        copied=copied,
        result={},
    )
    assert manifest["scientific_design"]["design_revision"] == 1
    assert manifest["scientific_design_files"]


def test_domain_context_is_manifested(tmp_path: Path) -> None:
    source = tmp_path / "source"
    (source / "analysis/plot_data").mkdir(parents=True)
    (source / "POSCAR").write_text("initial\n", encoding="utf-8")
    (source / "CONTCAR").write_text("relaxed\n", encoding="utf-8")
    (source / "analysis/plot_data/formation_energy.dat").write_text(
        "# vaplot_dat_version = 1\n"
        "# source = mock\n"
        "# units = energy:eV\n"
        "# columns = index formation_energy_eV\n"
        "1 1.25\n",
        encoding="utf-8",
    )
    (source / "task_spec.json").write_text(
        """
        {
          "case_slug": "v_si_neutral",
          "domain_pack": "defects-surfaces-interfaces",
          "domain_metadata": {
            "reference_cases": {"bulk_reference": "M_bulk"}
          },
          "domain_context": {
            "matrix_fixed_parameters": {"reference_case": "M_bulk"}
          },
          "design_provenance": {
            "design_id": "sic_computation",
            "design_revision": 2,
            "matrix_id": "M_defect",
            "domain_pack": "defects-surfaces-interfaces"
          }
        }
        """,
        encoding="utf-8",
    )
    selected = vwm_archive.collect(source, include_large=False)
    copied = vwm_archive.copy_selected(selected, source, tmp_path / "archive")
    manifest = vwm_archive.write_archive_files(
        source=source,
        dest=tmp_path / "archive",
        project="sic_project",
        task="sic_bulk.v_si_neutral",
        system_slug="sic_bulk",
        case_slug="v_si_neutral",
        cluster="nmg",
        task_state="COMPLETED",
        review_status="ACCEPTED",
        notes=None,
        copied=copied,
        result={},
    )
    domain = manifest["domain_context"]
    assert domain["domain_pack"] == "defects-surfaces-interfaces"
    assert domain["reference_case"] == "M_bulk"
    assert domain["variant_case"] == "v_si_neutral"
    assert domain["energy_tables"][0]["relpath"] == "analysis/plot_data/formation_energy.dat"
    assert {item["relpath"] for item in domain["structure_versions"]} == {"CONTCAR", "POSCAR"}


def test_ledger_migrates_design_columns(tmp_path: Path) -> None:
    ledger = tmp_path / "vwm.sqlite"
    with vwm_ledger.connect(ledger) as conn:
        conn.executescript("""
            CREATE TABLE tasks (id INTEGER PRIMARY KEY);
        """)
    vwm_ledger.init_db(ledger)
    with vwm_ledger.connect(ledger) as conn:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(tasks)")}
    assert {
        "design_id",
        "design_revision",
        "design_matrix_id",
        "domain_pack",
        "reference_case",
        "variant_case",
        "engine",
        "engine_status",
    }.issubset(columns)


def test_detects_and_archives_cp2k_core_files(tmp_path: Path) -> None:
    source = tmp_path / "cp2k_case"
    source.mkdir()
    (source / "water.inp").write_text("&GLOBAL\n&END GLOBAL\n", encoding="utf-8")
    (source / "water.out").write_text("ENERGY| mock\n", encoding="utf-8")
    assert vwm_archive.detect_engine(source) == "cp2k"
    selected = vwm_archive.collect(source, include_large=False)
    assert {item["relpath"] for item in selected} == {"water.inp", "water.out"}
    copied = vwm_archive.copy_selected(selected, source, tmp_path / "archive")
    manifest = vwm_archive.write_archive_files(
        source=source,
        dest=tmp_path / "archive",
        project="water_project",
        task="water.scf",
        system_slug="water",
        case_slug="scf",
        cluster="local",
        task_state="COMPLETED",
        review_status="ACCEPTED",
        notes=None,
        copied=copied,
        result={},
    )
    assert manifest["engine"] == "cp2k"
    assert manifest["schema"] == "dft-work-manager.archive.v3"
    assert manifest["calculation_fingerprint"]["exact"]


def test_detects_quantum_espresso_from_input_content(tmp_path: Path) -> None:
    source = tmp_path / "qe_case"
    source.mkdir()
    (source / "scf.in").write_text(
        "&CONTROL\n calculation='scf'\n/\n&SYSTEM\n ibrav=0\n/\nATOMIC_SPECIES\nSi 28.085 Si.upf\n",
        encoding="utf-8",
    )
    assert vwm_archive.detect_engine(source) == "quantum-espresso"
    selected = vwm_archive.collect(source, include_large=False)
    assert [item["relpath"] for item in selected] == ["scf.in"]


def test_archive_fallback_result_is_contract_valid_and_non_interpretive(tmp_path: Path) -> None:
    source = tmp_path / "run"
    source.mkdir()
    (source / "OUTCAR").write_text("free energy TOTEN = -12.3\n", encoding="utf-8")
    result = vwm_archive.load_or_create_result(source, "vasp")
    assert result["contract"] == "dft.result.v1"
    assert result["confidence"] == "provisional"
    assert "energy" not in result
    assert result["parser"]["name"] == "dft-work-manager.minimal-record"
