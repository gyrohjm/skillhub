#!/usr/bin/env python3
"""Preview and safely initialize a structured scientific research project."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any


SKILL_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_DIR = SKILL_ROOT / "assets" / "templates"
VALID_MODES = {"generic", "experimental", "computational", "hybrid"}
SLUG_RE = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")

BASE_DIRECTORIES = [
    "docs",
    "docs/literature",
    "docs/literature/papers",
    "docs/literature/notes",
    "docs/presentations",
    "docs/task_logs",
    "docs/tutorials",
    "code",
    "code/src",
    "code/scripts",
    "code/notebooks",
    "code/tests",
    "code/configs",
    "raw_data",
    "raw_data/external",
    "raw_data/interim",
    "formal_data",
    "formal_data/plot_data",
    "formal_data/figures",
    "formal_data/tables",
    "formal_data/structures",
    "formal_data/supplementary",
]

MODE_DIRECTORIES = {
    "generic": [],
    "experimental": ["raw_data/experiments"],
    "computational": ["raw_data/calculations"],
    "hybrid": ["raw_data/experiments", "raw_data/calculations"],
}


@dataclass(frozen=True)
class PlannedFile:
    relative_path: str
    content: str


def normalize_ascii_snake_case(value: str) -> str:
    """Normalize ASCII words; non-ASCII project names still require a confirmed English slug."""
    ascii_only = value.encode("ascii", errors="ignore").decode("ascii").lower()
    normalized = re.sub(r"[^a-z0-9]+", "_", ascii_only).strip("_")
    normalized = re.sub(r"_+", "_", normalized)
    if normalized and normalized[0].isdigit():
        normalized = f"project_{normalized}"
    return normalized


def load_spec(path: Path) -> dict[str, Any]:
    try:
        spec = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"Spec file does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path}: {exc}") from exc

    required = [
        "project_name",
        "project_slug",
        "mode",
        "domain",
        "summary",
        "research_questions",
        "hypotheses",
        "objectives",
    ]
    missing = [key for key in required if key not in spec]
    if missing:
        raise ValueError(f"Missing required spec fields: {', '.join(missing)}")

    slug = str(spec["project_slug"])
    if not SLUG_RE.fullmatch(slug):
        suggestion = normalize_ascii_snake_case(slug)
        hint = f" Suggested ASCII normalization: {suggestion!r}." if suggestion else " Confirm an English slug first."
        raise ValueError(
            "project_slug must use English lowercase_snake_case and match "
            f"{SLUG_RE.pattern!r}; got {slug!r}.{hint}"
        )

    mode = str(spec["mode"])
    if mode not in VALID_MODES:
        raise ValueError(f"mode must be one of {sorted(VALID_MODES)}; got {mode!r}")

    if not isinstance(spec["research_questions"], list) or not spec["research_questions"]:
        raise ValueError("research_questions must be a non-empty list")
    if not isinstance(spec["hypotheses"], list) or not spec["hypotheses"]:
        raise ValueError("hypotheses must be a non-empty list")
    if not isinstance(spec["objectives"], list) or not spec["objectives"]:
        raise ValueError("objectives must be a non-empty list")

    for index, item in enumerate(spec["hypotheses"], start=1):
        if not isinstance(item, dict) or not item.get("statement") or not item.get("falsification"):
            raise ValueError(f"hypotheses[{index}] requires statement and falsification")
    for index, item in enumerate(spec["objectives"], start=1):
        if not isinstance(item, dict) or not item.get("description") or not item.get("success_criteria"):
            raise ValueError(f"objectives[{index}] requires description and success_criteria")
    return spec


def markdown_list(items: Any, empty: str = "- TBD / 待补充") -> str:
    if not items:
        return empty
    if not isinstance(items, list):
        items = [items]
    lines = []
    for item in items:
        if isinstance(item, dict):
            lines.append(f"- {json.dumps(item, ensure_ascii=False)}")
        else:
            lines.append(f"- {item}")
    return "\n".join(lines)


def format_hypotheses(items: list[dict[str, Any]]) -> str:
    lines = []
    for index, item in enumerate(items, start=1):
        identifier = item.get("id", f"H{index}")
        lines.extend(
            [
                f"### {identifier}",
                f"- Statement / 陈述: {item['statement']}",
                f"- Falsification / 否证条件: {item['falsification']}",
                "",
            ]
        )
    return "\n".join(lines).rstrip()


def format_objectives(items: list[dict[str, Any]]) -> str:
    lines = []
    for index, item in enumerate(items, start=1):
        identifier = item.get("id", f"O{index}")
        lines.extend(
            [
                f"### {identifier}",
                f"- Objective / 目标: {item['description']}",
                f"- Success criteria / 验收标准: {item['success_criteria']}",
                "",
            ]
        )
    return "\n".join(lines).rstrip()


def format_milestones(items: Any) -> str:
    if not items:
        return "| ID | Milestone / 里程碑 | Acceptance / 验收 | Target date / 日期 |\n|---|---|---|---|\n| M1 | TBD | TBD | TBD |"
    lines = [
        "| ID | Milestone / 里程碑 | Acceptance / 验收 | Target date / 日期 |",
        "|---|---|---|---|",
    ]
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            item = {"description": str(item)}
        lines.append(
            f"| {item.get('id', f'M{index}')} | {item.get('description', 'TBD')} | "
            f"{item.get('acceptance', 'TBD')} | {item.get('target_date', 'TBD')} |"
        )
    return "\n".join(lines)


def format_risks(items: Any) -> str:
    if not items:
        return "| Risk / 风险 | Likelihood / 可能性 | Impact / 影响 | Mitigation / 缓解 |\n|---|---|---|---|\n| TBD | TBD | TBD | TBD |"
    lines = [
        "| Risk / 风险 | Likelihood / 可能性 | Impact / 影响 | Mitigation / 缓解 |",
        "|---|---|---|---|",
    ]
    for item in items:
        if not isinstance(item, dict):
            item = {"risk": str(item)}
        lines.append(
            f"| {item.get('risk', 'TBD')} | {item.get('likelihood', 'TBD')} | "
            f"{item.get('impact', 'TBD')} | {item.get('mitigation', 'TBD')} |"
        )
    return "\n".join(lines)


def format_plan(value: Any) -> str:
    if not value:
        return "TBD / 待补充"
    if not isinstance(value, dict):
        return str(value)
    lines = []
    for key, item in value.items():
        title = key.replace("_", " ").title()
        lines.append(f"## {title}")
        if isinstance(item, list):
            lines.append(markdown_list(item))
        elif isinstance(item, dict):
            lines.append("```json")
            lines.append(json.dumps(item, ensure_ascii=False, indent=2))
            lines.append("```")
        else:
            lines.append(str(item) if item else "TBD / 待补充")
        lines.append("")
    return "\n".join(lines).rstrip()


def format_evidence(value: Any) -> str:
    if not isinstance(value, dict):
        return "- External search approved / 已批准外部检索: No / 否\n- Pending validation / 待验证: TBD"
    approved = "Yes / 是" if value.get("external_search_approved") else "No / 否"
    sources = markdown_list(value.get("sources"), empty="- None recorded / 暂无")
    pending = markdown_list(value.get("pending_validation"), empty="- None recorded / 暂无")
    return f"- External search approved / 已批准外部检索: {approved}\n\n### Sources / 来源\n\n{sources}\n\n### Pending validation / 待验证\n\n{pending}"


def format_terminology(value: Any) -> str:
    if not isinstance(value, dict) or not value:
        return "- TBD / 待补充"
    return "\n".join(f"- **{key}**: {definition}" for key, definition in value.items())


def build_context(spec: dict[str, Any]) -> dict[str, str]:
    return {
        "PROJECT_NAME": str(spec["project_name"]),
        "PROJECT_SLUG": str(spec["project_slug"]),
        "MODE": str(spec["mode"]),
        "DOMAIN": str(spec["domain"]),
        "SUMMARY": str(spec["summary"]),
        "BACKGROUND": str(spec.get("background") or "TBD / 待补充"),
        "RESEARCH_QUESTIONS": markdown_list(spec["research_questions"]),
        "HYPOTHESES": format_hypotheses(spec["hypotheses"]),
        "OBJECTIVES": format_objectives(spec["objectives"]),
        "DELIVERABLES": markdown_list(spec.get("deliverables")),
        "CONSTRAINTS": markdown_list(spec.get("constraints")),
        "MILESTONES": format_milestones(spec.get("milestones")),
        "RISKS": format_risks(spec.get("risks")),
        "EVIDENCE_STATUS": format_evidence(spec.get("evidence")),
        "TERMINOLOGY": format_terminology(spec.get("terminology")),
        "EXPERIMENT_PLAN": format_plan(spec.get("experiment_plan")),
        "COMPUTATION_PLAN": format_plan(spec.get("computation_plan")),
        "CREATED_DATE": date.today().isoformat(),
    }


def render_template(name: str, context: dict[str, str]) -> str:
    path = TEMPLATE_DIR / name
    text = path.read_text(encoding="utf-8")
    for key, value in context.items():
        text = text.replace("{{" + key + "}}", value)
    unresolved = sorted(set(re.findall(r"\{\{([A-Z0-9_]+)\}\}", text)))
    if unresolved:
        raise ValueError(f"Unresolved template fields in {name}: {unresolved}")
    return text.rstrip() + "\n"


def build_files(spec: dict[str, Any]) -> list[PlannedFile]:
    context = build_context(spec)
    files = [
        PlannedFile("README.md", render_template("readme.md.tmpl", context)),
        PlannedFile("PROJECT_CONTEXT.md", render_template("project_context.md.tmpl", context)),
        PlannedFile("AGENTS.md", render_template("agents.md.tmpl", context)),
        PlannedFile(".gitignore", render_template("gitignore.tmpl", context)),
        PlannedFile("docs/literature/reading_queue.md", render_template("reading_queue.md.tmpl", context)),
        PlannedFile("docs/research_plan.md", render_template("research_plan.md.tmpl", context)),
        PlannedFile("docs/milestones.md", render_template("milestones.md.tmpl", context)),
        PlannedFile("docs/risk_register.md", render_template("risk_register.md.tmpl", context)),
        PlannedFile("docs/decisions.md", render_template("decisions.md.tmpl", context)),
        PlannedFile("formal_data/README.md", render_template("formal_data_readme.md.tmpl", context)),
        PlannedFile("formal_data/MANIFEST.csv", render_template("manifest.csv.tmpl", context)),
        PlannedFile("docs/project_spec.json", json.dumps(spec, ensure_ascii=False, indent=2) + "\n"),
    ]
    mode = spec["mode"]
    if mode in {"experimental", "hybrid"}:
        files.append(PlannedFile("docs/experiment_plan.md", render_template("experiment_plan.md.tmpl", context)))
    if mode in {"computational", "hybrid"}:
        files.append(PlannedFile("docs/computation_plan.md", render_template("computation_plan.md.tmpl", context)))
    return files


def find_nonconforming_directories(root: Path) -> list[Path]:
    if not root.exists():
        return []
    bad = []
    for path in root.rglob("*"):
        if path.is_dir() and not SLUG_RE.fullmatch(path.name):
            bad.append(path)
    return bad


def preview(root: Path, directories: list[str], files: list[PlannedFile]) -> tuple[int, int]:
    create_count = 0
    keep_count = 0
    print(f"Project root: {root}")
    print("\nDirectory plan:")
    for relative in directories:
        path = root / relative
        if path.exists() and not path.is_dir():
            raise ValueError(f"Path conflict: expected directory but found file: {path}")
        state = "KEEP_DIR" if path.is_dir() else "CREATE_DIR"
        create_count += state == "CREATE_DIR"
        keep_count += state == "KEEP_DIR"
        print(f"[{state}] {relative}/")

    print("\nFile plan:")
    for item in files:
        path = root / item.relative_path
        if path.exists() and path.is_dir():
            raise ValueError(f"Path conflict: expected file but found directory: {path}")
        state = "KEEP_EXISTING" if path.exists() else "CREATE_FILE"
        create_count += state == "CREATE_FILE"
        keep_count += state == "KEEP_EXISTING"
        print(f"[{state}] {item.relative_path}")

    bad = find_nonconforming_directories(root)
    if bad:
        print("\nWarnings: existing nonconforming directory names are preserved, not renamed:")
        for path in bad:
            print(f"[WARNING] {path.relative_to(root)}")
    print(f"\nSummary: create={create_count}, keep={keep_count}, overwrite=0")
    return create_count, keep_count


def apply_plan(root: Path, directories: list[str], files: list[PlannedFile]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for relative in directories:
        (root / relative).mkdir(parents=True, exist_ok=True)
    for item in files:
        path = root / item.relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with path.open("x", encoding="utf-8", newline="\n") as handle:
                handle.write(item.content)
            print(f"[CREATED] {item.relative_path}")
        except FileExistsError:
            print(f"[KEPT] {item.relative_path}")


def initialize_git(root: Path) -> None:
    if (root / ".git").exists():
        print("[GIT] Existing repository kept")
        return
    subprocess.run(["git", "init"], cwd=root, check=True)
    print("[GIT] Repository initialized; no files were staged or committed")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path, help="Exact project root; basename must equal project_slug.")
    parser.add_argument("--spec", required=True, type=Path, help="UTF-8 project specification JSON.")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--dry-run", action="store_true", help="Preview only; write nothing.")
    action.add_argument("--apply", action="store_true", help="Create missing directories and files without overwriting.")
    parser.add_argument("--git-init", action="store_true", help="Initialize Git after apply; requires separate user approval.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        spec = load_spec(args.spec.resolve())
        root = args.root.resolve()
        slug = spec["project_slug"]
        if root.name != slug:
            raise ValueError(f"Project root basename must equal project_slug {slug!r}; got {root.name!r}")
        if root.exists() and not root.is_dir():
            raise ValueError(f"Project root is not a directory: {root}")
        if args.git_init and not args.apply:
            raise ValueError("--git-init is allowed only together with --apply")

        directories = sorted(set(BASE_DIRECTORIES + MODE_DIRECTORIES[spec["mode"]]))
        files = build_files(spec)
        preview(root, directories, files)
        if args.dry_run:
            print("\nDry run complete: no files were written.")
            return 0

        print("\nApplying confirmed plan...")
        apply_plan(root, directories, files)
        if args.git_init:
            initialize_git(root)
        print("\nInitialization complete.")
        return 0
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
