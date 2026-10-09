#!/usr/bin/env python3
"""Materialize approved convergence candidates without approving production values."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

DESIGN_SCRIPTS = Path(__file__).resolve().parents[2] / "dft-design" / "scripts"
if str(DESIGN_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(DESIGN_SCRIPTS))
from convergence_campaign import load, now_iso, record_result, write  # noqa: E402


def candidate(campaign: dict[str, Any], parameter: str) -> dict[str, Any]:
    matches = [item for item in campaign.get("candidates", []) if str(item.get("parameter_value")) == parameter]
    if len(matches) != 1:
        raise ValueError(f"unknown or ambiguous convergence candidate: {parameter}")
    return matches[0]


def next_candidates(campaign: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in campaign.get("candidates", []) if item.get("status") == "planned"]


def bind_task(campaign: dict[str, Any], parameter: str, task_dir: Path, fingerprint: str | None) -> None:
    item = candidate(campaign, parameter)
    if item.get("status") == "completed":
        raise ValueError("cannot rebind a completed convergence candidate")
    item.update({
        "status": "prepared",
        "task_dir": str(task_dir.expanduser().resolve()),
        "task_fingerprint": fingerprint,
        "prepared_at": now_iso(),
    })
    campaign["updated_at"] = now_iso()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="dft_convergence.py")
    parser.add_argument("--campaign", type=Path, required=True)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("next")
    bind = sub.add_parser("bind")
    bind.add_argument("--parameter", required=True)
    bind.add_argument("--task-dir", type=Path, required=True)
    bind.add_argument("--fingerprint")
    complete = sub.add_parser("complete")
    complete.add_argument("--parameter", required=True)
    complete.add_argument("--observable", type=float, required=True)
    complete.add_argument("--fingerprint")
    args = parser.parse_args(argv)
    campaign = load(args.campaign)
    if args.command == "next":
        print(json.dumps(next_candidates(campaign), indent=2, ensure_ascii=False))
        return 0
    if args.command == "bind":
        bind_task(campaign, args.parameter, args.task_dir, args.fingerprint)
    else:
        record_result(campaign, args.parameter, args.observable, args.fingerprint)
    write(args.campaign, campaign)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
