from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import convergence_campaign as campaign  # noqa: E402


def test_campaign_stays_inside_design_and_requires_human_approval(tmp_path: Path) -> None:
    design_path = tmp_path / "design.json"
    design_path.write_text(json.dumps({
        "design_id": "sic",
        "revision": 2,
        "convergence_studies": [{
            "id": "CV1", "parameter": "ENCUT", "observable": "energy_per_atom",
            "candidate_values": [400, 500, 600], "fixed_conditions": ["same k mesh"],
            "acceptance_rule": "below 0.002 eV/atom",
        }],
    }), encoding="utf-8")
    assert campaign.main(["build", "--design", str(design_path), "--study", "CV1"]) == 0
    assert campaign.main([
        "record", "--design", str(design_path), "--study", "CV1",
        "--parameter", "400", "--observable", "-5.0", "--evidence-ref", "calculations/sic/a",
    ]) == 0
    assert campaign.main([
        "record", "--design", str(design_path), "--study", "CV1",
        "--parameter", "500", "--observable", "-5.010", "--evidence-ref", "calculations/sic/b",
    ]) == 0
    assert campaign.main([
        "record", "--design", str(design_path), "--study", "CV1",
        "--parameter", "600", "--observable", "-5.011", "--evidence-ref", "calculations/sic/c",
    ]) == 0
    assert campaign.main([
        "evaluate", "--design", str(design_path), "--study", "CV1",
        "--threshold", "0.002",
    ]) == 0
    design = json.loads(design_path.read_text(encoding="utf-8"))
    study = design["convergence_studies"][0]
    value = study["campaign"]
    result = value["evaluation"]
    assert result["recommended_value"] == 600
    assert value["approval"]["status"] == "awaiting_human_approval"
    assert value["approval"]["selected_value"] is None
    assert study.get("selected_value") is None

    assert campaign.main([
        "approve", "--design", str(design_path), "--study", "CV1",
        "--reviewer", "researcher",
    ]) == 0
    approved = json.loads(design_path.read_text(encoding="utf-8"))["convergence_studies"][0]
    assert approved["campaign"]["approval"]["selected_value"] == 600
    assert approved["selected_value"] == 600
    assert {item.name for item in tmp_path.iterdir()} == {"design.json"}
