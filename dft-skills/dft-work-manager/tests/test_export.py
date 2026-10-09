from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import vwm_export  # noqa: E402
import vwm_ledger  # noqa: E402


def test_export_profiles_are_explicit_interchange_bundles(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.sqlite"
    vwm_ledger.init_db(ledger)
    with vwm_ledger.connect(ledger) as conn:
        vwm_ledger.register_task(conn, project="sic", task="bulk.scf", engine="vasp")
    bundle = vwm_export.collect_bundle(ledger, "sic")
    aiida = vwm_export.aiida_profile(bundle)
    nomad = vwm_export.nomad_profile(bundle)
    atomate = vwm_export.atomate2_profile(bundle)
    assert aiida["profile"] == "aiida-provenance-interchange-v1"
    assert nomad["entries"][0]["entry_name"] == "bulk.scf"
    assert atomate["task_documents"][0]["engine"] == "vasp"
    output = tmp_path / "research.md"
    vwm_export.export("research-teach", bundle, output)
    assert "DFT Evidence Index" in output.read_text(encoding="utf-8")
