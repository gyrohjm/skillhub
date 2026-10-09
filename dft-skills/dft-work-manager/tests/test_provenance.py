from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import vwm_ledger  # noqa: E402
import vwm_archive  # noqa: E402
import vwm_provenance  # noqa: E402


def write_task(path: Path, *, encut: str = "520", resources: dict | None = None, parents: list[str] | None = None) -> None:
    path.mkdir(parents=True)
    for name, text in {"POSCAR": "structure\n", "INCAR": f"ENCUT={encut}\n", "POTCAR": "pseudo\n"}.items():
        (path / name).write_text(text, encoding="utf-8")
    spec = {
        "schema_version": 2,
        "contract": "dft.task-spec.v2",
        "engine": "vasp",
        "backend": "vwf",
        "task_kind": "scf",
        "task_dir": str(path),
        "input_hashes": {},
        "resources": resources or {"nodes": 1},
        "parent_fingerprints": parents or [],
    }
    (path / "task_spec.json").write_text(json.dumps(spec), encoding="utf-8")


def test_fingerprint_compatibility_and_cache(tmp_path: Path) -> None:
    left, right, changed = tmp_path / "left", tmp_path / "right", tmp_path / "changed"
    write_task(left, resources={"nodes": 1})
    write_task(right, resources={"nodes": 2})
    write_task(changed, encut="600")
    a = vwm_provenance.compute_fingerprint(left)
    b = vwm_provenance.compute_fingerprint(right)
    c = vwm_provenance.compute_fingerprint(changed)
    assert a["scientific"] == b["scientific"]
    assert a["exact"] != b["exact"]
    assert vwm_provenance.compatibility(a, a) == "exact_match"
    assert vwm_provenance.compatibility(a, b) == "scientifically_compatible"
    assert vwm_provenance.compatibility(a, c) == "similar_only"
    entry = vwm_provenance.cache_store(tmp_path / "cache", a, left)
    assert (entry / "cache_entry.json").is_file()
    assert vwm_provenance.cache_lookup(tmp_path / "cache", b)["match"] == "scientifically_compatible"


