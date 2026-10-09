#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN_ROOT / "skills/research-teach/scripts"))

from rtlib import (  # noqa: E402
    ResearchTeachError,
    atomic_write,
    find_project_root,
    is_research_intent,
    is_dft_intent,
    load_approved_context,
    load_config,
)
from converter import mineru_config_status  # noqa: E402


def configure_command() -> str:
    script = PLUGIN_ROOT / "skills/research-teach/scripts/research_teach.py"
    return f'python3 "{script}" configure-mineru'


def emit(event: str, context: str, system_message: str | None = None) -> None:
    payload: dict[str, object] = {
        "hookSpecificOutput": {
            "hookEventName": event,
            "additionalContext": context,
        }
    }
    if system_message:
        payload["systemMessage"] = system_message
    print(json.dumps(payload, ensure_ascii=False))


def first_start_reminder_needed() -> bool:
    data_root = Path(
        os.environ.get("PLUGIN_DATA")
        or os.environ.get("CLAUDE_PLUGIN_DATA")
        or "~/.local/share/research-teach/plugin-data"
    ).expanduser().resolve()
    sentinel = data_root / "mineru-config-reminder-v1.shown"
    if sentinel.exists():
        return False
    atomic_write(sentinel, "shown\n")
    return True


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0
    event = payload.get("hook_event_name", "")
    cwd = payload.get("cwd") or "."
    project = find_project_root(cwd)
    mineru_missing = not mineru_config_status()["token_configured"]

    if event == "SessionStart":
        reminder = (
            "MinerU API is not configured. Run the private setup command before converting PDFs: "
            f"{configure_command()}"
        )
        if project is None:
            if mineru_missing and first_start_reminder_needed():
                emit(event, reminder, "Research Teach needs a MinerU API key for PDF conversion.")
            return 0
        context = (
            "A Research Teach project was detected at "
            f"{project}. Do not read .research/global during ordinary programming tasks. "
            "When the user explicitly requests research, literature processing, knowledge mapping, "
            "or teaching, use $research-teach and then load only the approved AgentContext files."
        )
        if mineru_missing:
            first_start_reminder_needed()
            context += "\n\n" + reminder
        emit(
            event,
            context,
            "Research Teach PDF conversion is waiting for MinerU API configuration."
            if mineru_missing
            else None,
        )
        return 0

    if event != "UserPromptSubmit":
        return 0
    if project is None:
        return 0
    prompt = str(payload.get("prompt", ""))
    if not is_research_intent(prompt):
        return 0
    try:
        _, config = load_config(project)
        approved = load_approved_context(project)
    except ResearchTeachError:
        return 0
    skill_name = "$dote-tutor" if is_dft_intent(prompt) else "$research-teach"
    context = (
        "The user explicitly requested a research, DFT, or teaching workflow. "
        f"Use {skill_name}. "
        "Apply its three confirmation gates, project privacy policy, and source-traceability rules. "
        "The global learner context below is read-only; changes require a proposal and explicit "
        "accept-proposal action.\n\n"
        f"Project id: {config.get('project_id')}\n\n{approved}"
    )
    if mineru_missing:
        context += (
            "\n\nMinerU API is not configured. Before PDF conversion, ask the user to run: "
            f"{configure_command()}"
        )
    emit(
        event,
        context,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
