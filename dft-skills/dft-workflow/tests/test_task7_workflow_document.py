from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8").lower()


def test_workflow_documents_define_the_canonical_v2_sequence() -> None:
    skill = _read("SKILL.md")
    order = _read("references/workflow-order.md")
    review = _read("references/input-review.md")
    resource = _read("references/resource-preflight.md")
    recovery = _read("references/error-recovery.md")

    assert "design complete tree and all determinable inputs" in skill
    assert "one user scientific-parameter approval" in skill
    assert "initialize all executable leaves" in skill
    assert "current on-disk inputs are authoritative" in skill
    assert "deterministic dependency gate" in skill
    assert "agent only for an inconclusive verdict" in skill
    assert "project resource" in skill
    assert "submit without repeated user approval" in skill
    assert "technical failure retries in place" in recovery
    assert "scientifically unexpected completion creates a `rerun_nnn` branch" in order

    assert "current on-disk inputs are authoritative" in review
    assert "hash mismatch triggers reconciliation, not re-approval" in review
    assert "program first, professional agent second, user only for a major conflict" in order
    assert "one target-shell invocation" in resource
    assert "workflow.json is the sole live leaf ledger" in skill
    assert "`.dft/resource-profile.json` is the project cache" in resource


def test_workflow_documents_keep_legacy_helpers_behind_compatibility_only() -> None:
    skill = _read("SKILL.md")

    assert "compatibility only" in skill
    assert "prepare" in skill
    assert "vwf" in skill and "qewf" in skill
