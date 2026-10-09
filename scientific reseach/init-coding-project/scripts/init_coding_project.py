#!/usr/bin/env python3
"""Preview and safely initialize a framework-agnostic coding project."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path, PurePosixPath
from typing import Any


SKILL_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_DIR = SKILL_ROOT / "assets" / "templates"
SLUG_RE = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
PROJECT_TYPES = {
    "application",
    "service",
    "library",
    "cli",
    "automation",
    "data",
    "infrastructure",
    "monorepo",
}
COMMAND_NAMES = ("setup", "dev", "test", "lint", "typecheck", "build")
BASE_DIRECTORIES = (
    "docs",
    "docs/product",
    "docs/architecture",
    "docs/architecture/adr",
    "docs/plans",
    "docs/records",
)


@dataclass(frozen=True)
class PlannedFile:
    relative_path: str
    content: str


def require_mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{field} must be an object")
    return value


def require_list(value: Any, field: str, *, nonempty: bool = False) -> list[Any]:
    if not isinstance(value, list) or (nonempty and not value):
        suffix = " and must not be empty" if nonempty else ""
        raise ValueError(f"{field} must be a list{suffix}")
    return value


def validate_relative_directory(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty relative POSIX path")
    if "\\" in value:
        raise ValueError(f"{field} must use POSIX '/' separators; got {value!r}")
    path = PurePosixPath(value)
    if path.is_absolute() or value.endswith("/"):
        raise ValueError(f"{field} must be a normalized relative directory; got {value!r}")
    parts = path.parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise ValueError(f"{field} contains an unsafe path segment: {value!r}")
    normalized = path.as_posix()
    if normalized != value or parts[0] == ".git":
        raise ValueError(f"{field} must be a safe normalized relative directory; got {value!r}")
    return normalized


def load_spec(path: Path) -> dict[str, Any]:
    try:
        spec = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"Spec file does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path}: {exc}") from exc

    if not isinstance(spec, dict):
        raise ValueError("Spec root must be an object")

    required = (
        "schema_version",
        "project_name",
        "project_slug",
        "summary",
        "documentation_language",
        "project_types",
        "problem",
        "target_users",
        "goals",
        "scope",
        "stack",
        "architecture",
        "quality",
        "deliverables",
        "constraints",
        "milestones",
        "risks",
    )
    missing = [key for key in required if key not in spec]
    if missing:
        raise ValueError(f"Missing required spec fields: {', '.join(missing)}")

    if spec["schema_version"] != 1:
        raise ValueError("schema_version must equal 1")
    for field in ("project_name", "summary", "problem", "documentation_language"):
        if not isinstance(spec[field], str) or not spec[field].strip():
            raise ValueError(f"{field} must be a non-empty string")

    slug = spec["project_slug"]
    if not isinstance(slug, str) or not SLUG_RE.fullmatch(slug):
        raise ValueError(f"project_slug must match {SLUG_RE.pattern!r}; got {slug!r}")

    project_types = require_list(spec["project_types"], "project_types", nonempty=True)
    if any(not isinstance(item, str) for item in project_types):
        raise ValueError("project_types entries must be strings")
    if len(project_types) != len(set(project_types)):
        raise ValueError("project_types must not contain duplicates")
    invalid_types = sorted(set(project_types) - PROJECT_TYPES)
    if invalid_types:
        raise ValueError(f"Unsupported project_types: {', '.join(invalid_types)}")

    require_list(spec["target_users"], "target_users")
    goals = require_list(spec["goals"], "goals", nonempty=True)
    for index, goal in enumerate(goals):
        goal = require_mapping(goal, f"goals[{index}]")
        if not isinstance(goal.get("description"), str) or not goal["description"].strip():
            raise ValueError(f"goals[{index}].description must be a non-empty string")
        require_list(goal.get("success_criteria"), f"goals[{index}].success_criteria", nonempty=True)

    scope = require_mapping(spec["scope"], "scope")
    require_list(scope.get("in"), "scope.in")
    require_list(scope.get("out"), "scope.out")

    stack = require_mapping(spec["stack"], "stack")
    for field in ("languages", "runtimes", "frameworks", "evidence"):
        require_list(stack.get(field), f"stack.{field}")
    package_manager = stack.get("package_manager")
    if package_manager is not None and not isinstance(package_manager, str):
        raise ValueError("stack.package_manager must be a string or null")

    architecture = require_mapping(spec["architecture"], "architecture")
    for field in ("style", "modules", "external_dependencies", "pending_decisions"):
        if field not in architecture:
            raise ValueError(f"architecture.{field} is required")
    if not isinstance(architecture["style"], str):
        raise ValueError("architecture.style must be a string")
    for field in ("modules", "external_dependencies", "pending_decisions"):
        require_list(architecture[field], f"architecture.{field}")

    quality = require_mapping(spec["quality"], "quality")
    commands = require_mapping(quality.get("commands"), "quality.commands")
    for command_name in COMMAND_NAMES:
        if command_name not in commands:
            raise ValueError(f"quality.commands.{command_name} is required")
        command = commands[command_name]
        if command is not None and not isinstance(command, str):
            raise ValueError(f"quality.commands.{command_name} must be a string or null")
    if not isinstance(quality.get("testing_strategy"), str):
        raise ValueError("quality.testing_strategy must be a string")
    for field in ("test_seams", "ci_required", "non_functional_requirements", "definition_of_done"):
        require_list(quality.get(field), f"quality.{field}")

    for field in ("deliverables", "constraints", "milestones", "risks"):
        require_list(spec[field], field)

    documentation = require_mapping(spec.setdefault("documentation", {}), "documentation")
    for field in ("reports", "presentations", "assets", "deliverables"):
        value = documentation.setdefault(field, False)
        if not isinstance(value, bool):
            raise ValueError(f"documentation.{field} must be a boolean")

    agent_instructions = require_mapping(spec.setdefault("agent_instructions", {}), "agent_instructions")
    create_agents_md = agent_instructions.setdefault("create_agents_md", True)
    if not isinstance(create_agents_md, bool):
        raise ValueError("agent_instructions.create_agents_md must be a boolean")

    scaffold = require_mapping(spec.setdefault("scaffold", {}), "scaffold")
    raw_directories = require_list(scaffold.setdefault("directories", []), "scaffold.directories")
    directories = [
        validate_relative_directory(item, f"scaffold.directories[{index}]")
        for index, item in enumerate(raw_directories)
    ]
    if len(directories) != len(set(directories)):
        raise ValueError("scaffold.directories must not contain duplicates")
    scaffold["directories"] = directories

    planned_commands = require_list(scaffold.setdefault("planned_commands", []), "scaffold.planned_commands")
    for index, item in enumerate(planned_commands):
        item = require_mapping(item, f"scaffold.planned_commands[{index}]")
        if not isinstance(item.get("command"), str) or not item["command"].strip():
            raise ValueError(f"scaffold.planned_commands[{index}].command must be a non-empty string")
        if item.get("status") != "proposed":
            raise ValueError(f"scaffold.planned_commands[{index}].status must equal 'proposed'")

    require_list(spec.setdefault("assumptions", []), "assumptions")
    require_list(spec.setdefault("open_questions", []), "open_questions")
    external = require_mapping(spec.setdefault("external_operations", {}), "external_operations")
    external.setdefault("web_research_approved", False)
    external.setdefault("issue_tracker_sync", "disabled")
    external.setdefault("remote_repository", "disabled")
    return spec


def markdown_list(items: Any, *, empty: str = "- 无") -> str:
    if not items:
        return empty
    lines: list[str] = []
    for item in items:
        if isinstance(item, dict):
            lines.append("- `" + json.dumps(item, ensure_ascii=False, sort_keys=True) + "`")
        else:
            lines.append(f"- {item}")
    return "\n".join(lines)


def format_goals(goals: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for index, goal in enumerate(goals, start=1):
        identifier = goal.get("id") or f"G{index}"
        lines.append(f"### {identifier} — {goal['description']}")
        lines.append(markdown_list(goal["success_criteria"]))
        lines.append("")
    return "\n".join(lines).rstrip()


def format_stack(stack: dict[str, Any]) -> str:
    package_manager = stack.get("package_manager") or "待确认"
    return "\n".join(
        (
            f"- 语言：{', '.join(map(str, stack['languages'])) or '待确认'}",
            f"- 运行时：{', '.join(map(str, stack['runtimes'])) or '待确认'}",
            f"- 框架：{', '.join(map(str, stack['frameworks'])) or '待确认'}",
            f"- 包管理器：{package_manager}",
            "- 依据：",
            markdown_list(stack["evidence"], empty="  - 待确认"),
        )
    )


def format_architecture(architecture: dict[str, Any]) -> str:
    return "\n".join(
        (
            f"- 风格：{architecture['style'] or 'pending'}",
            "- 模块：",
            markdown_list(architecture["modules"], empty="  - pending"),
            "- 外部依赖：",
            markdown_list(architecture["external_dependencies"], empty="  - 无"),
            "- 待决策：",
            markdown_list(architecture["pending_decisions"], empty="  - 无"),
        )
    )


def format_quality(quality: dict[str, Any]) -> str:
    lines = ["### 命令", "", "| 用途 | 命令 |", "|---|---|"]
    for name in COMMAND_NAMES:
        command = quality["commands"].get(name)
        rendered = f"`{command}`" if command else "待确认"
        lines.append(f"| {name} | {rendered} |")
    lines.extend(
        (
            "",
            "### 测试策略",
            "",
            quality["testing_strategy"] or "pending",
            "",
            "### 测试 seam",
            "",
            markdown_list(quality["test_seams"], empty="- pending"),
            "",
            "### CI 必须项",
            "",
            markdown_list(quality["ci_required"], empty="- pending"),
            "",
            "### 非功能要求",
            "",
            markdown_list(quality["non_functional_requirements"], empty="- 无"),
            "",
            "### Definition of Done",
            "",
            markdown_list(quality["definition_of_done"], empty="- pending"),
        )
    )
    return "\n".join(lines)


def format_planned_commands(commands: list[dict[str, Any]]) -> str:
    if not commands:
        return "- 无"
    lines = []
    for item in commands:
        purpose = item.get("purpose") or "待确认"
        lines.append(f"- `{item['command']}` — {purpose}（状态：`proposed`）")
    return "\n".join(lines)


def build_context(spec: dict[str, Any]) -> dict[str, str]:
    scaffold = spec["scaffold"]
    return {
        "PROJECT_NAME": str(spec["project_name"]),
        "PROJECT_SLUG": str(spec["project_slug"]),
        "SUMMARY": str(spec["summary"]),
        "DOCUMENTATION_LANGUAGE": str(spec["documentation_language"]),
        "PROJECT_TYPES": markdown_list(spec["project_types"]),
        "PROJECT_TYPES_INLINE": ", ".join(map(str, spec["project_types"])),
        "PROBLEM": str(spec["problem"]),
        "TARGET_USERS": markdown_list(spec["target_users"], empty="- pending"),
        "GOALS": format_goals(spec["goals"]),
        "SCOPE_IN": markdown_list(spec["scope"]["in"], empty="- pending"),
        "SCOPE_OUT": markdown_list(spec["scope"]["out"], empty="- pending"),
        "STACK": format_stack(spec["stack"]),
        "ARCHITECTURE": format_architecture(spec["architecture"]),
        "QUALITY": format_quality(spec["quality"]),
        "DELIVERABLES": markdown_list(spec["deliverables"], empty="- pending"),
        "CONSTRAINTS": markdown_list(spec["constraints"]),
        "ASSUMPTIONS": markdown_list(spec["assumptions"]),
        "OPEN_QUESTIONS": markdown_list(spec["open_questions"]),
        "MILESTONES": markdown_list(spec["milestones"], empty="- pending"),
        "RISKS": markdown_list(spec["risks"]),
        "SCAFFOLD_DIRECTORIES": markdown_list(scaffold["directories"], empty="- 不创建技术栈目录"),
        "PLANNED_COMMANDS": format_planned_commands(scaffold["planned_commands"]),
        "CREATED_DATE": date.today().isoformat(),
    }


def render_template(name: str, context: dict[str, str]) -> str:
    text = (TEMPLATE_DIR / name).read_text(encoding="utf-8")
    placeholders = sorted(set(re.findall(r"\{\{([A-Z0-9_]+)\}\}", text)))
    missing = [key for key in placeholders if key not in context]
    if missing:
        raise ValueError(f"Unresolved template fields in {name}: {missing}")
    for key in placeholders:
        text = text.replace("{{" + key + "}}", context[key])
    return text.rstrip() + "\n"


def expand_directories(directories: list[str]) -> list[str]:
    expanded: set[str] = set()
    for value in directories:
        parts = PurePosixPath(value).parts
        for index in range(1, len(parts) + 1):
            expanded.add(PurePosixPath(*parts[:index]).as_posix())
    return sorted(expanded, key=lambda item: (len(PurePosixPath(item).parts), item))


def build_directories(spec: dict[str, Any]) -> list[str]:
    directories = list(BASE_DIRECTORIES)
    documentation = spec["documentation"]
    if documentation["reports"]:
        directories.append("docs/reports")
    if documentation["presentations"]:
        directories.append("docs/presentations")
    if documentation["assets"]:
        directories.append("assets")
    if documentation["deliverables"]:
        directories.append("deliverables")
    directories.extend(spec["scaffold"]["directories"])
    return expand_directories(directories)


def build_files(spec: dict[str, Any]) -> list[PlannedFile]:
    context = build_context(spec)
    files = [
        PlannedFile("README.md", render_template("readme.md.tmpl", context)),
        PlannedFile("PROJECT_CONTEXT.md", render_template("project_context.md.tmpl", context)),
        PlannedFile("docs/product/product_brief.md", render_template("product_brief.md.tmpl", context)),
        PlannedFile("docs/architecture/architecture.md", render_template("architecture.md.tmpl", context)),
        PlannedFile("docs/architecture/adr/README.md", render_template("adr_readme.md.tmpl", context)),
        PlannedFile("docs/plans/implementation_plan.md", render_template("implementation_plan.md.tmpl", context)),
        PlannedFile("docs/records/project_log.md", render_template("project_log.md.tmpl", context)),
        PlannedFile("docs/project_spec.json", json.dumps(spec, ensure_ascii=False, indent=2) + "\n"),
    ]
    if spec["agent_instructions"]["create_agents_md"]:
        files.insert(2, PlannedFile("AGENTS.md", render_template("agents.md.tmpl", context)))
    return files


def check_no_symlink_ancestor(root: Path, target: Path) -> None:
    if root.exists() and root.is_symlink():
        raise ValueError(f"Project root must not be a symlink: {root}")
    current = root
    for part in target.relative_to(root).parts:
        current = current / part
        if current.exists() and current.is_symlink():
            raise ValueError(f"Refusing to traverse existing symlink: {current}")


def check_conflicts(root: Path, directories: list[str], files: list[PlannedFile]) -> None:
    for relative in directories:
        path = root / relative
        check_no_symlink_ancestor(root, path)
        if path.exists() and not path.is_dir():
            raise ValueError(f"Path conflict: expected directory but found file: {path}")
    for item in files:
        path = root / item.relative_path
        check_no_symlink_ancestor(root, path)
        if path.exists() and path.is_dir():
            raise ValueError(f"Path conflict: expected file but found directory: {path}")
        parent = path.parent
        while parent != root:
            if parent.exists() and not parent.is_dir():
                raise ValueError(f"Path conflict: parent is not a directory: {parent}")
            parent = parent.parent


def preview(root: Path, spec: dict[str, Any], directories: list[str], files: list[PlannedFile]) -> None:
    check_conflicts(root, directories, files)
    create_count = 0
    keep_count = 0
    print(f"Project: {spec['project_name']}")
    print(f"Slug: {spec['project_slug']}")
    print(f"Types: {', '.join(spec['project_types'])}")
    print(f"Project root: {root}")
    print("\nDirectory plan:")
    for relative in directories:
        state = "KEEP_DIR" if (root / relative).is_dir() else "CREATE_DIR"
        create_count += state == "CREATE_DIR"
        keep_count += state == "KEEP_DIR"
        print(f"[{state}] {relative}/")
    print("\nFile plan:")
    for item in files:
        state = "KEEP_EXISTING" if (root / item.relative_path).exists() else "CREATE_FILE"
        create_count += state == "CREATE_FILE"
        keep_count += state == "KEEP_EXISTING"
        print(f"[{state}] {item.relative_path}")
    print("\n[PRESERVE_EXISTING] Every path outside this plan remains untouched")
    print("[NO_EXECUTE] scaffold.planned_commands are recorded, never executed")
    print(f"Summary: create={create_count}, keep={keep_count}, overwrite=0")


def apply_plan(root: Path, directories: list[str], files: list[PlannedFile]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    check_conflicts(root, directories, files)
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
    parser.add_argument("--root", required=True, type=Path, help="Target project root")
    parser.add_argument("--spec", required=True, type=Path, help="UTF-8 project specification JSON")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--dry-run", action="store_true", help="Preview only; write nothing")
    action.add_argument("--apply", action="store_true", help="Create missing paths without overwriting")
    parser.add_argument("--git-init", action="store_true", help="Initialize Git after apply; requires separate approval")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.git_init and not args.apply:
            raise ValueError("--git-init requires --apply and separate user approval")
        spec = load_spec(args.spec.resolve())
        root = args.root.expanduser().absolute()
        if root.exists() and not root.is_dir():
            raise ValueError(f"Project root exists but is not a directory: {root}")
        directories = build_directories(spec)
        files = build_files(spec)
        preview(root, spec, directories, files)
        if args.dry_run:
            print("\nDry run complete; no files were written")
            return 0
        apply_plan(root, directories, files)
        if args.git_init:
            initialize_git(root)
        return 0
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
