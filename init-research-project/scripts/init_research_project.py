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
    "docs/plans",
    "docs/records",
    "docs/records/task_logs",
    "docs/records/task_logs/daily",
    "docs/presentations",
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
    "raw_data/calculations",
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
    "computational": ["docs/records/design_reviews"],
    "hybrid": ["docs/records/design_reviews", "raw_data/experiments", "raw_data/calculations"],
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
    for index, item in enumerate(spec.get("systems", []), start=1):
        if isinstance(item, dict):
            system_slug = str(item.get("system_slug") or "")
            cases = item.get("case_slugs", [])
        else:
            system_slug = str(item)
            cases = []
        if not SLUG_RE.fullmatch(system_slug):
            raise ValueError(f"systems[{index}].system_slug must use English lowercase_snake_case; got {system_slug!r}")
        if not isinstance(cases, list):
            raise ValueError(f"systems[{index}].case_slugs must be a list")
        for case_index, case_slug in enumerate(cases, start=1):
            if not SLUG_RE.fullmatch(str(case_slug)):
                raise ValueError(
                    f"systems[{index}].case_slugs[{case_index}] must use English lowercase_snake_case; got {case_slug!r}"
                )
    return spec


def markdown_list(items: Any, empty: str = "- 待补充") -> str:
    if not items:
        return empty
    if not isinstance(items, list):
        items = [items]
    lines = []
    for item in items:
        if isinstance(item, dict):
            lines.append("- 结构化内容：")
            lines.append("  ```json")
            for line in json.dumps(item, ensure_ascii=False, indent=2).splitlines():
                lines.append(f"  {line}")
            lines.append("  ```")
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
                f"- 陈述：{item['statement']}",
                f"- 否证条件：{item['falsification']}",
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
                f"- 目标：{item['description']}",
                f"- 验收标准：{item['success_criteria']}",
                "",
            ]
        )
    return "\n".join(lines).rstrip()


def format_milestones(items: Any) -> str:
    if not items:
        return "| ID | 里程碑 | 验收条件 | 目标日期 |\n|---|---|---|---|\n| M1 | 待补充 | 待补充 | 待补充 |"
    lines = [
        "| ID | 里程碑 | 验收条件 | 目标日期 |",
        "|---|---|---|---|",
    ]
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            item = {"description": str(item)}
        lines.append(
            f"| {item.get('id', f'M{index}')} | {item.get('description', '待补充')} | "
            f"{item.get('acceptance', '待补充')} | {item.get('target_date', '待补充')} |"
        )
    return "\n".join(lines)


def format_risks(items: Any) -> str:
    if not items:
        return "| 风险 | 可能性 | 影响 | 缓解措施 |\n|---|---|---|---|\n| 待补充 | 待补充 | 待补充 | 待补充 |"
    lines = [
        "| 风险 | 可能性 | 影响 | 缓解措施 |",
        "|---|---|---|---|",
    ]
    for item in items:
        if not isinstance(item, dict):
            item = {"risk": str(item)}
        lines.append(
            f"| {item.get('risk', '待补充')} | {item.get('likelihood', '待补充')} | "
            f"{item.get('impact', '待补充')} | {item.get('mitigation', '待补充')} |"
        )
    return "\n".join(lines)


def format_plan(value: Any) -> str:
    if not value:
        return "待补充"
    if not isinstance(value, dict):
        return str(value)
    lines = []
    headings = {
        "models": "模型",
        "methods": "方法",
        "parameter_matrix": "参数矩阵",
        "vasp_workflow_envelope": "VASP workflow 参数包",
        "convergence": "收敛测试",
        "validation": "验证",
        "resource_budget": "资源预算",
        "stop_conditions": "停止条件",
        "variables": "变量",
        "controls": "对照",
        "measurements": "测量",
        "replication": "重复与复现",
        "analysis": "分析",
    }
    for key, item in value.items():
        title = headings.get(key, key)
        lines.append(f"## {title}")
        if isinstance(item, list):
            lines.append(markdown_list(item))
        elif isinstance(item, dict):
            lines.append("```json")
            lines.append(json.dumps(item, ensure_ascii=False, indent=2))
            lines.append("```")
        else:
            lines.append(str(item) if item else "待补充")
        lines.append("")
    return "\n".join(lines).rstrip()


def format_evidence(value: Any) -> str:
    if not isinstance(value, dict):
        return "- 已批准外部检索：否\n- 待验证：待补充"
    approved = "是" if value.get("external_search_approved") else "否"
    sources = markdown_list(value.get("sources"), empty="- 暂无")
    pending = markdown_list(value.get("pending_validation"), empty="- 暂无")
    return f"- 已批准外部检索：{approved}\n\n### 来源\n\n{sources}\n\n### 待验证\n\n{pending}"


