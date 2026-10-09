from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _design_docs() -> str:
    paths = (
        ROOT / "SKILL.md",
        ROOT / "references/design-contract.md",
        ROOT / "references/engine-contract.md",
        ROOT / "assets/plan_readme.template.md",
    )
    return " ".join("\n".join(path.read_text(encoding="utf-8") for path in paths).lower().split())


def test_design_documents_define_the_v2_one_approval_initialization_contract() -> None:
    text = _design_docs()

    assert "design the complete task tree and all determinable inputs" in text
    assert "one user scientific-parameter approval" in text
    assert "initialize all executable leaves" in text
    assert "execution_plan.tasks[]" in text
    assert "current on-disk inputs are authoritative" in text
    assert "hash mismatch triggers reconciliation, not re-approval" in text
    assert "one workflow.json per executable leaf" in text
    assert "no repeated user approval" in text


def test_design_legacy_bootstrap_is_labeled_compatibility_only() -> None:
    text = (ROOT / "SKILL.md").read_text(encoding="utf-8").lower()

    assert "compatibility only" in text
    assert "bootstrap" in text
