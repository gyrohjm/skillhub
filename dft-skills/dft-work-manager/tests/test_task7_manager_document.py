from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_manager_documents_preserve_the_live_leaf_and_lineage_contract() -> None:
    skill = (ROOT / "SKILL.md").read_text(encoding="utf-8").lower()
    contract = (ROOT / "references/skill-contract.md").read_text(encoding="utf-8").lower()
    template = (ROOT / "references/task-readme-template.md").read_text(encoding="utf-8").lower()

    assert "workflow.json is the sole live leaf ledger" in skill
    assert "technical failure retries in place" in skill
    assert "scientifically unexpected completion creates a `rerun_nnn` branch" in contract
    assert "attempts/attempt-nnn" in skill
    assert "derived_from" in template
    assert "scheduler_complete" in template
    assert "artifact_complete" in template
    assert "scientifically_accepted" in template
