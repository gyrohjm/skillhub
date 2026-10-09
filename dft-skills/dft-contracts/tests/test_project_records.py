from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dft_contracts import project as p


def workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("DFT_SKILLS_CONFIG_DIR", str(tmp_path / "private"))
    root = tmp_path / "research"
    root.mkdir()
    (root / "README.md").write_text("# Human project title\n\nKeep this paragraph.\n")
    (root / "AGENTS.md").write_text("# Human rules\n\nKeep these rules.\n")
    p.init_project(root, "legacy")
    return root


def task(root, branch="p1_relax"):
    leaf = root / "calculations/mgb2/bulk" / branch
    leaf.mkdir(parents=True)
    source = Path(__file__).resolve().parents[1] / "examples/workflow-v2.example.json"
    workflow = json.loads(source.read_text())
    workflow["task_uuid"] = str(uuid4())
    (leaf / "workflow.json").write_text(json.dumps(workflow))
    return leaf


def test_memory_resume_preserves_human_text_and_reads_live_status(tmp_path, monkeypatch):
    root = workspace(tmp_path, monkeypatch)
    leaf = task(root)
    p.remember(root, "method_choice", "decision", "Use the reviewed inputs.", ["calculations/mgb2/bulk/p1_relax/workflow.json"])
    p.remember(root, "next_step", "next", "Check convergence.", [])
    memory = (root / "MEMORY.md").read_text()
    p.init_project(root, "legacy")
    assert (root / "MEMORY.md").read_text() == memory
    assert "Keep these rules." in (root / "AGENTS.md").read_text()
    assert (root / "AGENTS.md").read_text().count(p.START) == 1
    p.remember(root, "next_step", "next", "Interpret the completed run.", [])
    assert "Check convergence." not in (root / "MEMORY.md").read_text()
    assert "Use the reviewed inputs." in (root / "MEMORY.md").read_text()
    document = json.loads((leaf / "workflow.json").read_text())
    document["status"] = "completed"
    document["completion"]["scientifically_accepted"] = False
    (leaf / "workflow.json").write_text(json.dumps(document))
    text = p.project_context(root)
    assert '"status": "completed"' in text
    assert '"scientifically_accepted": false' in text
    assert "Interpret the completed run." in text
    p.sync_project(root)
    first = (root / "README.md").read_text()
    p.sync_project(root)
    assert (root / "README.md").read_text() == first
    assert "Keep this paragraph." in first
    assert p.check_project(root) == []


def test_router_separates_variants_reruns_and_refuses_clobber(tmp_path, monkeypatch):
    root = workspace(tmp_path, monkeypatch)
    leaves = [task(root, name) for name in ("p1_relax/mag_0", "p1_relax/mag_1", "rerun_001")]
    paths = [p.save_document(root, "report", "convergence", ".md", b"# Evidence\n", task_root=leaf) for leaf in leaves]
    assert len(set(paths)) == 3
    assert paths[0] == root / "calculations/mgb2/bulk/analysis/reports/p1_relax/mag_0/convergence.md"
    with pytest.raises(FileExistsError):
        p.save_document(root, "report", "convergence", ".md", b"new", task_root=leaves[0])
    assert paths[0].read_bytes() == b"# Evidence\n"
    p.save_document(root, "report", "convergence", ".md", b"updated", task_root=leaves[0], replace=True)
    assert paths[0].read_bytes() == b"updated"
    with pytest.raises(ValueError):
        p.document_path(root, "note", "Final Report", ".md")
    with pytest.raises(ValueError):
        p.artifact_path(leaves[0], "report", "../escape", ".md")
    assert p.check_project(root) == []


