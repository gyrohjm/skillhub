#!/usr/bin/env python3
"""Materialize selected analysis templates into a project's ``code/`` tree."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
CONTRACTS_ROOT = SKILL_ROOT.parent / "dft-contracts"
if str(CONTRACTS_ROOT) not in sys.path:
    sys.path.insert(0, str(CONTRACTS_ROOT))

from dft_contracts import code_root, discover_workspace  # noqa: E402


TEMPLATES = {
    "plotting": ("dftplot_plot.py", "dftplot_style.py"),
}


def initialize_template(workspace: str | Path, family: str) -> list[Path]:
    """Copy a named template family without overwriting project files."""

    if family not in TEMPLATES:
        raise ValueError(f"unknown template family {family!r}; choose from {sorted(TEMPLATES)}")
    try:
        root = discover_workspace(Path(workspace).expanduser().resolve())
    except ValueError as exc:
        raise ValueError(str(exc)) from exc
    project_code = code_root(root)
    template_dir = project_code / "templates" / family
    created: list[Path] = []
    readmes = [
        (
            project_code / "README.md",
            "# Project Code\n\n"
            "Reusable programs and explicitly materialized skill templates live here.\n",
        ),
        (
            project_code / "templates" / "README.md",
            "# Local Skill Templates\n\n"
            "Existing local adaptations are never overwritten by a skill update.\n",
        ),
        (
            template_dir / "README.md",
            f"# {family} Templates\n\n"
            "Source: dft-analysis skill. Adapt these project-local copies as needed.\n",
        ),
    ]
    for destination, content in readmes:
        if destination.exists():
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")
        created.append(destination)
    for filename in TEMPLATES[family]:
        source = SKILL_ROOT / "scripts" / filename
        destination = template_dir / filename
        if destination.exists():
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        created.append(destination)
    return created


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="init_project_code.py")
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--family", choices=sorted(TEMPLATES), required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        for path in initialize_template(args.workspace, args.family):
            print(f"[created] {path}")
        return 0
    except (OSError, ValueError) as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
