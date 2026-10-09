#!/usr/bin/env python3
"""Maintain convergence results inside calculation_design.json."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def write(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def study_by_id(design: dict[str, Any], study_id: str) -> dict[str, Any]:
    studies = [
        item for item in design.get("convergence_studies", [])
        if isinstance(item, dict) and item.get("id") == study_id
    ]
    if len(studies) != 1:
        raise ValueError(f"expected one convergence study {study_id!r}; found {len(studies)}")
    return studies[0]


def build_campaign(design: dict[str, Any], study_id: str) -> dict[str, Any]:
    study = study_by_id(design, study_id)
    if "campaign" in study:
        raise ValueError(f"convergence study {study_id!r} already has a campaign")
    candidates = study.get("candidate_values")
    if not isinstance(candidates, list) or len(candidates) < 2:
        raise ValueError("convergence study requires at least two candidate_values")
    timestamp = now_iso()
    campaign = {
        "schema": "dft.convergence-campaign.v2",
        "campaign_id": f"{design['design_id']}.{study_id}.r{design['revision']:04d}",
        "candidates": [
            {
                "index": index,
                "parameter_value": value,
                "status": "planned",
                "observable_value": None,
                "evidence_ref": None,
            }
            for index, value in enumerate(candidates)
        ],
        "evaluation": None,
        "approval": {
            "status": "not_requested",
            "selected_value": None,
            "reviewer": None,
            "reviewed_at": None,
        },
        "created_at": timestamp,
        "updated_at": timestamp,
    }
    study["campaign"] = campaign
    return campaign


def record_result(
    campaign: dict[str, Any],
    parameter_value: Any,
    observable_value: float,
    evidence_ref: str | None = None,
) -> None:
    matches = [
        item for item in campaign["candidates"]
        if str(item["parameter_value"]) == str(parameter_value)
    ]
    if len(matches) != 1:
        raise ValueError(f"unknown or ambiguous candidate value: {parameter_value!r}")
    item = matches[0]
    item.update({
        "status": "completed",
        "observable_value": float(observable_value),
        "evidence_ref": evidence_ref,
        "recorded_at": now_iso(),
    })
    campaign["evaluation"] = None
    campaign["approval"] = {
        "status": "not_requested",
        "selected_value": None,
        "reviewer": None,
        "reviewed_at": None,
    }
    campaign["updated_at"] = now_iso()


def evaluate(
    campaign: dict[str, Any],
    threshold: float,
    required_consecutive: int = 1,
) -> dict[str, Any]:
    if threshold < 0 or required_consecutive < 1:
        raise ValueError("threshold must be non-negative and required_consecutive must be positive")
    completed = [
        item for item in campaign["candidates"]
        if item.get("observable_value") is not None
    ]
    completed.sort(key=lambda item: item["index"])
    comparisons: list[dict[str, Any]] = []
    selected = None
    streak = 0
    for previous, current in zip(completed, completed[1:]):
        delta = abs(float(current["observable_value"]) - float(previous["observable_value"]))
        passed = delta <= threshold
        streak = streak + 1 if passed else 0
        comparisons.append({
            "from": previous["parameter_value"],
            "to": current["parameter_value"],
            "absolute_delta": delta,
            "passed": passed,
        })
        if streak >= required_consecutive and selected is None:
            selected = current["parameter_value"]
    status = "recommendation_ready" if selected is not None else (
        "insufficient_data" if len(completed) < 2 else "not_converged"
    )
    evaluation = {
        "status": status,
        "threshold": threshold,
        "required_consecutive": required_consecutive,
        "comparisons": comparisons,
        "recommended_value": selected,
        "evaluated_at": now_iso(),
    }
    campaign["evaluation"] = evaluation
    campaign["approval"] = {
        "status": "awaiting_human_approval" if selected is not None else "not_requested",
        "selected_value": None,
        "reviewer": None,
        "reviewed_at": None,
    }
    campaign["updated_at"] = now_iso()
    return evaluation


def approve(study: dict[str, Any], reviewer: str) -> None:
    if not reviewer.strip():
        raise ValueError("reviewer must not be empty")
    campaign = study.get("campaign") or {}
    evaluation = campaign.get("evaluation") or {}
    value = evaluation.get("recommended_value")
    if evaluation.get("status") != "recommendation_ready" or value is None:
        raise ValueError("campaign has no convergence recommendation to approve")
    campaign["approval"] = {
        "status": "approved",
        "selected_value": value,
        "reviewer": reviewer,
        "reviewed_at": now_iso(),
    }
    campaign["updated_at"] = now_iso()
    study["selected_value"] = value


def add_design_scope(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--design", type=Path, required=True)
    parser.add_argument("--study", required=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="convergence_campaign.py")
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build")
    add_design_scope(build)
    record = sub.add_parser("record")
    add_design_scope(record)
    record.add_argument("--parameter", required=True)
    record.add_argument("--observable", type=float, required=True)
    record.add_argument("--evidence-ref")
    check = sub.add_parser("evaluate")
    add_design_scope(check)
    check.add_argument("--threshold", type=float, required=True)
    check.add_argument("--required-consecutive", type=int, default=1)
    accept = sub.add_parser("approve")
    add_design_scope(accept)
    accept.add_argument("--reviewer", required=True)
    args = parser.parse_args(argv)

    design = load(args.design)
    study = study_by_id(design, args.study)
    if args.command == "build":
        build_campaign(design, args.study)
    else:
        campaign = study.get("campaign")
        if not isinstance(campaign, dict):
            raise ValueError(f"convergence study {args.study!r} has no campaign; run build first")
        if args.command == "record":
            record_result(campaign, args.parameter, args.observable, args.evidence_ref)
        elif args.command == "evaluate":
            print(json.dumps(evaluate(campaign, args.threshold, args.required_consecutive), indent=2))
        elif args.command == "approve":
            approve(study, args.reviewer)
    write(args.design, design)
    print(f"[ok] updated convergence study {args.study}: {args.design}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