def format_terminology(value: Any) -> str:
    if not isinstance(value, dict) or not value:
        return "- 待补充"
    return "\n".join(f"- **{key}**: {definition}" for key, definition in value.items())


def build_context(spec: dict[str, Any]) -> dict[str, str]:
    return {
        "PROJECT_NAME": str(spec["project_name"]),
        "PROJECT_SLUG": str(spec["project_slug"]),
        "MODE": str(spec["mode"]),
        "DOMAIN": str(spec["domain"]),
        "SUMMARY": str(spec["summary"]),
        "BACKGROUND": str(spec.get("background") or "待补充"),
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


def build_calculation_design(spec: dict[str, Any]) -> dict[str, Any]:
    project_slug = str(spec["project_slug"])
    hypotheses = [
        {
            "id": str(item.get("id") or f"H{index}"),
            "statement": str(item["statement"]),
            "falsification": str(item["falsification"]),
        }
        for index, item in enumerate(spec["hypotheses"], start=1)
    ]
    research_questions = []
    for index, item in enumerate(spec["research_questions"], start=1):
        if isinstance(item, dict):
            research_questions.append(
                {"id": str(item.get("id") or f"Q{index}"), "question": str(item.get("question") or "待补充")}
            )
        else:
            research_questions.append({"id": f"Q{index}", "question": str(item)})

    systems = []
    for item in spec.get("systems", []):
        system_slug = str(item["system_slug"] if isinstance(item, dict) else item)
        systems.append(
            {
                "system_slug": system_slug,
                "model": "待补充",
                "structure_provenance": "待补充",
                "assumptions": [],
            }
        )
    if not systems:
        systems.append(
            {
                "system_slug": "system_tbd",
                "model": "待补充",
                "structure_provenance": "待补充",
                "assumptions": [],
            }
        )

    computation_plan = spec.get("computation_plan")
    if not isinstance(computation_plan, dict):
        computation_plan = {}
    workflow_envelopes = computation_plan.get("vasp_workflow_envelope")
    if not isinstance(workflow_envelopes, list) or not workflow_envelopes:
        workflow_envelopes = [{}]

    matrix: list[dict[str, Any]] = []
    vasp_envelopes: list[dict[str, Any]] = []
    known_systems = {item["system_slug"] for item in systems}
    default_system = systems[0]["system_slug"]
    for index, item in enumerate(workflow_envelopes, start=1):
        if not isinstance(item, dict):
            item = {}
        system_slug = str(item.get("system_slug") or default_system)
        if system_slug not in known_systems:
            systems.append(
                {
                    "system_slug": system_slug,
                    "model": "待补充",
                    "structure_provenance": "待补充",
                    "assumptions": [],
                }
            )
            known_systems.add(system_slug)
        case_slug = str(item.get("case_slug") or f"case_{index}")
        matrix_id = f"matrix_{system_slug}_{case_slug}"
        stages = item.get("stages") if isinstance(item.get("stages"), list) else ["relax"]
        matrix.append(
            {
                "id": matrix_id,
                "class": "exploratory",
                "system_slug": system_slug,
                "case_slug": case_slug,
                "hypothesis_ids": [entry["id"] for entry in hypotheses],
                "purpose": "待补充",
                "variables": {},
                "fixed_parameters": {},
                "stages": stages,
                "observable_ids": ["OBS1"],
                "completion_gate": "待补充",
            }
        )
        vasp_envelopes.append(
            {
                "matrix_id": matrix_id,
                "structure_source": "待补充",
                "incar_policy": str(item.get("incar_inheritance") or "待补充"),
                "kpoints_policy": str(item.get("kpoints_policy") or "待补充"),
                "potcar_labels": item.get("potcar_labels") if isinstance(item.get("potcar_labels"), dict) else {},
                "resource_profile": str(item.get("cluster_profile") or "待补充"),
                "completion_gates": {stage: "待补充" for stage in stages},
            }
        )

    evidence_spec = spec.get("evidence") if isinstance(spec.get("evidence"), dict) else {}
    sources = evidence_spec.get("sources") if isinstance(evidence_spec.get("sources"), list) else []
    evidence = [
        {
            "id": f"E{index}",
            "claim": "待补充",
            "source": str(source),
            "kind": "primary_source",
            "status": "pending",
            "supports": [entry["id"] for entry in hypotheses],
        }
        for index, source in enumerate(sources, start=1)
    ]
    if not evidence:
        evidence.append(
            {
                "id": "E1",
                "claim": "待补充",
                "source": "待补充",
                "kind": "primary_source",
                "status": "pending",
                "supports": [entry["id"] for entry in hypotheses],
            }
        )

    stop_conditions = computation_plan.get("stop_conditions")
    if not isinstance(stop_conditions, list) or not stop_conditions:
        stop_conditions = ["待补充"]
    return {
        "schema_version": 1,
        "design_id": f"{project_slug}_computation",
        "revision": 1,
        "status": "draft",
        "project_slug": project_slug,
        "title": f"{spec['project_name']}计算实验设计",
        "research_questions": research_questions,
        "hypotheses": hypotheses,
        "systems": systems,
        "observables": [
            {
                "id": "OBS1",
                "hypothesis_ids": [entry["id"] for entry in hypotheses],
                "quantity": "待补充",
                "decision_rule": "待补充",
                "uncertainty_target": "待补充",
            }
        ],
        "controls": [{"id": "CTRL1", "type": "baseline", "purpose": "待补充", "fixed_or_varied": "待补充"}],
        "convergence_studies": [
            {
                "id": "CONV1",
                "parameter": "待补充",
                "candidate_values": [],
                "fixed_conditions": [],
                "target_observable_ids": ["OBS1"],
                "acceptance_rule": "待补充",
                "selected_value": None,
            }
        ],
        "validation_checks": [
            {"id": "VAL1", "type": "independent_reference", "reference": "待补充", "acceptance_rule": "待补充"}
        ],
        "calculation_matrix": matrix,
        "vasp_stage_envelopes": vasp_envelopes,
        "evidence": evidence,
        "uncertainty_budget": [],
        "resource_budget": {
            "task_count": "待补充",
            "compute": str(computation_plan.get("resource_budget") or "待补充"),
            "storage": "待补充",
        },
        "stop_conditions": stop_conditions,
        "pending_decisions": ["完成并审核计算实验设计"],
    }


def build_files(spec: dict[str, Any]) -> list[PlannedFile]:
    context = build_context(spec)
    agents_context = {**context, "AGENT_CONTEXT_FILENAME": "AGENTS.md"}
    claude_context = {**context, "AGENT_CONTEXT_FILENAME": "CLAUDE.md"}
    files = [
        PlannedFile("README.md", render_template("readme.md.tmpl", context)),
        PlannedFile("PROJECT_CONTEXT.md", render_template("project_context.md.tmpl", context)),
        PlannedFile("AGENTS.md", render_template("agents.md.tmpl", agents_context)),
        PlannedFile("CLAUDE.md", render_template("agents.md.tmpl", claude_context)),
        PlannedFile(".gitignore", render_template("gitignore.tmpl", context)),
        PlannedFile("docs/literature/reading_queue.md", render_template("reading_queue.md.tmpl", context)),
        PlannedFile("docs/plans/research_plan.md", render_template("research_plan.md.tmpl", context)),
        PlannedFile("docs/plans/milestones.md", render_template("milestones.md.tmpl", context)),
        PlannedFile("docs/plans/risk_register.md", render_template("risk_register.md.tmpl", context)),
        PlannedFile("docs/records/decisions.md", render_template("decisions.md.tmpl", context)),
        PlannedFile("docs/records/task_logs/README.md", render_template("task_logs_readme.md.tmpl", context)),
        PlannedFile("docs/records/task_logs/project_log.md", render_template("project_log.md.tmpl", context)),
        PlannedFile(
            f"docs/records/task_logs/daily/{context['CREATED_DATE']}.md",
            render_template("daily_task_log.md.tmpl", context),
        ),
        PlannedFile("formal_data/README.md", render_template("formal_data_readme.md.tmpl", context)),
        PlannedFile("formal_data/MANIFEST.csv", render_template("manifest.csv.tmpl", context)),
        PlannedFile("docs/project_spec.json", json.dumps(spec, ensure_ascii=False, indent=2) + "\n"),
    ]
    mode = spec["mode"]
    if mode in {"experimental", "hybrid"}:
        files.append(PlannedFile("docs/plans/experiment_plan.md", render_template("experiment_plan.md.tmpl", context)))
    if mode in {"computational", "hybrid"}:
        files.append(PlannedFile("docs/plans/computation_plan.md", render_template("computation_plan.md.tmpl", context)))
        files.append(
            PlannedFile(
                "docs/plans/calculation_design.json",
                json.dumps(build_calculation_design(spec), ensure_ascii=False, indent=2) + "\n",
            )
        )
    return files


def system_directories(spec: dict[str, Any]) -> list[str]:
    directories: list[str] = []
    for item in spec.get("systems", []):
        if isinstance(item, dict):
            system_slug = str(item["system_slug"])
            case_slugs = [str(case_slug) for case_slug in item.get("case_slugs", [])]
        else:
            system_slug = str(item)
            case_slugs = []
        directories.append(f"raw_data/calculations/{system_slug}")
        directories.append(f"formal_data/structures/{system_slug}")
        for case_slug in case_slugs:
            directories.append(f"raw_data/calculations/{system_slug}/{case_slug}")
    return directories


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

        directories = sorted(set(BASE_DIRECTORIES + MODE_DIRECTORIES[spec["mode"]] + system_directories(spec)))
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