def test_registers_parent_child_graph(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.sqlite"
    parent_dir, child_dir = tmp_path / "parent", tmp_path / "child"
    write_task(parent_dir)
    parent_fp = vwm_provenance.compute_fingerprint(parent_dir)
    write_task(child_dir, encut="600", parents=[parent_fp["exact"]])
    vwm_ledger.init_db(ledger)
    with vwm_ledger.connect(ledger) as conn:
        vwm_ledger.register_task(conn, project="p", task="parent", source_path=str(parent_dir))
        vwm_ledger.register_task(conn, project="p", task="child", source_path=str(child_dir))
        parent = vwm_ledger.register_provenance_node(
            conn, project="p", task="parent", fingerprint=parent_fp
        )
        child_fp = vwm_provenance.compute_fingerprint(child_dir)
        child = vwm_ledger.register_provenance_node(
            conn, project="p", task="child", fingerprint=child_fp
        )
        vwm_ledger.add_provenance_edge(
            conn, parent_node_id=int(parent["id"]), child_node_id=int(child["id"])
        )
        graph = vwm_ledger.provenance_graph(conn, "p")
    assert len(graph["nodes"]) == 2
    assert graph["edges"][0]["relation"] == "depends_on"


def test_archive_chain_links_hypothesis_to_claim(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.sqlite"
    task_dir = tmp_path / "task"
    write_task(task_dir)
    archive = tmp_path / "archive"
    design_path = archive / "design/calculation_design.json"
    design_path.parent.mkdir(parents=True)
    design_path.write_text(json.dumps({
        "design_id": "sic", "revision": 1,
        "hypotheses": [{"id": "H1", "statement": "stable", "falsification": "unstable"}],
        "calculation_matrix": [{"id": "M1", "hypothesis_ids": ["H1"]}],
    }), encoding="utf-8")
    vwm_ledger.init_db(ledger)
    with vwm_ledger.connect(ledger) as conn:
        vwm_ledger.register_task(conn, project="p", task="scf", source_path=str(task_dir))
        calculation = vwm_ledger.register_provenance_node(
            conn, project="p", task="scf", fingerprint=vwm_provenance.compute_fingerprint(task_dir)
        )
        vwm_archive.register_evidence_chain(
            conn,
            project="p",
            task="scf",
            calculation_node=calculation,
            manifest={
                "engine": "vasp",
                "scientific_design": {"design_id": "sic", "design_revision": 1, "matrix_id": "M1"},
                "scientific_design_files": [{"relpath": "design/calculation_design.json"}],
                "files": [
                    {"relpath": "analysis/energy.dat", "category": "plot_data", "sha256": "a" * 64, "size": 1},
                    {"relpath": "analysis/energy.png", "category": "plot_data", "sha256": "b" * 64, "size": 1},
                ],
            },
            result={"claims": [{"statement": "SiC is stable"}], "parser": {"name": "test"}},
            archive_dir=archive,
        )
        graph = vwm_ledger.provenance_graph(conn, "p")
    assert {node["node_type"] for node in graph["nodes"]} == {
        "calculation", "hypothesis", "design_matrix", "parsed_result", "plot_data", "figure", "scientific_claim"
    }
    assert {edge["relation"] for edge in graph["edges"]} >= {
        "motivates", "authorizes", "produces", "transforms_to", "visualizes", "supports"
    }


def test_v2_workflow_provenance_renders_attempt_lineage_and_user_override(tmp_path: Path) -> None:
    task_dir = tmp_path / "calculations" / "mgb2" / "ref_struct" / "rerun_001"
    task_dir.mkdir(parents=True)
    for name, text in {
        "POSCAR": "structure\n",
        "INCAR": "ENCUT=600\n",
        "POTCAR": "pseudo\n",
    }.items():
        (task_dir / name).write_text(text, encoding="utf-8")
    workflow = {
        "schema_version": 2,
        "contract": "dft.workflow.v2",
        "composition_slug": "mgb2",
        "structure_slug": "ref_struct",
        "task_slug": "p1_relax",
        "status": "completed",
        "engine": "vasp",
        "updated_at": "2026-08-31T12:00:00+00:00",
        "design": {
            "design_id": "mgb2",
            "revision": 2,
            "approval_ref": "workspace_root:plans/mgb2/ref_struct/history.jsonl#mgb2:r0002",
            "baseline_parameter_hash": "c" * 64,
        },
        "inputs": {
            "materialization": "static",
            "files": [
                {"base": "task_root", "path": "POSCAR", "name": "POSCAR", "authority": "generated"},
                {"base": "task_root", "path": "INCAR", "name": "INCAR", "authority": "user_override"},
                {"base": "task_root", "path": "POTCAR", "name": "POTCAR", "authority": "generated"},
            ],
        },
        "dependencies": [],
        "input_authority": {
            "INCAR": {
                "authority": "user_override",
                "previous_sha256": "a" * 64,
                "current_sha256": "b" * 64,
            }
        },
        "parameter_reconciliation": {
            "status": "propagated",
            "changed_parameters": [{"name": "ENCUT", "old": 520, "new": 600, "impact": "L2"}],
            "affected_tasks": ["p2_scf"],
        },
        "resource_profile": {"ref": "workspace_root:.dft/resource-profile.json", "overrides": {}},
        "attempts": [
            {"attempt_id": "attempt-001", "reason": "technical retry", "snapshot": {"ENCUT": 520}},
            {"attempt_id": "attempt-002", "reason": "rerun", "snapshot": {"ENCUT": 600}},
        ],
        "submission": {"state": "completed", "allowed": True, "job_id": "12345"},
        "completion": {
            "scheduler_complete": True,
            "artifact_complete": True,
            "scientifically_accepted": False,
        },
        "lineage": {
            "derived_from": "workspace_root:calculations/mgb2/ref_struct/p1_relax/workflow.json",
            "supersedes": None,
        },
        "history": [],
    }
    workflow_path = task_dir / "workflow.json"
    workflow_path.write_text(json.dumps(workflow, indent=2) + "\n", encoding="utf-8")

    fingerprint = vwm_provenance.compute_fingerprint(task_dir)

    assert fingerprint["engine"] == "vasp"
    assert fingerprint["workflow"]["contract"] == "dft.workflow.v2"
    assert fingerprint["workflow"]["attempt_ids"] == ["attempt-001", "attempt-002"]
    assert fingerprint["workflow"]["lineage"]["derived_from"] == workflow["lineage"]["derived_from"]
    assert fingerprint["workflow"]["user_overrides"] == ["INCAR"]
    assert fingerprint["payloads"]["workflow"]["user_override_evidence"][0]["name"] == "INCAR"
