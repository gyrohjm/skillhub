#!/usr/bin/env python3
"""Create the only text payload a slide authoring module may consume."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


ALLOWED_NONVISIBLE_FIELDS = {"speaker_script"}
RESERVED_KEY_RE = re.compile(
    r"(?:internal|intent|\bqa\b|evidence[ _-]*map|boundary|route|priority)",
    re.IGNORECASE,
)
RESERVED_TEXT_RE = re.compile(
    r"(?:internal[_ -]|slide[_ -]?intent|evidence[ _-]*map|\bQA\b|"
    r"\bboundary\b|\broute\b|\bpriority\b|任务边界|证据图谱|验证重点|内容路线)",
    re.IGNORECASE,
)


class PayloadError(ValueError):
    pass


def _walk_strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from _walk_strings(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from _walk_strings(item)


def _validate_visible_value(key: str, value: Any, slide_number: int) -> None:
    for text in _walk_strings(value):
        match = RESERVED_TEXT_RE.search(text)
        if match:
            raise PayloadError(
                f"slide {slide_number} field {key!r} contains reserved planning text: {match.group(0)!r}"
            )


def sanitize_payload(source: dict[str, Any], *, include_speaker_notes: bool = False) -> dict[str, Any]:
    slides = source.get("slides")
    if not isinstance(slides, list) or not slides:
        raise PayloadError("source must contain a non-empty 'slides' list")

    clean_slides: list[dict[str, Any]] = []
    for index, raw_slide in enumerate(slides, start=1):
        if not isinstance(raw_slide, dict):
            raise PayloadError(f"slide {index} must be an object")

        clean: dict[str, Any] = {}
        for key, value in raw_slide.items():
            if key.startswith("visible_") or key in ALLOWED_NONVISIBLE_FIELDS or (include_speaker_notes and key == "speaker_notes"):
                if RESERVED_KEY_RE.search(key) and not key.startswith("visible_"):
                    raise PayloadError(f"slide {index} uses reserved key {key!r}")
                _validate_visible_value(key, value, index)
                clean[key] = value

        title = clean.get("visible_title")
        if not isinstance(title, str) or not title.strip():
            raise PayloadError(f"slide {index} requires a non-empty visible_title")
        clean_slides.append(clean)

    return {"slides": clean_slides}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Keep visible_* fields and optional separate speaker_script; omit slide notes by default."
    )
    parser.add_argument("source", type=Path, help="source deck-spec JSON")
    parser.add_argument("--output", type=Path, required=True, help="sanitized JSON path")
    parser.add_argument("--include-speaker-notes", action="store_true", help="Retain slide notes only when explicitly requested by the user")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        source = json.loads(args.source.read_text(encoding="utf-8"))
        if not isinstance(source, dict):
            raise PayloadError("top-level JSON value must be an object")
        clean = sanitize_payload(source, include_speaker_notes=args.include_speaker_notes)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(clean, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    except (OSError, json.JSONDecodeError, PayloadError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"Visible payload written: {args.output.resolve()}")
    print(f"Slides: {len(clean['slides'])}; planning fields retained: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
