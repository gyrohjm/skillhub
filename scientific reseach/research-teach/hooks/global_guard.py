#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN_ROOT / "skills/research-teach/scripts"))

from rtlib import find_project_root, load_config  # noqa: E402


MUTATING_TOOL_TERMS = ("write", "edit", "update", "create", "delete", "remove", "move", "rename")
MUTATING_SHELL = re.compile(
    r"(?:^|[;&|]\s*)(?:rm|mv|cp|touch|mkdir|rmdir|chmod|chown|truncate|tee|"
    r"sed\s+-i|perl\s+-pi|install)\b|(?:^|[^<])>>?",
    flags=re.IGNORECASE,
)


def flatten(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return "\n".join(f"{key}: {flatten(item)}" for key, item in value.items())
    if isinstance(value, list):
        return "\n".join(flatten(item) for item in value)
    return str(value)


def deny(reason: str) -> None:
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            }
        )
    )


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
    global_path = Path(str(config.get("global_context", ""))).expanduser().resolve()
    tool_name = str(payload.get("tool_name", ""))
    content = flatten(payload.get("tool_input", {}))
    normalized = content.replace("\\", "/")
    references_global = (
        ".research/global" in normalized
        or str(global_path) in content
        or str(global_path).replace("\\", "/") in normalized
    )
    if not references_global:
        return 0

    if "research_teach.py" in content and "accept-proposal" in content:
        return 0

    canonical = tool_name.casefold()
    if canonical == "apply_patch" or any(term in canonical for term in MUTATING_TOOL_TERMS):
        deny(
            "Direct writes to the global AgentContext are blocked. Create a project proposal, "
            "show its diff, obtain explicit user approval, then run accept-proposal."
        )
        return 0
    if canonical == "bash" and MUTATING_SHELL.search(content):
        deny(
            "This shell command appears to mutate the global AgentContext. Use the proposal "
            "approval workflow instead."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
