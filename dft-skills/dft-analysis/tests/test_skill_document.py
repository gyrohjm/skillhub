from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_skill_documents_success_failure_plot_and_design_handoffs() -> None:
    skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    failure = (ROOT / "references/failure-diagnosis.md").read_text(encoding="utf-8")
    plot = (ROOT / "references/plot-style.md").read_text(encoding="utf-8")

    assert skill.startswith("---\nname: dft-analysis\ndescription: Use when")
    assert "assess_completion" in skill
    assert "diagnose_failure" in skill
    assert "dft-design" in skill and "dft-workflow" in skill
    assert "submission_authorized" in failure
    assert "failure_class" in failure
    assert "28pt" in plot
    assert "--xlim" in plot and "--ylim" in plot


def test_analysis_documents_keep_completion_evidence_separate_from_reruns() -> None:
    skill = (ROOT / "SKILL.md").read_text(encoding="utf-8").lower()
    failure = (ROOT / "references/failure-diagnosis.md").read_text(encoding="utf-8").lower()
    report = (ROOT / "references/report-format.md").read_text(encoding="utf-8").lower()

    assert "scheduler_complete" in skill
    assert "artifact_complete" in skill
    assert "scientifically_accepted" in skill
    assert "technical failure retries in place" in failure
    assert "scientifically unexpected completion creates a `rerun_nnn` branch" in failure
    assert "workflow.json is the sole live leaf ledger" in report
