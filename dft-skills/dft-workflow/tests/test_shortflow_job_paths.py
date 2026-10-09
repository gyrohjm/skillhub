from __future__ import annotations

import json
from pathlib import Path

import pytest

import job_paths
import workflow_control as wc
from test_workflow_control import _workflow, _write_vasp_inputs, _write_workflow


def _write_script(root: Path, relative: str, content: str = "#!/usr/bin/env bash\ntrue\n") -> Path:
    path = root.joinpath(*relative.replace("\\", "/").split("/"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


@pytest.mark.parametrize(
    ("script_ref", "script_path"),
    [
        ("task_root:vasp.sh", "vasp.sh"),
        ("qe.sh", "qe.sh"),
    ],
)
def test_resolve_job_script_accepts_named_and_task_root_relative_paths(
    tmp_path: Path, script_ref: str, script_path: str
) -> None:
    root = tmp_path / "task"
    root.mkdir()
    expected = _write_script(root, script_path)
    workflow = {"job": {"script": script_ref}, "inputs": {"files": []}}

    assert job_paths.resolve_job_script(root, workflow) == expected.resolve()


def test_resolve_job_script_preserves_nested_script_path_and_legacy_fallback(tmp_path: Path) -> None:
    root = tmp_path / "task"
    root.mkdir()
    nested = _write_script(root, "launchers/qe.sh")

    assert job_paths.resolve_job_script(
        root,
        {"job": {"script": "task_root:launchers/qe.sh"}, "inputs": {"files": []}},
    ) == nested.resolve()

    legacy = _write_script(root, "job.sh")
    assert job_paths.resolve_job_script(root, {"inputs": {"files": []}}) == legacy.resolve()


def test_resolve_job_script_does_not_fallback_when_declared_script_is_missing(tmp_path: Path) -> None:
    root = tmp_path / "task"
    root.mkdir()
    _write_script(root, "job.sh")

    with pytest.raises(ValueError, match="missing.*job script"):
        job_paths.resolve_job_script(
            root,
            {"job": {"script": "vasp.sh"}, "inputs": {"files": []}},
        )


@pytest.mark.parametrize(
    "script_ref",
    [
        "/outside/vasp.sh",
        r"\outside\vasp.sh",
        r"C:\outside\vasp.sh",
        "../outside/vasp.sh",
        r"..\outside\vasp.sh",
        "nested/../outside/vasp.sh",
        r"task_root:nested\..\outside\vasp.sh",
    ],
)
def test_resolve_job_script_rejects_absolute_and_traversing_paths(
    tmp_path: Path, script_ref: str
) -> None:
    root = tmp_path / "task"
    root.mkdir()

    with pytest.raises(ValueError, match="unsafe"):
        job_paths.resolve_job_script(
            root,
            {"job": {"script": script_ref}, "inputs": {"files": []}},
        )


@pytest.mark.parametrize(
    ("script_ref", "input_path"),
    [
        ("workflow.json", None),
        ("task_root:workflow.json", None),
        ("INCAR", "INCAR"),
        ("task_root:launchers/qe.sh", "launchers/qe.sh"),
    ],
)
def test_resolve_job_script_rejects_reserved_workflow_and_input_collisions(
    tmp_path: Path, script_ref: str, input_path: str | None
) -> None:
    root = tmp_path / "task"
    root.mkdir()
    (root / "workflow.json").write_text("{}\n", encoding="utf-8")
    if input_path is not None:
        _write_script(root, input_path, "input\n")
    inputs = {"files": []}
    if input_path is not None:
        inputs["files"].append({"base": "task_root", "path": input_path, "name": input_path})

    with pytest.raises(ValueError, match="reserved|collid"):
        job_paths.resolve_job_script(root, {"job": {"script": script_ref}, "inputs": inputs})


def _symlink_or_skip(link: Path, target: Path, *, target_is_directory: bool) -> None:
    try:
        link.symlink_to(target, target_is_directory=target_is_directory)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")


def test_resolve_job_script_rejects_symlink_component_that_escapes_task_root(tmp_path: Path) -> None:
    root = tmp_path / "task"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    _write_script(outside, "vasp.sh")
    _symlink_or_skip(root / "launcher", outside, target_is_directory=True)

    with pytest.raises(ValueError, match="unsafe|escape"):
        job_paths.resolve_job_script(
            root,
            {"job": {"script": "launcher/vasp.sh"}, "inputs": {"files": []}},
        )


def test_archive_attempt_snapshots_declared_nested_script_not_legacy_job_sh(
    tmp_path: Path,
) -> None:
    task_root = tmp_path / "task"
    _write_vasp_inputs(task_root)
    (task_root / "job.sh").unlink()
    script = _write_script(task_root, "launchers/vasp.sh", "#!/usr/bin/env bash\nvasp\n")
    workflow = _workflow(task_root)
    workflow["job"] = {
        "script": "task_root:launchers/vasp.sh",
        "sha256": "old",
        "syntax_checked_sha256": "keep-this-metadata",
        "execution": {"launcher": "srun"},
    }
    _write_workflow(task_root, workflow)

    attempt = wc.archive_attempt(task_root, "repair nested launcher")
    manifest = json.loads((attempt / "manifest.json").read_text(encoding="utf-8"))

    assert "launchers/vasp.sh" in {item["path"] for item in manifest["files"]}
    assert not (attempt / "job.sh").exists()
    assert (attempt / "launchers/vasp.sh").read_bytes() == script.read_bytes()


def test_rerun_branch_copies_nested_declared_script_and_preserves_job_metadata(
    tmp_path: Path,
) -> None:
    task_root = tmp_path / "calculations/mgb2/bulk/p1_scf"
    _write_vasp_inputs(task_root)
    (task_root / "job.sh").unlink()
    script = _write_script(task_root, "launchers/vasp.sh", "#!/usr/bin/env bash\nvasp\n")
    (task_root / "OUTCAR").write_text("completed output\n", encoding="utf-8")
    workflow = _workflow(task_root, task_slug="p1_scf", status="completed")
    workflow["completion"] = {
        "scheduler_complete": True,
        "artifact_complete": True,
        "scientifically_accepted": False,
    }
    workflow["job"] = {
        "script": "launchers/vasp.sh",
        "sha256": "old",
        "syntax_checked_sha256": "keep-this-metadata",
        "execution": {"launcher": "srun"},
    }
    source_before = {
        path.relative_to(task_root): path.read_bytes()
        for path in task_root.rglob("*")
        if path.is_file()
    }
    _write_workflow(task_root, workflow)
    source_workflow_before = (task_root / "workflow.json").read_bytes()

    rerun = wc.create_rerun_branch(task_root, "unexpected ordering", [])
    rerun_workflow = json.loads((rerun / "workflow.json").read_text(encoding="utf-8"))

    assert (rerun / "launchers/vasp.sh").read_bytes() == script.read_bytes()
    assert not (rerun / "job.sh").exists()
    assert not (rerun / "OUTCAR").exists()
    assert rerun_workflow["job"]["script"] == "task_root:launchers/vasp.sh"
    assert rerun_workflow["job"]["sha256"]
    assert rerun_workflow["job"]["syntax_checked_sha256"] == "keep-this-metadata"
    assert rerun_workflow["job"]["execution"] == {"launcher": "srun"}
    assert (task_root / "workflow.json").read_bytes() == source_workflow_before
    assert {
        path.relative_to(task_root): path.read_bytes()
        for path in task_root.rglob("*")
        if path.is_file()
    } == source_before | {Path("workflow.json"): source_workflow_before}
