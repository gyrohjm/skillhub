from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import dft_ideation as di  # noqa: E402


def valid_portfolio() -> dict:
    return {
        "schema_version": 1,
        "contract": "dft.research-idea.v1",
        "portfolio_id": "sic_interface_ideas",
        "revision": 1,
        "status": "ready_for_review",
        "research_question": "What controls the interface dipole in graphene/SiC?",
        "scope": {
            "materials": ["graphene/SiC interface"],
            "phenomena": ["interface dipole"],
            "constraints": ["VASP or QE"],
            "excluded_topics": ["device transport"],
        },
        "evidence": [{
            "id": "E1",
            "source": "doi:10.example/test",
            "source_type": "primary_paper",
            "claim": "Registry changes charge transfer.",
            "locator": "Figure 3 and page 6",
            "verification_status": "verified",
            "role": "support",
        }],
        "gaps": [{
            "id": "G1",
            "type": "missing_control",
            "statement": "Registry and strain have not been separated.",
            "evidence_ids": ["E1"],
            "confidence": "medium",
            "why_dft_can_help": "A matched matrix can vary registry and strain independently.",
        }],
        "ideas": [{
            "id": "I1",
            "title": "Separate registry and strain contributions",
            "hypothesis": "Registry dominates the interface dipole at fixed strain.",
            "falsification": "The dipole follows strain and is insensitive to registry.",
            "rationale": "The literature comparison confounds both variables.",
            "evidence_ids": ["E1"],
            "gap_ids": ["G1"],
            "target_observables": [{
                "quantity": "work-function difference",
                "unit": "eV",
                "decision_rule": "registry effect exceeds strain effect by 0.1 eV",
                "dft_method": "slab SCF plus planar potential",
            }],
            "controls": ["isolated strained graphene", "bare strained SiC slab"],
            "reference_states": ["same slab thickness, area and dipole correction"],
            "convergence_axes": ["vacuum", "slab thickness", "k-point density"],
            "uncertainty_sources": ["commensurate strain", "functional dependence"],
            "novelty_checks": [{
                "query": "graphene SiC registry strain interface dipole DFT",
                "source": "Crossref and Google Scholar",
                "searched_at": "2026-07-16",
                "overlap": "partial",
                "outcome": "Closest paper varies registry but not a matched strain control.",
            }],
            "calculation_outline": ["relax matched structures", "SCF", "planar potential comparison"],
            "resource_estimate": {"task_count": 12, "relative_cost": "medium", "storage_risk": "low"},
            "risks": ["commensurate supercell may be too large"],
            "scores": {
                "literature_grounding": 4,
                "novelty": 4,
                "significance": 4,
                "falsifiability": 5,
                "dft_tractability": 4,
                "numerical_robustness": 4,
                "resource_fit": 4,
            },
            "verdict": "keep",
        }],
        "review_history": [{"type": "four_lens_review", "reviewed_at": "2026-07-16"}],
        "selected_idea_id": None,
        "pending_decisions": [],
    }


def test_validates_and_ranks_portfolio() -> None:
    portfolio = valid_portfolio()
    assert di.validate_portfolio(portfolio) == []
    ranked = di.ranked_ideas(portfolio)
    assert ranked[0]["id"] == "I1"
    assert ranked[0]["score"] == 4.15


def test_rejects_untraceable_and_unverified_selection() -> None:
    portfolio = valid_portfolio()
    portfolio["ideas"][0]["evidence_ids"] = ["missing"]
    assert any("unknown evidence" in error for error in di.validate_portfolio(portfolio))
    portfolio = valid_portfolio()
    portfolio["status"] = "selected_for_design"
    portfolio["selected_idea_id"] = "I1"
    portfolio["evidence"][0]["verification_status"] = "pending"
    assert any("unverified evidence" in error for error in di.validate_portfolio(portfolio))


def test_design_seed_is_proposal_only() -> None:
    seed = di.design_seed(valid_portfolio(), "I1")
    assert seed["status"] == "proposal_not_approved"
    assert seed["hypotheses"][0]["id"] == "H1"
    assert "engine_stage_envelopes" not in seed
    assert any("dft-design" in item for item in seed["pending_decisions"])


def test_bootstrap_preserves_existing_files(tmp_path: Path) -> None:
    (tmp_path / "calculations").mkdir(parents=True)
    (tmp_path / "AGENTS.md").write_text("# Project rules\n", encoding="utf-8")
    created = di.bootstrap(tmp_path, "sic_project", "sic_project_dft_ideas")
    assert len(created) == 6
    portfolio = tmp_path / "plans/research/ideation/idea_portfolio.json"
    assert (tmp_path / "plans/README.md").is_file()
    assert (tmp_path / "plans/research/README.md").is_file()
    assert (tmp_path / "plans/research/ideation/README.md").is_file()
    portfolio.write_text("user-owned\n", encoding="utf-8")
    assert di.bootstrap(tmp_path, "sic_project", "sic_project_dft_ideas") == []
    assert portfolio.read_text(encoding="utf-8") == "user-owned\n"


def test_selection_is_immutable_and_records_handoff(tmp_path: Path) -> None:
    (tmp_path / "calculations").mkdir(parents=True)
    (tmp_path / "AGENTS.md").write_text("# Project rules\n", encoding="utf-8")
    portfolio_path = tmp_path / "idea_portfolio.json"
    portfolio_path.write_text(json.dumps(valid_portfolio()), encoding="utf-8")
    record = di.select_for_design(tmp_path, portfolio_path, "I1", "gyro")
    assert (record / "idea_portfolio.json").is_file()
    assert (record / "dft_design_seed.json").is_file()
    selection = json.loads((record / "selection.json").read_text(encoding="utf-8"))
    assert selection["authorization"] == "ideation_selection_only_not_dft_design_approval"
    with pytest.raises(FileExistsError, match="immutable"):
        di.select_for_design(tmp_path, portfolio_path, "I1", "gyro")
