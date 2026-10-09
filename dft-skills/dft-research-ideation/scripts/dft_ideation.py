#!/usr/bin/env python3
"""Validate, rank, select, and hand off literature-grounded DFT research ideas."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SKILL_ROOT = Path(__file__).resolve().parents[1]
CONTRACTS_ROOT = SKILL_ROOT.parent / "dft-contracts"
if str(CONTRACTS_ROOT) not in sys.path:
    sys.path.insert(0, str(CONTRACTS_ROOT))
from dft_contracts import discover_workspace, plans_root, validate_document  # noqa: E402

PLAN_DIR = Path("plans/research/ideation")
RECORD_DIR = Path("docs/records/dft_ideation")
SLUG_RE = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")
SCORE_KEYS = (
    "literature_grounding", "novelty", "significance", "falsifiability",
    "dft_tractability", "numerical_robustness", "resource_fit",
)
SCORE_WEIGHTS = {
    "literature_grounding": 0.15,
    "novelty": 0.15,
    "significance": 0.15,
    "falsifiability": 0.15,
    "dft_tractability": 0.15,
    "numerical_robustness": 0.15,
    "resource_fit": 0.10,
}
SELECTION_MINIMUMS = {
    "literature_grounding": 3,
    "novelty": 3,
    "significance": 3,
    "falsifiability": 4,
    "dft_tractability": 4,
    "numerical_robustness": 3,
    "resource_fit": 3,
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temp.replace(path)


def workspace_root(project: Path) -> Path:
    try:
        return discover_workspace(project.expanduser().resolve())
    except ValueError as exc:
        raise ValueError(str(exc)) from exc


def ideation_dir(project: Path) -> Path:
    root = workspace_root(project)
    return (plans_root(root) / "research" / "ideation").resolve()


def validate_portfolio(portfolio: dict[str, Any]) -> list[str]:
    errors = validate_document("research-idea-v1", portfolio)
    if errors:
        return errors
    evidence_ids = [item["id"] for item in portfolio["evidence"]]
    gap_ids = [item["id"] for item in portfolio["gaps"]]
    idea_ids = [item["id"] for item in portfolio["ideas"]]
    for label, values in (("evidence", evidence_ids), ("gaps", gap_ids), ("ideas", idea_ids)):
        duplicates = sorted({value for value in values if values.count(value) > 1})
        if duplicates:
            errors.append(f"{label} ids must be unique; duplicates: {duplicates}")
    evidence_set, gap_set = set(evidence_ids), set(gap_ids)
    for item in portfolio["evidence"]:
        if item["source_type"] == "local_result" and not item.get("source_hash"):
            errors.append(f"evidence {item['id']}: local_result requires source_hash")
    for gap in portfolio["gaps"]:
        missing = sorted(set(gap["evidence_ids"]) - evidence_set)
        if missing:
            errors.append(f"gap {gap['id']}: unknown evidence ids {missing}")
    for idea in portfolio["ideas"]:
        missing_evidence = sorted(set(idea["evidence_ids"]) - evidence_set)
        missing_gaps = sorted(set(idea["gap_ids"]) - gap_set)
        if missing_evidence:
            errors.append(f"idea {idea['id']}: unknown evidence ids {missing_evidence}")
        if missing_gaps:
            errors.append(f"idea {idea['id']}: unknown gap ids {missing_gaps}")
        missing_scores = sorted(set(SCORE_KEYS) - set(idea["scores"]))
        if missing_scores:
            errors.append(f"idea {idea['id']}: missing scores {missing_scores}")
        if idea["hypothesis"].strip() == idea["falsification"].strip():
            errors.append(f"idea {idea['id']}: falsification must differ from the hypothesis")
    if portfolio["status"] in {"ready_for_review", "selected_for_design"} and not portfolio["ideas"]:
        errors.append("reviewable portfolio must contain at least one idea")
    if portfolio["status"] == "selected_for_design":
        selected = portfolio.get("selected_idea_id")
        matches = [item for item in portfolio["ideas"] if item["id"] == selected]
        if len(matches) != 1:
            errors.append("selected_for_design requires one valid selected_idea_id")
        else:
            idea = matches[0]
            if idea["verdict"] != "keep":
                errors.append("selected idea verdict must be keep")
            pending = [
                item["id"] for item in portfolio["evidence"]
                if item["id"] in idea["evidence_ids"] and item["verification_status"] != "verified"
            ]
            if pending:
                errors.append(f"selected idea has unverified evidence: {pending}")
            unknown = [check for check in idea["novelty_checks"] if check["overlap"] == "unknown"]
            high = [check for check in idea["novelty_checks"] if check["overlap"] == "high"]
            if unknown:
                errors.append("selected idea has incomplete novelty checks")
            if high:
                errors.append("selected idea has high literature overlap and cannot be selected as novel")
            for key, minimum in SELECTION_MINIMUMS.items():
                if float(idea["scores"].get(key, 0)) < minimum:
                    errors.append(f"selected idea score {key} must be >= {minimum}")
        if portfolio["pending_decisions"]:
            errors.append("selected_for_design requires no pending_decisions")
    elif portfolio.get("selected_idea_id") is not None:
        errors.append("selected_idea_id must be null unless status is selected_for_design")
    return errors


def weighted_score(idea: dict[str, Any]) -> float:
    return round(sum(float(idea["scores"][key]) * SCORE_WEIGHTS[key] for key in SCORE_KEYS), 3)


def ranked_ideas(portfolio: dict[str, Any]) -> list[dict[str, Any]]:
    return sorted(
        ({"id": idea["id"], "title": idea["title"], "verdict": idea["verdict"], "score": weighted_score(idea)} for idea in portfolio["ideas"]),
        key=lambda item: (-item["score"], item["id"]),
    )


def selected_idea(portfolio: dict[str, Any], idea_id: str) -> dict[str, Any]:
    matches = [idea for idea in portfolio["ideas"] if idea["id"] == idea_id]
    if len(matches) != 1:
        raise ValueError(f"expected one idea {idea_id!r}; found {len(matches)}")
    return matches[0]


def design_seed(portfolio: dict[str, Any], idea_id: str) -> dict[str, Any]:
    idea = selected_idea(portfolio, idea_id)
    evidence = [item for item in portfolio["evidence"] if item["id"] in idea["evidence_ids"]]
    return {
        "schema_version": 1,
        "contract": "dft.idea-to-design-seed.v1",
        "status": "proposal_not_approved",
        "source": {
            "portfolio_id": portfolio["portfolio_id"],
            "portfolio_revision": portfolio["revision"],
            "idea_id": idea_id,
        },
        "research_questions": [{"id": "Q1", "question": portfolio["research_question"]}],
        "hypotheses": [{"id": "H1", "statement": idea["hypothesis"], "falsification": idea["falsification"]}],
        "systems": [
            {"system_slug": f"system_{index}", "model": material, "structure_provenance": "unresolved", "assumptions": []}
            for index, material in enumerate(portfolio["scope"]["materials"], start=1)
        ],
        "observables": [
            {"id": f"O{index}", "hypothesis_ids": ["H1"], **observable, "uncertainty_target": "unresolved"}
            for index, observable in enumerate(idea["target_observables"], start=1)
        ],
        "controls": [
            {"id": f"C{index}", "type": "ideation_control", "purpose": value, "fixed_or_varied": "unresolved"}
            for index, value in enumerate(idea["controls"], start=1)
        ],
        "reference_states": idea["reference_states"],
        "convergence_axes": idea["convergence_axes"],
        "calculation_outline": idea["calculation_outline"],
        "uncertainty_sources": idea["uncertainty_sources"],
        "resource_estimate": idea["resource_estimate"],
        "evidence": evidence,
        "pending_decisions": [
            "resolve structures and structure provenance",
            "choose and justify engine/method envelope",
            "turn convergence axes into candidate values and observable thresholds",
            "define resource profile and stopping rules",
            "run dft-design validation and obtain explicit scientific approval",
        ],
    }


def bootstrap(project: Path, project_slug: str, portfolio_id: str) -> list[Path]:
    if not SLUG_RE.fullmatch(project_slug) or not SLUG_RE.fullmatch(portfolio_id):
        raise ValueError("project_slug and portfolio_id must use lowercase_snake_case")
    target = ideation_dir(project)
    target.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []
    plans_dir = target.parents[1]
    readmes = [
        (
            plans_dir / "README.md",
            "# DFT Plans\n\n"
            "Composition- and structure-scoped designs plus pre-system ideation live below this directory.\n",
        ),
        (
            target.parent / "README.md",
            "# DFT Research Staging\n\n"
            "This directory holds proposal-stage ideation before a composition and structure are resolved.\n",
        ),
        (
            target / "README.md",
            "# DFT Research Ideation\n\n"
            "This directory contains literature-grounded proposal files only.\n",
        ),
    ]
    for destination, content in readmes:
        if destination.exists():
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")
        created.append(destination)
    mappings = {
        "research_brief.template.json": "research_brief.json",
        "idea_portfolio.template.json": "idea_portfolio.json",
        "literature_protocol.template.md": "literature_protocol.md",
    }
    for source_name, target_name in mappings.items():
        source, destination = SKILL_ROOT / "assets" / source_name, target / target_name
        if destination.exists():
            continue
        if source.suffix == ".json":
            value = load_json(source)
            if target_name == "research_brief.json":
                value["project_slug"] = project_slug
            else:
                value["portfolio_id"] = portfolio_id
            atomic_json(destination, value)
        else:
            shutil.copy2(source, destination)
        created.append(destination)
    return created


def select_for_design(project: Path, portfolio_path: Path, idea_id: str, reviewer: str) -> Path:
    portfolio = load_json(portfolio_path)
    candidate = copy.deepcopy(portfolio)
    candidate["status"] = "selected_for_design"
    candidate["selected_idea_id"] = idea_id
    candidate["pending_decisions"] = []
    candidate.setdefault("review_history", []).append({
        "type": "human_selection",
        "reviewer": reviewer,
        "idea_id": idea_id,
        "selected_at": utc_now(),
    })
    errors = validate_portfolio(candidate)
    if errors:
        raise ValueError("selection blocked: " + "; ".join(errors))
    record = workspace_root(project) / RECORD_DIR / candidate["portfolio_id"] / f"r{candidate['revision']:04d}"
    if record.exists():
        raise FileExistsError(f"immutable selection record already exists: {record}")
    record.mkdir(parents=True)
    atomic_json(portfolio_path, candidate)
    snapshot = record / "idea_portfolio.json"
    atomic_json(snapshot, candidate)
    seed = design_seed(candidate, idea_id)
    atomic_json(record / "dft_design_seed.json", seed)
    atomic_json(record / "selection.json", {
        "schema_version": 1,
        "portfolio_id": candidate["portfolio_id"],
        "revision": candidate["revision"],
        "idea_id": idea_id,
        "reviewer": reviewer,
        "selected_at": utc_now(),
        "portfolio_sha256": sha256_file(snapshot),
        "authorization": "ideation_selection_only_not_dft_design_approval",
    })
    return record


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dft_ideation.py")
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("bootstrap")
    init.add_argument("--project", type=Path, required=True)
    init.add_argument("--project-slug", required=True)
    init.add_argument("--portfolio-id")
    validate = sub.add_parser("validate")
    validate.add_argument("--portfolio", type=Path, required=True)
    rank = sub.add_parser("rank")
    rank.add_argument("--portfolio", type=Path, required=True)
    handoff = sub.add_parser("handoff")
    handoff.add_argument("--portfolio", type=Path, required=True)
    handoff.add_argument("--idea", required=True)
    handoff.add_argument("--output", type=Path, required=True)
    select = sub.add_parser("select")
    select.add_argument("--project", type=Path, required=True)
    select.add_argument("--portfolio", type=Path, required=True)
    select.add_argument("--idea", required=True)
    select.add_argument("--reviewer", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "bootstrap":
        portfolio_id = args.portfolio_id or f"{args.project_slug}_dft_ideas"
        for path in bootstrap(args.project, args.project_slug, portfolio_id):
            print(f"[created] {path}")
        return 0
    portfolio = load_json(args.portfolio)
    if args.command == "validate":
        errors = validate_portfolio(portfolio)
        if errors:
            for error in errors:
                print(f"[error] {error}", file=sys.stderr)
            return 1
        print("[ok] valid dft.research-idea.v1")
        return 0
    if args.command == "rank":
        errors = validate_portfolio(portfolio)
        if errors:
            raise ValueError("invalid portfolio: " + "; ".join(errors))
        print(json.dumps(ranked_ideas(portfolio), indent=2, ensure_ascii=False))
        return 0
    if args.command == "handoff":
        if args.output.exists():
            raise FileExistsError(f"refusing to overwrite: {args.output}")
        atomic_json(args.output, design_seed(portfolio, args.idea))
        print(f"[ok] proposal-only handoff: {args.output}")
        return 0
    record = select_for_design(args.project, args.portfolio, args.idea, args.reviewer)
    print(f"[ok] immutable ideation selection: {record}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
