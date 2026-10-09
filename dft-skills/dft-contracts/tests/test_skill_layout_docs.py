from __future__ import annotations

from pathlib import Path
import re


SKILLHUB = Path(__file__).resolve().parents[2]
DFT_SKILLS = (
    "dft-design",
    "dft-workflow",
    "dft-analysis",
    "dft-work-manager",
    "dft-research-ideation",
)


TASK7_DOCUMENTS = (
    "dft-design/SKILL.md",
    "dft-design/references/design-contract.md",
    "dft-design/references/engine-contract.md",
    "dft-design/assets/plan_readme.template.md",
    "dft-workflow/SKILL.md",
    "dft-workflow/references/workflow-order.md",
    "dft-workflow/references/input-review.md",
    "dft-workflow/references/submit-review.md",
    "dft-workflow/references/resource-preflight.md",
    "dft-workflow/references/iterative-relax-gate.md",
    "dft-workflow/references/error-recovery.md",
    "dft-workflow/references/directory-layout.md",
    "dft-analysis/SKILL.md",
    "dft-analysis/references/failure-diagnosis.md",
    "dft-analysis/references/report-format.md",
    "dft-work-manager/SKILL.md",
    "dft-work-manager/references/skill-contract.md",
    "dft-work-manager/references/task-readme-template.md",
    "dft-contracts/references/workspace-layout.md",
)


def _read(relative_path: str) -> str:
    return (SKILLHUB / relative_path).read_text(encoding="utf-8")


def _recommended_text(text: str) -> str:
    """Return the recommended part, excluding an explicitly named legacy section."""

    match = re.search(r"(?im)^##+ .*?(?:compatibility|legacy)\b", text)
    return text if match is None else text[: match.start()]


def test_every_dft_skill_routes_to_the_shared_workspace_contract() -> None:
    for skill in DFT_SKILLS:
        text = (SKILLHUB / skill / "SKILL.md").read_text(encoding="utf-8")
        assert "../dft-contracts/references/workspace-layout.md" in text, skill


def test_canonical_layout_docs_do_not_embed_developer_work_roots() -> None:
    paths = [
        SKILLHUB / "dft-contracts" / "references" / "workspace-layout.md",
        SKILLHUB / "dft-workflow" / "references" / "directory-layout.md",
        *(SKILLHUB / skill / "SKILL.md" for skill in DFT_SKILLS),
    ]
    forbidden = (
        "/Users/example",
        "/opt/example/project",
        "/home/<user>/projects",
        "raw_data/calculations/<system_slug>",
    )
    for path in paths:
        text = path.read_text(encoding="utf-8")
        for value in forbidden:
            assert value not in text, f"{path}: {value}"


def test_manager_declares_live_leaf_as_truth_and_archive_as_optional() -> None:
    text = (SKILLHUB / "dft-work-manager" / "SKILL.md").read_text(encoding="utf-8")
    assert "The canonical record is the live task" in text
    assert "Keep `workflow.json` as the source of execution state" in text
    assert "as the source" in text
    assert "An archive is an explicit export" in text
    assert "task-local analysis/" in text
    assert "`failed/`" in text
    assert "Classify existing files before moving or exporting them" in text
    assert "marked latest-status blocks" in text
    assert "Archive creation never" in text
    assert "deletes or moves the live source" in text
    assert "Legacy structure-level analysis remains supported" in text
    assert "does not replace" in text
    assert "human-record update step" in text


def test_root_services_and_two_level_script_policy_are_documented() -> None:
    layout = (SKILLHUB / "dft-contracts" / "references" / "workspace-layout.md").read_text(encoding="utf-8")
    analysis = (SKILLHUB / "dft-analysis" / "SKILL.md").read_text(encoding="utf-8")
    manager = (SKILLHUB / "dft-work-manager" / "SKILL.md").read_text(encoding="utf-8")
    assert "plans/<composition>/<structure>" in layout
    assert "logs/<composition>/<structure>.md" in layout
    assert "code/templates/" in layout
    assert "structure-local" in layout
    assert "<workspace_root>/code/" in analysis
    assert "<structure_root>/scripts/" in analysis
    assert "scripts/vwm_task_log.py" in manager
    assert "README" in layout and "main_report.md" in layout


