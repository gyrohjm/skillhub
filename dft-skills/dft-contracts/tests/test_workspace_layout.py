from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dft_contracts import (  # noqa: E402
    calculations_root,
    code_root,
    design_plan_root,
    discover_workspace,
    ensure_within,
    logs_root,
    plans_root,
    structure_log_path,
    validate_document,
)


def test_discovers_nearest_workspace_from_nested_task(tmp_path: Path) -> None:
    workspace = tmp_path / "project"
    task = workspace / "calculations" / "mgb2" / "ref_struct" / "p1_relax" / "magmom_0"
    task.mkdir(parents=True)
    (workspace / "AGENTS.md").write_text("# Project rules\n", encoding="utf-8")

    assert discover_workspace(task) == workspace.resolve()
    assert calculations_root(task) == (workspace / "calculations").resolve()


def test_workspace_discovery_does_not_guess_without_project_evidence(tmp_path: Path) -> None:
    task = tmp_path / "calculations" / "mgb2" / "ref_struct" / "p0"
    task.mkdir(parents=True)

    with pytest.raises(ValueError, match="workspace root"):
        discover_workspace(task)


def test_ensure_within_rejects_parent_escape(tmp_path: Path) -> None:
    workspace = tmp_path / "project"
    calculations = workspace / "calculations"
    calculations.mkdir(parents=True)

    assert ensure_within(calculations, calculations / "mgb2") == (calculations / "mgb2").resolve()
    with pytest.raises(ValueError, match="outside"):
        ensure_within(calculations, calculations / ".." / "docs")


def test_plans_and_logs_are_scoped_by_composition_and_structure(tmp_path: Path) -> None:
    workspace = tmp_path / "project"
    task = workspace / "calculations" / "mgb2" / "ref_struct" / "p1_relax"
    task.mkdir(parents=True)
    (workspace / "AGENTS.md").write_text("# Project rules\n", encoding="utf-8")

    assert design_plan_root(task, "mgb2", "ref_struct") == (
        workspace / "plans" / "mgb2" / "ref_struct"
    ).resolve()
    assert logs_root(task) == (workspace / "logs").resolve()
    assert plans_root(task) == (workspace / "plans").resolve()
    assert code_root(task) == (workspace / "code").resolve()
    assert structure_log_path(task, "mgb2", "ref_struct") == (
        workspace / "logs" / "mgb2" / "ref_struct.md"
    ).resolve()


def test_plan_and_log_slugs_cannot_escape_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "project"
    task = workspace / "calculations" / "mgb2" / "ref_struct" / "p0"
    task.mkdir(parents=True)
    (workspace / "AGENTS.md").write_text("# Project rules\n", encoding="utf-8")

    with pytest.raises(ValueError, match="slug"):
        design_plan_root(task, "../outside", "ref_struct")
    with pytest.raises(ValueError, match="slug"):
        structure_log_path(task, "mgb2", "../outside")


def _workflow_document() -> dict[str, object]:
    return {
        "schema_version": 1,
        "contract": "dft.workflow.v1",
        "composition_slug": "mgb2",
        "structure_slug": "ref_struct",
        "task_slug": "p1_relax",
        "variant_slug": "magmom_0",
        "status": "prepared",
        "engine": "quantum-espresso",
        "updated_at": "2026-08-19T10:00:00+08:00",
        "inputs": [
            {
                "base": "task_root",
                "path": "scf.in",
                "sha256": "a" * 64,
            },
            {
                "base": "composition_root",
                "path": "refs/pseudopotentials/Mg.UPF",
            },
        ],
        "submission": {"scheduler": "slurm", "job_id": "12345"},
        "result": {"termination": "unknown"},
    }


def test_workflow_v1_accepts_one_lightweight_leaf_record() -> None:
    assert validate_document("workflow-v1", _workflow_document()) == []


def test_checked_in_workflow_example_is_valid() -> None:
    import json

    example = json.loads(
        (ROOT / "examples" / "workflow-v1.example.json").read_text(encoding="utf-8")
    )
    assert validate_document("workflow-v1", example) == []


@pytest.mark.parametrize(
    "bad_path",
    [
        "/home/user/project/scf.in",
        "C:/project/scf.in",
        "../sibling/scf.in",
        "inputs/../../outside",
    ],
)
def test_workflow_v1_rejects_absolute_and_parent_paths(bad_path: str) -> None:
    workflow = _workflow_document()
    workflow["inputs"] = [{"base": "task_root", "path": bad_path}]

    assert validate_document("workflow-v1", workflow)
