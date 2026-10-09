#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN_ROOT / "skills/research-teach/scripts"))

from rtlib import atomic_write, find_project_root, load_config, now_iso  # noqa: E402


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0
    project = find_project_root(payload.get("cwd") or ".")
    if project is None:
        return 0
    try:
        _, config = load_config(project)
    except Exception:
        return 0
    checkpoint = {
        "version": 1,
        "checkpointed_at": now_iso(),
        "trigger": payload.get("trigger"),
        "session_id": payload.get("session_id"),
        "turn_id": payload.get("turn_id"),
        "project_id": config.get("project_id"),
        "research_plan": str(project / ".research/state/research-plan.md"),
    }
    atomic_write(
        project / ".research/state/last-compaction.json",
        json.dumps(checkpoint, ensure_ascii=False, indent=2) + "\n",
    )
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreCompact",
                    "additionalContext": "Research Teach checkpoint saved. Preserve the current "
                    "confirmation-gate state, unresolved evidence issues, and pending profile proposals.",
                }
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
