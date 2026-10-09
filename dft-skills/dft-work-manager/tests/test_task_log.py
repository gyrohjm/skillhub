from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from vwm_task_log import append_task_event  # noqa: E402


def test_append_task_event_creates_scoped_readable_log(tmp_path: Path) -> None:
    workspace = tmp_path / "project"
    task = workspace / "calculations" / "mgb2" / "ref_struct" / "p1_relax" / "magmom_0"
    task.mkdir(parents=True)
    (workspace / "AGENTS.md").write_text("# Project rules\n", encoding="utf-8")
    evidence = task / "workflow.json"
    evidence.write_text("{}\n", encoding="utf-8")

    log_path = append_task_event(
        task,
        action="prepared",
        status="prepared",
        timestamp="2026-08-19T10:00:00+08:00",
        job_id="",
        evidence=[evidence],
        next_action="submit review",
    )
    append_task_event(
        task,
        action="completed",
        status="completed",
        timestamp="2026-08-19T12:00:00+08:00",
        job_id="12345",
        evidence=[evidence],
        next_action="analysis",
    )

    assert log_path == (workspace / "logs" / "mgb2" / "ref_struct.md").resolve()
    text = log_path.read_text(encoding="utf-8")
    assert "# DFT Task Log: mgb2 / ref_struct" in text
    assert "p1_relax/magmom_0" in text
    assert "prepared" in text and "completed" in text
    assert "calculations/mgb2/ref_struct/p1_relax/magmom_0/workflow.json" in text
    assert (workspace / "logs" / "README.md").is_file()
    assert (workspace / "logs" / "mgb2" / "README.md").is_file()
    task_readme = (task / "README.md").read_text(encoding="utf-8")
    assert task_readme.count("dft-work-manager:status:start") == 1
    assert task_readme.count("dft-work-manager:status:end") == 1
    assert "Event status: `completed`" in task_readme
    assert "Job ID: `12345`" in task_readme


def test_append_task_event_updates_task_structure_and_log_readmes(tmp_path: Path) -> None:
    workspace = tmp_path / "project"
    structure = workspace / "calculations" / "mgb2" / "ref_struct"
    task = structure / "p1_relax" / "magmom_0"
    task.mkdir(parents=True)
    (workspace / "AGENTS.md").write_text("# Project rules\n", encoding="utf-8")
    (structure / "README.md").write_text("# ref_struct\n\nScientific summary.\n", encoding="utf-8")
    (task / "README.md").write_text("# p1_relax/magmom_0\n\nStatus: `prepared`\n", encoding="utf-8")
    evidence = task / "workflow.json"
    evidence.write_text("{\"status\": \"prepared\"}\n", encoding="utf-8")

    append_task_event(
        task,
        action="completed",
        status="completed",
        timestamp="2026-08-19T12:00:00+08:00",
        job_id="12345",
        evidence=[evidence],
        next_action="analysis",
    )

    task_readme = (task / "README.md").read_text(encoding="utf-8")
    structure_readme = (structure / "README.md").read_text(encoding="utf-8")
    logs_readme = (workspace / "logs" / "README.md").read_text(encoding="utf-8")
    composition_logs_readme = (workspace / "logs" / "mgb2" / "README.md").read_text(encoding="utf-8")

    for text in (task_readme, structure_readme, logs_readme, composition_logs_readme):
        assert "dft-work-manager:status:start" in text
        assert "completed" in text
        assert "2026-08-19T12:00:00+08:00" in text
    assert "12345" in task_readme
    assert "calculations/mgb2/ref_struct/p1_relax/magmom_0/workflow.json" in task_readme
    assert "Scientific summary." in structure_readme
    assert "Workflow status at recording: `prepared`" in task_readme
    assert "Event status: `completed`" in task_readme


def test_append_task_event_rejects_task_outside_calculations(tmp_path: Path) -> None:
    workspace = tmp_path / "project"
    outside = tmp_path / "outside" / "task"
    outside.mkdir(parents=True)
    (workspace / "calculations").mkdir(parents=True)
    (workspace / "AGENTS.md").write_text("# Project rules\n", encoding="utf-8")

    with pytest.raises(ValueError, match="calculations"):
        append_task_event(
            outside,
            action="prepared",
            status="prepared",
            timestamp="2026-08-19T10:00:00+08:00",
            job_id="",
            evidence=[],
            next_action="review",
        )


def test_failed_task_log_keeps_original_task_identity(tmp_path: Path) -> None:
    workspace = tmp_path / "project"
    task = workspace / "calculations" / "mgb2" / "ref_struct" / "failed" / "p1_relax" / "magmom_1"
    task.mkdir(parents=True)
    (workspace / "AGENTS.md").write_text("# Project rules\n", encoding="utf-8")
    evidence = task / "workflow.json"
    evidence.write_text("{}\n", encoding="utf-8")

    log_path = append_task_event(
        task,
        action="confirmed failure",
        status="failed",
        timestamp="2026-08-19T13:00:00+08:00",
        job_id="12345",
        evidence=[evidence],
        next_action="revise magnetic setup",
    )

    text = log_path.read_text(encoding="utf-8")
    assert "| p1_relax/magmom_1 |" in text
    assert "calculations/mgb2/ref_struct/failed/p1_relax/magmom_1/workflow.json" in text


def test_task_log_renders_v2_attempt_lineage_and_user_override_without_rewriting_source(tmp_path: Path) -> None:
    workspace = tmp_path / "project"
    task = workspace / "calculations" / "mgb2" / "ref_struct" / "rerun_001"
    task.mkdir(parents=True)
    (workspace / "AGENTS.md").write_text("# Project rules\n", encoding="utf-8")
    workflow = {
        "schema_version": 2,
        "contract": "dft.workflow.v2",
        "task_slug": "p1_relax",
        "status": "completed",
        "attempts": [{"attempt_id": "attempt-001", "reason": "technical retry", "snapshot": {}}],
        "lineage": {
            "derived_from": "workspace_root:calculations/mgb2/ref_struct/p1_relax/workflow.json",
            "supersedes": None,
        },
        "input_authority": {
            "INCAR": {
                "authority": "user_override",
                "previous_sha256": "a" * 64,
                "current_sha256": "b" * 64,
            }
        },
    }
    workflow_path = task / "workflow.json"
    workflow_path.write_text(__import__("json").dumps(workflow, indent=2) + "\n", encoding="utf-8")
    (task / "INCAR").write_text("ENCUT = 600\n", encoding="utf-8")
    source_before = workflow_path.read_bytes()
    incar_before = (task / "INCAR").read_bytes()

    log_path = append_task_event(
        task,
        action="analysis complete",
        status="completed",
        timestamp="2026-08-31T12:00:00+08:00",
        job_id="12345",
        evidence=[workflow_path],
        next_action="create scientific rerun branch",
    )

    rendered = log_path.read_text(encoding="utf-8") + (task / "README.md").read_text(encoding="utf-8")
    assert "attempt-001" in rendered
    assert "rerun_001" in rendered
    assert "workspace_root:calculations/mgb2/ref_struct/p1_relax/workflow.json" in rendered
    assert "user_override" in rendered
    assert workflow_path.read_bytes() == source_before
    assert (task / "INCAR").read_bytes() == incar_before