def test_context_and_paths_do_not_write_and_unsafe_paths_are_rejected(tmp_path, monkeypatch):
    root = workspace(tmp_path, monkeypatch)
    leaf = task(root)
    before = {str(x.relative_to(root)): x.read_bytes() for x in root.rglob('*') if x.is_file()}
    p.project_context(root)
    p.artifact_path(leaf, "data", "bands", ".dat")
    after = {str(x.relative_to(root)): x.read_bytes() for x in root.rglob('*') if x.is_file()}
    assert after == before
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "docs/link").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError):
        p.remember(root, "choice", "decision", "bad", ["docs/link/file.md"])
    (leaf.parent / "analysis").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError):
        p.artifact_path(leaf, "report", "convergence", ".md")
    assert not list(outside.iterdir())
    external = tmp_path / "external_project"
    external.mkdir()
    p.init_project(external, "legacy")
    other_task = task(external)
    linked_task = leaf.parent / "p2_alias"
    linked_task.symlink_to(other_task, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        p.task_context(linked_task)


def test_missing_evidence_private_content_and_bad_layout_are_detected(tmp_path, monkeypatch):
    root = workspace(tmp_path, monkeypatch)
    leaf = task(root)
    with pytest.raises(ValueError, match="evidence"):
        p.remember(root, "claim", "finding", "Unsupported claim", [])
    with pytest.raises(ValueError):
        p.remember(root, "claim", "finding", "Claim", ["../outside"])
    with pytest.raises(ValueError, match="private|Private"):
        p.remember(root, "environment", "next", "/home/" + "fictional_person/software", [])
    (root / "Summary Final.md").write_text("misplaced")
    (leaf / "analysis").mkdir()
    (leaf / "analysis/result.md").write_text("misplaced")
    (leaf.parent / "analysis/reports").mkdir(parents=True)
    (leaf.parent / "analysis/reports/Final Report.md").write_text("ambiguous")
    messages = p.check_project(root)
    assert any("notes belong" in m for m in messages)
    assert any("directly under" in m for m in messages)
    assert any("use analysis" in m for m in messages)
    assert (root / "Summary Final.md").exists()  # No implicit relocation.


def test_duplicate_ids_and_invalid_workflow_fail_check(tmp_path, monkeypatch):
    root = workspace(tmp_path, monkeypatch)
    first, second = task(root), task(root, "p2_scf")
    data = json.loads((first / "workflow.json").read_text())
    (second / "workflow.json").write_text(json.dumps(data))
    assert any("duplicate" in issue for issue in p.check_project(root))
    (second / "workflow.json").write_text("{")
    assert any("invalid workflow" in issue for issue in p.check_project(root))


def test_cli_handoff_in_fresh_process(tmp_path, monkeypatch):
    root = workspace(tmp_path, monkeypatch)
    leaf = task(root)
    p.remember(root, "next_step", "next", "Resume the phonon analysis.", [])
    script = Path(__file__).resolve().parents[2] / "dft-work-manager/scripts/dft_project.py"
    result = subprocess.run([sys.executable, str(script), "context", "--project-root", str(root)], capture_output=True, text=True)
    assert result.returncode == 0 and "Resume the phonon analysis." in result.stdout
    assert "p1_relax" in result.stdout


def test_parser_writes_canonical_result_without_task_local_report(tmp_path, monkeypatch):
    import shutil
    root = workspace(tmp_path, monkeypatch)
    leaf = task(root)
    skills = Path(__file__).resolve().parents[2]
    for source in (skills / "dft-analysis/tests/fixtures/vasp_scf").iterdir():
        if source.is_file():
            shutil.copy2(source, leaf / source.name)
    script = skills / "dft-analysis/scripts/parse_result.py"
    result = subprocess.run([sys.executable, str(script), "--task-dir", str(leaf), "--write"], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    expected = root / "calculations/mgb2/bulk/analysis/plot_data/p1_relax/result.json"
    assert expected.is_file() and not (leaf / "result.json").exists()
    second = subprocess.run([sys.executable, str(script), "--task-dir", str(leaf), "--write"], capture_output=True, text=True)
    assert second.returncode == 1 and "overwrite" in second.stderr
    assert p.check_project(root) == []


def test_check_reports_tracked_private_baseline_and_bad_status(tmp_path, monkeypatch):
    root = workspace(tmp_path, monkeypatch)
    leaf = task(root)
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    baseline = root / "docs/project-resources.md"
    baseline.write_text("local environment")
    subprocess.run(["git", "-C", str(root), "add", "-f", "docs/project-resources.md"], check=True)
    document = json.loads((leaf / "workflow.json").read_text())
    document["status"] = "invented_status"
    (leaf / "workflow.json").write_text(json.dumps(document))
    messages = p.check_project(root)
    assert any("Git-tracked" in message for message in messages)
    assert any("contract validation" in message for message in messages)
    assert baseline.exists()