def test_project_resource_baseline_is_persistent_and_not_per_task() -> None:
    layout = (SKILLHUB / "dft-contracts" / "references" / "workspace-layout.md").read_text(encoding="utf-8")
    workflow = (SKILLHUB / "dft-workflow" / "references" / "resource-preflight.md").read_text(encoding="utf-8")
    assert "docs/project-resources.md" in layout
    assert "AGENTS.md" in layout
    assert "resource JSON" in layout
    assert "environment file per task" in layout
    assert "dft-submit" in workflow
    assert "one target-shell invocation" in workflow
    assert "drift" in workflow
    assert "scientific input-only change" in workflow


def test_workflow_documents_canonical_prepare_and_submission_boundary() -> None:
    skill = (SKILLHUB / "dft-workflow" / "SKILL.md").read_text(encoding="utf-8")
    profiles = (SKILLHUB / "dft-workflow" / "references" / "job-profiles.md").read_text(
        encoding="utf-8"
    )
    assert "initialize --draft" in skill
    assert "bind-approval" in skill
    assert "job.script" in skill
    assert "dft.project-resources.v1" in profiles
    assert "status: approved" in profiles
    assert "launch_template" in profiles
    assert "dft-submit determines defaults" in profiles
    assert "method: modules" in profiles
    assert "source-script" in profiles
    assert "source_command" in profiles


def test_task7_contracts_are_present_in_their_owning_documents() -> None:
    design = " ".join("\n".join(_read(path) for path in TASK7_DOCUMENTS[:4]).lower().split())
    workflow = "\n".join(_read(path) for path in TASK7_DOCUMENTS[4:12]).lower()
    analysis = "\n".join(_read(path) for path in TASK7_DOCUMENTS[12:15]).lower()
    manager = "\n".join(_read(path) for path in TASK7_DOCUMENTS[15:18]).lower()
    layout = _read(TASK7_DOCUMENTS[18]).lower()

    assert "design the complete task tree and all determinable inputs" in design
    assert "one user scientific-parameter approval" in design
    assert "initialize all executable leaves" in design
    assert "current on-disk inputs are authoritative" in workflow
    assert "hash mismatch triggers reconciliation, not re-approval" in workflow
    assert "program first, professional agent second, user only for a major conflict" in workflow
    assert "technical failure retries in place" in workflow
    assert "scientifically unexpected completion creates a `rerun_nnn` branch" in analysis
    assert "scheduler_complete" in analysis
    assert "artifact_complete" in analysis
    assert "scientifically_accepted" in analysis
    assert "one target-shell invocation" in workflow
    assert "one workflow.json per executable leaf" in layout
    assert "workflow.json is the sole live leaf ledger" in manager
    assert "`.dft/resource-profile.json` is the project cache" in layout


def test_task7_legacy_commands_are_explicitly_compatibility_only() -> None:
    workflow = _read("dft-workflow/SKILL.md").lower()
    design = _read("dft-design/SKILL.md").lower()

    assert "compatibility only" in workflow
    assert "prepare" in workflow
    assert "vwf" in workflow and "qewf" in workflow
    assert "compatibility only" in design
    assert "bootstrap" in design


def test_recommended_sections_do_not_require_repeated_reviews_or_broad_probes() -> None:
    forbidden_patterns = (
        re.compile(r"before\s+any\s+[`']?sbatch.*(?:explicit|user).*approval", re.I | re.S),
        re.compile(r"\b(?:every|each)\b.{0,100}\bsubmission\b.{0,100}\bapproval\b", re.I | re.S),
        re.compile(r"\b(?:full|complete)\s+resource\s+(?:review|audit|detection)\b", re.I),
        re.compile(r"\bfull\s+[`']?scontrol\s+(?:show\s+)?node\b", re.I),
        re.compile(r"(?:\buser\b|\$user).{0,40}\bsqueue\b|\bsqueue\b.{0,40}(?:\buser\b|\$user)", re.I | re.S),
        re.compile(r"/home\b.{0,60}(?:disk|storage|df)|(?:disk|storage|df).{0,60}/home\b", re.I | re.S),
    )

    for relative_path in TASK7_DOCUMENTS:
        recommended = _recommended_text(_read(relative_path))
        for pattern in forbidden_patterns:
            assert pattern.search(recommended) is None, f"{relative_path}: {pattern.pattern}"
