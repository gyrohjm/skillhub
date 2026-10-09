from __future__ import annotations

import hashlib
import json
import shutil
import sys
from copy import deepcopy
from pathlib import Path

import pytest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
CONTRACTS = Path(__file__).resolve().parents[2] / "dft-contracts"
if str(CONTRACTS) not in sys.path:
    sys.path.insert(0, str(CONTRACTS))

import canonical_workflow as cw  # noqa: E402
from dft_contracts import validate_document  # noqa: E402


def _batched_success(command):
    import resource_preflight as rp
    partition = "gpu" if "sinfo -h -p gpu " in command[2] else "compute"
    return rp.format_batched_probe_output({
        name: {"returncode": 0, "detail": partition + "|up" if name == "target_partition" else "/ok"}
        for name in rp._BATCH_NAMES
    })


def canonical_sha256(value: dict) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def approved_history(
    project: Path,
    *,
    engine: str,
    resource_profile: str,
    engine_parameters: dict,
    matrix_class: str = "production",
    execution_plan: dict | None = None,
) -> tuple[Path, str]:
    cutoff = engine_parameters.get("ENCUT", engine_parameters.get("ecutwfc"))
    kpoints = engine_parameters.get("KPOINTS")
    design = {
        "schema_version": 2,
        "design_id": "mgb2_calculation",
        "revision": 1,
        "status": "ready_for_review",
        "project_slug": "mgb2",
        "title": "MgB2 calculation",
        "research_questions": [{"id": "Q1", "question": "Is the SCF protocol converged?"}],
        "hypotheses": [
            {"id": "H1", "statement": "The protocol is converged", "falsification": "The threshold is exceeded"}
        ],
        "systems": [
            {
                "system_slug": "ref_struct",
                "model": "MgB2 reference structure",
                "structure_provenance": "project approved structure",
                "assumptions": ["periodic bulk"],
            }
        ],
        "observables": [
            {
                "id": "O1",
                "hypothesis_ids": ["H1"],
                "quantity": "total energy",
                "decision_rule": "change below threshold",
                "uncertainty_target": "1 meV/atom",
            }
        ],
        "controls": [
            {"id": "C1", "type": "baseline", "purpose": "parameter control", "fixed_or_varied": "fixed"}
        ],
        "convergence_studies": [
            {
                "id": "CV1",
                "parameter": "basis_cutoff",
                "candidate_values": [cutoff],
                "fixed_conditions": ["same occupations and k mesh"],
                "target_observable_ids": ["O1"],
                "acceptance_rule": "change below 1 meV/atom",
                "selected_value": cutoff,
            },
            {
                "id": "CV2",
                "parameter": "occupations",
                "candidate_values": ["gaussian_0.05_eV"],
                "fixed_conditions": ["same cutoff and k mesh"],
                "target_observable_ids": ["O1"],
                "acceptance_rule": "energy ordering unchanged",
                "selected_value": "gaussian_0.05_eV",
            },
            {
                "id": "CV3",
                "parameter": "kpoints",
                "candidate_values": [kpoints],
                "fixed_conditions": ["same cutoff and occupations"],
                "target_observable_ids": ["O1"],
                "acceptance_rule": "change below 1 meV/atom",
                "selected_value": kpoints,
            },
        ],
        "validation_checks": [
            {"id": "V1", "type": "independent_reference", "reference": "project plan", "acceptance_rule": "matches plan"}
        ],
        "calculation_matrix": [
            {
                "id": "M1",
                "class": matrix_class,
                "system_slug": "ref_struct",
                "case_slug": "scf",
                "hypothesis_ids": [],
                "purpose": "validated SCF",
                "variables": {},
                "fixed_parameters": {},
            "stages": ["relax", "scf"] if execution_plan is not None else ["scf"],
                "observable_ids": [],
                "completion_gate": "engine completed and converged",
            }
        ],
        "engine_stage_envelopes": [
            {
                "matrix_id": "M1",
                "engine": engine,
                "structure_source": "calculations/mgb2/refs/MgB2.cif",
                "parameter_policy": "validated",
                "kpoints_policy": "validated",
                "pseudopotential_policy": "validated",
                "resource_profile": resource_profile,
                "completion_gates": {"scf": "engine completed and converged"},
                "parameter_selection": {
                    "basis_cutoff": {
                        "status": "validated",
                        "method": "convergence test",
                        "source_metadata": {"engine": engine},
                        "candidate_values": [cutoff],
                        "units": "eV" if engine == "vasp" else "Ry",
                        "fixed_conditions": ["same occupations and k mesh"],
                        "target_observable_ids": ["O1"],
                        "acceptance_rule": "change below 1 meV/atom",
                        "selected_value": cutoff,
                        "evidence_refs": ["CV1"],
                    },
                    "occupations": {
                        "status": "validated",
                        "method": "material class and convergence",
                        "source_metadata": {"material_class": "metal", "stage": "scf"},
                        "candidate_values": ["gaussian_0.05_eV"],
                        "units": "eV",
                        "fixed_conditions": ["same cutoff and k mesh"],
                        "target_observable_ids": ["O1"],
                        "acceptance_rule": "energy ordering unchanged",
                        "selected_value": "gaussian_0.05_eV",
                        "evidence_refs": ["CV2"],
                    },
                    "kpoints": {
                        "status": "validated",
                        "method": "reciprocal spacing plus convergence",
                        "source_metadata": {"centering": "gamma", "target_spacing": "validated"},
                        "candidate_values": [kpoints],
                        "units": "1/angstrom",
                        "fixed_conditions": ["same cutoff and occupations"],
                        "target_observable_ids": ["O1"],
                        "acceptance_rule": "change below 1 meV/atom",
                        "selected_value": kpoints,
                        "evidence_refs": ["CV3"],
                    },
                },
                "engine_parameters": engine_parameters,
            }
        ],
        "evidence": [
            {
                "id": "E1",
                "claim": "project protocol",
                "source": "project plan",
                "kind": "project_record",
                "status": "verified",
                "supports": ["H1"],
            }
        ],
        "uncertainty_budget": ["1 meV/atom numerical"],
        "resource_budget": {"task_count": 1, "compute": "approved profile", "storage": "bounded"},
        "stop_conditions": ["stop when completion gate is met"],
        "pending_decisions": [],
    }
    if execution_plan is not None:
        design["execution_plan"] = deepcopy(execution_plan)
    event_id = "mgb2_calculation:r0001"
    event = {
        "history_schema_version": 1,
        "event_type": "scientific_design_approved",
        "event_id": event_id,
        "design_id": design["design_id"],
        "revision": design["revision"],
        "scope": ["M1"],
        "reviewer": "user",
        "approved_at": "2026-08-20T00:00:00+00:00",
        "design_path": "plans/mgb2/ref_struct/calculation_design.json",
        "design_sha256": canonical_sha256(design),
        "design_snapshot": design,
    }
    history = project / "plans/mgb2/ref_struct/history.jsonl"
    history.parent.mkdir(parents=True, exist_ok=True)
    history.write_text(json.dumps(event) + "\n", encoding="utf-8")
    return history, event_id


def resource_document(project: Path, profiles: dict) -> Path:
    payload = {
        "schema": "dft.project-resources.v1",
        "cluster": "test-cluster",
        "scheduler": "slurm",
        "profiles": profiles,
    }
    path = project / "docs/project-resources.md"
    path.parent.mkdir(parents=True)
    path.write_text(
        "# Project Resource Baseline\n\n"
        "<!-- dft-workflow:profiles:start -->\n"
        "```json\n"
        + json.dumps(payload, indent=2)
        + "\n```\n"
        "<!-- dft-workflow:profiles:end -->\n",
        encoding="utf-8",
    )
    return path


def vasp_profile(**overrides) -> dict:
    profile = {
        "status": "approved",
        "engine": "vasp",
        "software": "vasp-6.4.2-cpu",
        "partition": "ExampleQueue",
        "nodes": 2,
        "ntasks_per_node": 40,
        "cpus_per_task": 1,
        "modules": ["example_compiler", "example_vasp"],
        "pre_commands": ["unset I_MPI_PMI_LIBRARY", "ulimit -s unlimited"],
        "executable": "vasp_std",
        "launch_template": "srun {executable}",
        "walltime": None,
    }
    profile.update(overrides)
    return profile


def qe_profile(**overrides) -> dict:
    profile = {
        "status": "approved",
        "engine": "quantum-espresso",
        "software": "qe-7.0-avx512",
        "partition": "ExampleCPU",
        "qos": "huge",
        "nodes": 1,
        "ntasks_per_node": 112,
        "cpus_per_task": 1,
        "modules": ["example_compiler", "qe/qe-7.0-avx512"],
        "pre_commands": ["unset I_MPI_PMI_LIBRARY", "ulimit -s unlimited"],
        "executable": "pw.x",
        "launch_template": "srun {executable} -in {primary_input} > {primary_stem}.out",
        "walltime": None,
    }
    profile.update(overrides)
    return profile


def qe_source_script_profile(**overrides) -> dict:
    profile = qe_profile()
    profile.pop("modules")
    profile["environment"] = {
        "method": "source-script",
        "availability_probe": "test -r /opt/example/qe/7.2/env.sh",
        "source_command": "source /opt/example/qe/7.2/env.sh",
        "verify_command": "command -v pw.x",
        "documentation_url": "https://example.org/software",
    }
    profile.update(overrides)
    return profile


def qe_typed_module_profile(**overrides) -> dict:
    profile = qe_profile()
    modules = profile.pop("modules")
    profile["environment"] = {
        "method": "modules",
        "module_init": "source /etc/profile.d/modules.sh",
        "purge": True,
        "modules": modules,
        "availability_probe": "module avail quantum-espresso",
        "verify_command": "command -v pw.x",
        "documentation_url": "https://cluster.example/software/qe",
    }
    profile.update(overrides)
    return profile


def write_vasp_inputs(root: Path, *, encut: int = 600) -> dict[str, Path]:
    root.mkdir(parents=True)
    files = {
        "POSCAR": "Mg B\n1.0\n1 0 0\n0 1 0\n0 0 1\nMg B\n1 2\nDirect\n0 0 0\n0 0 0.3\n0 0 0.7\n",
        "INCAR": f"ENCUT = {encut}\nISMEAR = 0\nSIGMA = 0.05\nEDIFF = 1E-8\n",
        "KPOINTS": "automatic\n0\nGamma\n6 6 6\n0 0 0\n",
        "POTCAR": "TITEL = test-only Mg and B\n",
    }
    result = {}
    for name, content in files.items():
        path = root / name
        path.write_text(content, encoding="utf-8")
        result[name] = path
    return result


def two_task_execution_plan() -> dict:
    return {
        "tasks": [
            {
                "task_slug": "p1_relax",
                "matrix_id": "M1",
                "stage": "relax",
                "engine": "vasp",
                "dependencies": [],
                "inputs": [
                    {"name": "INCAR", "mode": "static", "source": "plans/mgb2/ref_struct/inputs/p1_relax/INCAR"},
                    {"name": "KPOINTS", "mode": "static", "source": "plans/mgb2/ref_struct/inputs/p1_relax/KPOINTS"},
                    {"name": "POSCAR", "mode": "static", "source": "plans/mgb2/ref_struct/inputs/p1_relax/POSCAR"},
                    {"name": "POTCAR", "mode": "static", "source": "plans/mgb2/ref_struct/inputs/p1_relax/POTCAR"},
                ],
            },
            {
                "task_slug": "p2_scf",
                "matrix_id": "M1",
                "stage": "scf",
                "engine": "vasp",
                "dependencies": ["p1_relax"],
                "inputs": [
                    {"name": "INCAR", "mode": "static", "source": "plans/mgb2/ref_struct/inputs/p2_scf/INCAR"},
                    {"name": "KPOINTS", "mode": "static", "source": "plans/mgb2/ref_struct/inputs/p2_scf/KPOINTS"},
                    {"name": "POTCAR", "mode": "static", "source": "plans/mgb2/ref_struct/inputs/p2_scf/POTCAR"},
                    {"name": "POSCAR", "mode": "recipe", "source_task": "p1_relax", "artifact": "CONTCAR"},
                ],
            },
        ]
    }


def write_two_task_inputs(project: Path) -> None:
    root = project / "plans/mgb2/ref_struct/inputs"
    p1 = root / "p1_relax"
    p2 = root / "p2_scf"
    p1.mkdir(parents=True)
    p2.mkdir(parents=True)
    contents = {
        p1 / "INCAR": "ENCUT = 600\nISMEAR = 0\nSIGMA = 0.05\nEDIFF = 1E-8\n",
        p1 / "KPOINTS": "automatic\n0\nGamma\n6 6 6\n0 0 0\n",
        p1 / "POSCAR": "Mg B\n1.0\n1 0 0\n0 1 0\n0 0 1\nMg B\n1 2\nDirect\n0 0 0\n0 0 0.3\n0 0 0.7\n",
        p1 / "POTCAR": "TITEL = test-only Mg and B\n",
        p2 / "INCAR": "ENCUT = 600\nISMEAR = 0\nSIGMA = 0.05\n",
        p2 / "KPOINTS": "automatic\n0\nGamma\n6 6 6\n0 0 0\n",
        p2 / "POTCAR": "TITEL = test-only Mg and B\n",
    }
    for path, content in contents.items():
        path.write_text(content, encoding="utf-8")


def base_project(tmp_path: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "AGENTS.md").write_text(
        "Read docs/project-resources.md before dft-workflow.\n", encoding="utf-8"
    )
    (tmp_path / "calculations").mkdir()
    return tmp_path


def submission_task_fixture(tmp_path: Path, task_slug: str = "p1_relax") -> tuple[Path, Path]:
    project = base_project(tmp_path)
    task_root = project / "calculations/mgb2/ref_struct" / task_slug
    inputs = write_vasp_inputs(task_root)
    job = "#!/usr/bin/env bash\nset -euo pipefail\nsrun vasp_std\n"
    (task_root / "job.sh").write_text(job, encoding="utf-8", newline="\n")
    design_root = project / "plans/mgb2/ref_struct"
    design_root.mkdir(parents=True)
    (design_root / "calculation_design.json").write_text("{}\n", encoding="utf-8")

    current = cw.parse_current_inputs("vasp", task_root)
    workflow = {
        "schema_version": 2,
        "contract": "dft.workflow.v2",
        "composition_slug": "mgb2",
        "structure_slug": "ref_struct",
        "task_slug": task_slug,
        "status": "prepared",
        "engine": "vasp",
        "updated_at": "2026-08-31T00:00:00+00:00",
        "design": {
            "design_id": "mgb2_calculation",
            "revision": 1,
            "approval_ref": "workspace_root:plans/mgb2/ref_struct/history.jsonl#mgb2:r0001",
            "baseline_parameter_hash": current["parameter_hash"],
            "engine_parameters": {"ENCUT": 600, "ISMEAR": 0, "SIGMA": 0.05, "KPOINTS": "6x6x6"},
        },
        "inputs": {
            "materialization": "static",
            "files": [
                {
                    "base": "task_root",
                    "path": name,
                    "name": name,
                    "role": "engine_input",
                    "mode": "static",
                    "authority": "generated",
                    "sha256": current["file_hashes"][name],
                }
                for name in inputs
            ],
        },
        "dependencies": [],
        "input_authority": {},
        "parameter_reconciliation": {
            "status": "synchronized",
            "changed_parameters": [],
            "affected_tasks": [],
        },
        "resource_profile": {
            "ref": "workspace_root:.dft/resource-profile.json#test",
            "overrides": {},
        },
        "resources": {
            "partition": "compute",
            "executable": "vasp_std",
            "activation_command": "source /opt/vasp/env.sh",
        },
        "job": {
            "script": "task_root:job.sh",
            "sha256": hashlib.sha256(job.encode("utf-8")).hexdigest(),
            "encoding": "utf-8",
            "line_endings": "lf",
        },
        "attempts": [],
        "submission": {"state": "not_submitted", "allowed": False, "job_id": None},
        "completion": {
            "scheduler_complete": False,
            "artifact_complete": False,
            "scientifically_accepted": False,
        },
        "lineage": {"derived_from": None, "supersedes": None},
        "history": [{"at": "2026-08-31T00:00:00+00:00", "status": "prepared"}],
        "input_snapshot": current,
    }
    (task_root / "workflow.json").write_text(
        json.dumps(workflow, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return project, task_root


def test_init_tree_creates_only_canonical_calculations_root(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("# Project\n", encoding="utf-8")

    calculations = cw.initialize_calculation_tree(tmp_path)

    assert calculations == tmp_path / "calculations"
    assert sorted(path.name for path in calculations.iterdir()) == ["README.md"]
    assert not (tmp_path / "raw_data").exists()


def test_initialize_cli_command_is_available() -> None:
    args = cw.build_parser().parse_args(
        [
            "initialize",
            "--project-root",
            "project",
            "--composition",
            "mgb2",
            "--structure",
            "ref_struct",
            "--history",
            "history.jsonl",
            "--event-id",
            "mgb2_calculation:r0001",
            "--resource-document",
            "resources.md",
        ]
    )

    assert args.command == "initialize"


def test_submit_cli_command_is_available() -> None:
    args = cw.build_parser().parse_args(["submit", "--task-root", "task"])

    assert args.command == "submit"
    assert args.task_root == Path("task")


def test_initialize_creates_complete_v2_task_tree_in_one_call(tmp_path: Path) -> None:
    project = base_project(tmp_path)
    execution_plan = two_task_execution_plan()
    write_two_task_inputs(project)
    history, event_id = approved_history(
        project,
        engine="vasp",
        resource_profile="nmg_vasp_2n",
        engine_parameters={"ENCUT": 600, "ISMEAR": 0, "SIGMA": 0.05, "KPOINTS": "6x6x6"},
        execution_plan=execution_plan,
    )
    resources = resource_document(project, {"nmg_vasp_2n": vasp_profile()})

    leaves = cw.initialize_workflow_tree(
        project_root=project,
        composition="mgb2",
        structure="ref_struct",
        history_path=history,
        event_id=event_id,
        resource_document=resources,
    )

    p1 = project / "calculations/mgb2/ref_struct/p1_relax"
    p2 = project / "calculations/mgb2/ref_struct/p2_scf"
    assert leaves == [p1, p2]
    assert (p1 / "job.sh").is_file()
    assert not (p2 / "job.sh").exists()
    for leaf in (p1, p2):
        workflow = json.loads((leaf / "workflow.json").read_text(encoding="utf-8"))
        assert validate_document("workflow-v2", workflow) == []
        text = json.dumps(workflow) + (leaf / "README.md").read_text(encoding="utf-8")
        assert "explicit user submission approval" not in text
        assert "not_approved" not in text

    p1_workflow = json.loads((p1 / "workflow.json").read_text(encoding="utf-8"))
    assert p1_workflow["status"] == "prepared"
    assert p1_workflow["inputs"]["materialization"] == "static"
    assert all(item["authority"] == "generated" for item in p1_workflow["inputs"]["files"])
    assert all((p1 / item["path"]).is_file() for item in p1_workflow["inputs"]["files"])

    p2_workflow = json.loads((p2 / "workflow.json").read_text(encoding="utf-8"))
    assert p2_workflow["status"] == "awaiting_upstream"
    assert p2_workflow["inputs"]["materialization"] == "mixed"
    recipe = next(item for item in p2_workflow["inputs"]["files"] if item["name"] == "POSCAR")
    assert recipe["mode"] == "recipe"
    assert recipe["source_task"] == "p1_relax"
    assert recipe["artifact"] == "CONTCAR"
    assert not (p2 / "POSCAR").exists()
    assert p2_workflow["dependencies"] == [
        {"task_ref": "p1_relax", "required_artifacts": ["CONTCAR"], "gate_status": "awaiting_upstream"}
    ]


def test_initialize_rejects_missing_static_source_without_creating_tree(tmp_path: Path) -> None:
    project = base_project(tmp_path)
    execution_plan = two_task_execution_plan()
    write_two_task_inputs(project)
    (project / "plans/mgb2/ref_struct/inputs/p2_scf/POTCAR").unlink()
    history, event_id = approved_history(
        project,
        engine="vasp",
        resource_profile="nmg_vasp_2n",
        engine_parameters={"ENCUT": 600, "ISMEAR": 0, "SIGMA": 0.05, "KPOINTS": "6x6x6"},
        execution_plan=execution_plan,
    )
    resources = resource_document(project, {"nmg_vasp_2n": vasp_profile()})

    with pytest.raises(cw.WorkflowError, match="source does not exist"):
        cw.initialize_workflow_tree(
            project_root=project,
            composition="mgb2",
            structure="ref_struct",
            history_path=history,
            event_id=event_id,
            resource_document=resources,
        )

    assert not (project / "calculations/mgb2").exists()


def test_initialize_refuses_existing_target_structure(tmp_path: Path) -> None:
    project = base_project(tmp_path)
    execution_plan = two_task_execution_plan()
    write_two_task_inputs(project)
    existing = project / "calculations/mgb2/ref_struct"
    existing.mkdir(parents=True)
    (existing / "README.md").write_text("keep", encoding="utf-8")
    history, event_id = approved_history(
        project,
        engine="vasp",
        resource_profile="nmg_vasp_2n",
        engine_parameters={"ENCUT": 600, "ISMEAR": 0, "SIGMA": 0.05, "KPOINTS": "6x6x6"},
        execution_plan=execution_plan,
    )
    resources = resource_document(project, {"nmg_vasp_2n": vasp_profile()})

    with pytest.raises(cw.WorkflowError, match="already exists") as error:
        cw.initialize_workflow_tree(
            project_root=project,
            composition="mgb2",
            structure="ref_struct",
            history_path=history,
            event_id=event_id,
            resource_document=resources,
        )

    assert (existing / "README.md").read_text(encoding="utf-8") == "keep"
    assert str(existing) in str(error.value)


def test_initialize_preserves_existing_composition_siblings(tmp_path: Path) -> None:
    project = base_project(tmp_path)
    execution_plan = two_task_execution_plan()
    write_two_task_inputs(project)
    composition = project / "calculations/mgb2"
    composition.mkdir()
    (composition / "README.md").write_text("keep composition", encoding="utf-8")
    sibling = composition / "other_structure"
    sibling.mkdir()
    (sibling / "keep.txt").write_text("keep sibling", encoding="utf-8")
    history, event_id = approved_history(
        project,
        engine="vasp",
        resource_profile="nmg_vasp_2n",
        engine_parameters={"ENCUT": 600, "ISMEAR": 0, "SIGMA": 0.05, "KPOINTS": "6x6x6"},
        execution_plan=execution_plan,
    )
    resources = resource_document(project, {"nmg_vasp_2n": vasp_profile()})

    leaves = cw.initialize_workflow_tree(
        project_root=project,
        composition="mgb2",
        structure="ref_struct",
        history_path=history,
        event_id=event_id,
        resource_document=resources,
    )

    assert leaves == [project / "calculations/mgb2/ref_struct/p1_relax", project / "calculations/mgb2/ref_struct/p2_scf"]
    assert (composition / "README.md").read_text(encoding="utf-8") == "keep composition"
    assert (sibling / "keep.txt").read_text(encoding="utf-8") == "keep sibling"


def test_initialize_rejects_missing_approved_matrix_stages_before_writing(tmp_path: Path) -> None:
    project = base_project(tmp_path)
    execution_plan = two_task_execution_plan()
    write_two_task_inputs(project)
    history, event_id = approved_history(
        project,
        engine="vasp",
        resource_profile="nmg_vasp_2n",
        engine_parameters={"ENCUT": 600, "ISMEAR": 0, "SIGMA": 0.05, "KPOINTS": "6x6x6"},
        execution_plan=execution_plan,
    )
    event = json.loads(history.read_text(encoding="utf-8"))
    design = event["design_snapshot"]
    matrix_m2 = deepcopy(design["calculation_matrix"][0])
    matrix_m2["id"] = "M2"
    matrix_m2["case_slug"] = "scf_m2"
    envelope_m2 = deepcopy(design["engine_stage_envelopes"][0])
    envelope_m2["matrix_id"] = "M2"
    design["calculation_matrix"].append(matrix_m2)
    design["engine_stage_envelopes"].append(envelope_m2)
    event["scope"] = ["M1", "M2"]
    event["design_snapshot"] = design
    event["design_sha256"] = canonical_sha256(design)
    history.write_text(json.dumps(event) + "\n", encoding="utf-8")
    resources = resource_document(project, {"nmg_vasp_2n": vasp_profile()})

    with pytest.raises(cw.WorkflowError) as error:
        cw.initialize_workflow_tree(
            project_root=project,
            composition="mgb2",
            structure="ref_struct",
            history_path=history,
            event_id=event_id,
            resource_document=resources,
        )

    message = str(error.value)
    assert "M2" in message
    assert "relax" in message
    assert "scf" in message
    assert not (project / "calculations/mgb2").exists()


def test_prepare_builds_canonical_tree_and_one_machine_state(tmp_path: Path) -> None:
    project = base_project(tmp_path)
    inputs = write_vasp_inputs(tmp_path / "source")
    history, event_id = approved_history(
        project,
        engine="vasp",
        resource_profile="nmg_vasp_2n",
        engine_parameters={
            "ENCUT": 600,
            "ISMEAR": 0,
            "SIGMA": 0.05,
            "EDIFF": 1e-8,
            "KPOINTS": "6x6x6",
        },
    )
    resources = resource_document(project, {"nmg_vasp_2n": vasp_profile()})

    leaf = cw.prepare_task(
        project_root=project,
        composition="mgb2",
        structure="ref_struct",
        task="p2_scf",
        variant=None,
        stage="scf",
        engine="vasp",
        history_path=history,
        event_id=event_id,
        matrix_id="M1",
        resource_document=resources,
        resource_profile="nmg_vasp_2n",
        staged_inputs=inputs,
        dependencies={},
        primary_input=None,
    )

    assert leaf == project / "calculations/mgb2/ref_struct/p2_scf"
    for relative in (
        "calculations/README.md",
        "calculations/mgb2/README.md",
        "calculations/mgb2/refs/README.md",
        "calculations/mgb2/ref_struct/README.md",
        "calculations/mgb2/ref_struct/scripts/README.md",
        "calculations/mgb2/ref_struct/analysis/README.md",
        "calculations/mgb2/ref_struct/failed/README.md",
        "calculations/mgb2/ref_struct/p2_scf/README.md",
        "calculations/mgb2/ref_struct/p2_scf/workflow.json",
    ):
        assert (project / relative).is_file(), relative
    forbidden = {
        "task_spec.json",
        "state.json",
        "submission.json",
        "submission_approval.json",
        "preflight.json",
        "parse.json",
    }
    assert not forbidden.intersection(path.name for path in leaf.iterdir())

    workflow = json.loads((leaf / "workflow.json").read_text(encoding="utf-8"))
    assert workflow["contract"] == "dft.workflow.v1"
    assert workflow["composition_slug"] == "mgb2"
    assert workflow["structure_slug"] == "ref_struct"
    assert workflow["task_slug"] == "p2_scf"
    assert "variant_slug" not in workflow
    assert validate_document("workflow-v1", workflow) == []
    assert workflow["design"]["approval_ref"].endswith(
        "plans/mgb2/ref_struct/history.jsonl#mgb2_calculation:r0001"
    )
    assert workflow["submission"]["state"] == "not_approved"
    assert workflow["submission"]["allowed"] is False
    assert workflow["resource_preflight"]["targeted_live_check"] == "required_before_submit"
    assert str(project) not in json.dumps(workflow)


def test_vasp_prepare_rejects_input_that_disagrees_with_approved_parameters(
    tmp_path: Path,
) -> None:
    project = base_project(tmp_path)
    inputs = write_vasp_inputs(tmp_path / "source", encut=500)
    history, event_id = approved_history(
        project,
        engine="vasp",
        resource_profile="nmg_vasp_2n",
        engine_parameters={"ENCUT": 600, "ISMEAR": 0, "SIGMA": 0.05, "KPOINTS": "6x6x6"},
    )
    resources = resource_document(project, {"nmg_vasp_2n": vasp_profile()})

    with pytest.raises(cw.WorkflowError, match="ENCUT"):
        cw.prepare_task(
            project_root=project,
            composition="mgb2",
            structure="ref_struct",
            task="p2_scf",
            variant=None,
            stage="scf",
            engine="vasp",
            history_path=history,
            event_id=event_id,
            matrix_id="M1",
            resource_document=resources,
            resource_profile="nmg_vasp_2n",
            staged_inputs=inputs,
            dependencies={},
            primary_input=None,
        )
    assert not (project / "calculations/mgb2/ref_struct/p2_scf/workflow.json").exists()


def test_qe_prepare_checks_exact_input_and_renders_selected_software(
    tmp_path: Path,
) -> None:
    project = base_project(tmp_path)
    source = tmp_path / "source"
    source.mkdir()
    qe_input = source / "scf.in"
    qe_input.write_text(
        "&CONTROL\n calculation='scf'\n/\n&SYSTEM\n ecutwfc=80\n occupations='smearing'\n smearing='mv'\n degauss=0.02\n/\n"
        "K_POINTS automatic\n12 12 12 0 0 0\n",
        encoding="utf-8",
    )
    pseudo = source / "Mg.upf"
    pseudo.write_text("test pseudo\n", encoding="utf-8")
    history, event_id = approved_history(
        project,
        engine="quantum-espresso",
        resource_profile="phoenix_qe_pw_1n",
        engine_parameters={
            "ecutwfc": 80,
            "occupations": "smearing",
            "smearing": "mv",
            "degauss": 0.02,
            "KPOINTS": "12x12x12",
        },
    )
    resources = resource_document(project, {"phoenix_qe_pw_1n": qe_profile()})

    leaf = cw.prepare_task(
        project_root=project,
        composition="mgb2",
        structure="ref_struct",
        task="p2_scf",
        variant=None,
        stage="scf",
        engine="quantum-espresso",
        history_path=history,
        event_id=event_id,
        matrix_id="M1",
        resource_document=resources,
        resource_profile="phoenix_qe_pw_1n",
        staged_inputs={"scf.in": qe_input},
        dependencies={"Mg.upf": pseudo},
        primary_input="scf.in",
    )

    job = (leaf / "job.sh").read_text(encoding="utf-8")
    assert "#SBATCH --partition=ExampleCPU" in job
    assert "#SBATCH --qos=huge" in job
    assert "#SBATCH --nodes=1" in job
    assert "#SBATCH --ntasks=112" in job
    assert "module load qe/qe-7.0-avx512" in job
    assert "srun pw.x -in scf.in > scf.out" in job
    assert "#SBATCH --time" not in job
    assert "\r" not in job
    assert not job.startswith("\ufeff")


def test_source_script_environment_is_rendered_without_module_commands(
    tmp_path: Path,
) -> None:
    project = base_project(tmp_path)
    source = tmp_path / "source"
    source.mkdir()
    qe_input = source / "scf.in"
    qe_input.write_text(
        "&SYSTEM\n ecutwfc=80\n occupations='smearing'\n smearing='mv'\n degauss=0.02\n/\n"
        "K_POINTS automatic\n12 12 12 0 0 0\n",
        encoding="utf-8",
    )
    history, event_id = approved_history(
        project,
        engine="quantum-espresso",
        resource_profile="paratera_qe_pw_1n",
        engine_parameters={
            "ecutwfc": 80,
            "occupations": "smearing",
            "smearing": "mv",
            "degauss": 0.02,
            "KPOINTS": "12x12x12",
        },
    )
    resources = resource_document(
        project, {"paratera_qe_pw_1n": qe_source_script_profile()}
    )

    leaf = cw.prepare_task(
        project_root=project,
        composition="mgb2",
        structure="ref_struct",
        task="p2_scf",
        variant=None,
        stage="scf",
        engine="quantum-espresso",
        history_path=history,
        event_id=event_id,
        matrix_id="M1",
        resource_document=resources,
        resource_profile="paratera_qe_pw_1n",
        staged_inputs={"scf.in": qe_input},
        dependencies={},
        primary_input="scf.in",
    )

    job = (leaf / "job.sh").read_text(encoding="utf-8")
    assert "source /opt/example/qe/7.2/env.sh" in job
    assert "command -v pw.x" not in job
    assert "module load" not in job
    assert job.index("source /opt/example/qe/7.2/env.sh") < job.index("srun pw.x")
    workflow = json.loads((leaf / "workflow.json").read_text(encoding="utf-8"))
    assert workflow["resources"]["environment"]["method"] == "source-script"


def test_source_script_profile_requires_explicit_source_and_verify_commands(
    tmp_path: Path,
) -> None:
    project = base_project(tmp_path)
    profile = qe_source_script_profile()
    del profile["environment"]["source_command"]
    resources = resource_document(project, {"broken": profile})

    with pytest.raises(cw.WorkflowError, match="source_command"):
        cw.load_resource_profile(project, resources, "broken", "quantum-espresso")


def test_source_script_profile_rejects_chained_shell_commands(tmp_path: Path) -> None:
    project = base_project(tmp_path)
    profile = qe_source_script_profile()
    profile["environment"]["source_command"] = (
        "source /opt/example/qe/7.2/env.sh; touch /tmp/unapproved"
    )
    resources = resource_document(project, {"unsafe": profile})

    with pytest.raises(cw.WorkflowError, match="one reviewed script"):
        cw.load_resource_profile(project, resources, "unsafe", "quantum-espresso")


def test_module_environment_records_probe_and_renders_ordered_module_loads(
    tmp_path: Path,
) -> None:
    project = base_project(tmp_path)
    resources = resource_document(
        project, {"qe_modules": qe_typed_module_profile()}
    )

    profile, _, _ = cw.load_resource_profile(
        project, resources, "qe_modules", "quantum-espresso"
    )
    job, rendered = cw.render_job_script(
        "qe_modules",
        profile,
        job_name="mgb2-scf",
        primary_input="scf.in",
    )

    assert profile["environment"]["availability_probe"] == "module avail quantum-espresso"
    assert "source /etc/profile.d/modules.sh" in job
    assert "module purge" in job
    assert job.index("module load example_compiler") < job.index(
        "module load qe/qe-7.0-avx512"
    )
    assert "command -v pw.x" not in job
    assert "source /opt/example" not in job
    assert rendered["environment"]["method"] == "modules"


def test_qe_phonon_launch_uses_selected_template_arguments() -> None:
    profile = qe_profile(
        executable="ph.x",
        launch_template="srun {executable} -pd .true. -in {primary_input} > {primary_stem}.out",
    )
    job, _ = cw.render_job_script(
        "qe_phonon", profile, job_name="mgb2-ph", primary_input="ph.in"
    )
    assert "srun ph.x -pd .true. -in ph.in > ph.out" in job

    profile["launch_template"] = "srun {executable} -in {primary_input}"
    job, _ = cw.render_job_script(
        "qe_phonon", profile, job_name="mgb2-ph", primary_input="ph.in")
    assert "srun ph.x -in ph.in" in job
    assert "-pd" not in job


def test_module_init_must_source_one_reviewed_script(tmp_path: Path) -> None:
    project = base_project(tmp_path)
    profile = qe_typed_module_profile()
    profile["environment"]["module_init"] = (
        "source /opt/example/modules/module.sh; touch /tmp/unapproved"
    )
    resources = resource_document(project, {"unsafe_modules": profile})

    with pytest.raises(cw.WorkflowError, match="module_init.*one reviewed script"):
        cw.load_resource_profile(
            project, resources, "unsafe_modules", "quantum-espresso"
        )


def test_environment_verification_must_resolve_approved_executable(
    tmp_path: Path,
) -> None:
    project = base_project(tmp_path)
    profile = qe_source_script_profile()
    profile["environment"]["verify_command"] = "true"
    resources = resource_document(project, {"unverified": profile})

    with pytest.raises(cw.WorkflowError, match="verify_command.*pw.x"):
        cw.load_resource_profile(
            project, resources, "unverified", "quantum-espresso"
        )


def test_module_name_rejects_shell_metacharacters(tmp_path: Path) -> None:
    project = base_project(tmp_path)
    profile = qe_typed_module_profile()
    profile["environment"]["modules"] = ["qe/7.3.1; touch /tmp/unapproved"]
    resources = resource_document(project, {"unsafe_module_name": profile})

    with pytest.raises(cw.WorkflowError, match="module identifier"):
        cw.load_resource_profile(
            project, resources, "unsafe_module_name", "quantum-espresso"
        )


@pytest.mark.parametrize(
    ("profile_id", "profile", "expected"),
    [
        (
            "cluster_a_vasp_2n",
            vasp_profile(partition="cpu-a", nodes=2, ntasks_per_node=40),
            ["--partition=cpu-a", "--nodes=2", "--ntasks=80", "srun vasp_std"],
        ),
        (
            "cluster_b_vasp_1n",
            vasp_profile(
                partition="cpu-b",
                nodes=1,
                ntasks_per_node=64,
                modules=["oneapi", "vasp/6.5"],
                executable="vasp_gam",
                launch_template="srun {executable}",
            ),
            ["--partition=cpu-b", "--nodes=1", "--ntasks=64", "srun vasp_gam"],
        ),
    ],
)
def test_job_script_is_driven_by_cluster_software_partition_and_node_profile(
    tmp_path: Path, profile_id: str, profile: dict, expected: list[str]
) -> None:
    project = base_project(tmp_path)
    inputs = write_vasp_inputs(tmp_path / "source")
    history, event_id = approved_history(
        project,
        engine="vasp",
        resource_profile=profile_id,
        engine_parameters={"ENCUT": 600, "ISMEAR": 0, "SIGMA": 0.05, "KPOINTS": "6x6x6"},
    )
    resources = resource_document(project, {profile_id: profile})

    leaf = cw.prepare_task(
        project_root=project,
        composition="mgb2",
        structure="ref_struct",
        task="p2_scf",
        variant=None,
        stage="scf",
        engine="vasp",
        history_path=history,
        event_id=event_id,
        matrix_id="M1",
        resource_document=resources,
        resource_profile=profile_id,
        staged_inputs=inputs,
        dependencies={},
        primary_input=None,
    )

    job = (leaf / "job.sh").read_text(encoding="utf-8")
    for text in expected:
        assert text in job


def test_prepare_rejects_unapproved_missing_or_wrong_engine_profile(tmp_path: Path) -> None:
    project = base_project(tmp_path)
    inputs = write_vasp_inputs(tmp_path / "source")
    history, event_id = approved_history(
        project,
        engine="vasp",
        resource_profile="required_profile",
        engine_parameters={"ENCUT": 600, "ISMEAR": 0, "SIGMA": 0.05, "KPOINTS": "6x6x6"},
    )
    resources = resource_document(
        project,
        {
            "required_profile": qe_profile(),
            "draft_profile": vasp_profile(status="candidate"),
        },
    )

    with pytest.raises(cw.WorkflowError, match="engine"):
        cw.prepare_task(
            project_root=project,
            composition="mgb2",
            structure="ref_struct",
            task="p2_scf",
            variant=None,
            stage="scf",
            engine="vasp",
            history_path=history,
            event_id=event_id,
            matrix_id="M1",
            resource_document=resources,
            resource_profile="required_profile",
            staged_inputs=inputs,
            dependencies={},
            primary_input=None,
        )


def test_prepare_rejects_candidate_resource_profile_before_writing(tmp_path: Path) -> None:
    project = base_project(tmp_path)
    inputs = write_vasp_inputs(tmp_path / "source")
    history, event_id = approved_history(
        project,
        engine="vasp",
        resource_profile="candidate_vasp",
        engine_parameters={"ENCUT": 600, "ISMEAR": 0, "SIGMA": 0.05, "KPOINTS": "6x6x6"},
    )
    resources = resource_document(
        project, {"candidate_vasp": vasp_profile(status="candidate")}
    )

    with pytest.raises(cw.WorkflowError, match="not approved"):
        cw.prepare_task(
            project_root=project,
            composition="mgb2",
            structure="ref_struct",
            task="p2_scf",
            variant=None,
            stage="scf",
            engine="vasp",
            history_path=history,
            event_id=event_id,
            matrix_id="M1",
            resource_document=resources,
            resource_profile="candidate_vasp",
            staged_inputs=inputs,
            dependencies={},
            primary_input=None,
        )
    assert not (project / "calculations/mgb2/ref_struct/p2_scf").exists()


def test_prepare_rejects_tampered_design_event_before_writing(tmp_path: Path) -> None:
    project = base_project(tmp_path)
    inputs = write_vasp_inputs(tmp_path / "source")
    history, event_id = approved_history(
        project,
        engine="vasp",
        resource_profile="nmg_vasp_2n",
        engine_parameters={"ENCUT": 600, "ISMEAR": 0, "SIGMA": 0.05, "KPOINTS": "6x6x6"},
    )
    event = json.loads(history.read_text(encoding="utf-8"))
    event["design_snapshot"]["engine_stage_envelopes"][0]["engine_parameters"]["ENCUT"] = 500
    history.write_text(json.dumps(event) + "\n", encoding="utf-8")
    resources = resource_document(project, {"nmg_vasp_2n": vasp_profile()})

    with pytest.raises(cw.WorkflowError, match="hash"):
        cw.prepare_task(
            project_root=project,
            composition="mgb2",
            structure="ref_struct",
            task="p2_scf",
            variant=None,
            stage="scf",
            engine="vasp",
            history_path=history,
            event_id=event_id,
            matrix_id="M1",
            resource_document=resources,
            resource_profile="nmg_vasp_2n",
            staged_inputs=inputs,
            dependencies={},
            primary_input=None,
        )
    assert not (project / "calculations/mgb2/ref_struct/p2_scf").exists()


def test_prepare_rejects_design_from_another_composition_or_structure(
    tmp_path: Path,
) -> None:
    project = base_project(tmp_path)
    inputs = write_vasp_inputs(tmp_path / "source")
    history, event_id = approved_history(
        project,
        engine="vasp",
        resource_profile="nmg_vasp_2n",
        engine_parameters={"ENCUT": 600, "ISMEAR": 0, "SIGMA": 0.05, "KPOINTS": "6x6x6"},
    )
    resources = resource_document(project, {"nmg_vasp_2n": vasp_profile()})

    with pytest.raises(cw.WorkflowError, match="plan scope"):
        cw.prepare_task(
            project_root=project,
            composition="mgb6",
            structure="other_struct",
            task="p2_scf",
            variant=None,
            stage="scf",
            engine="vasp",
            history_path=history,
            event_id=event_id,
            matrix_id="M1",
            resource_document=resources,
            resource_profile="nmg_vasp_2n",
            staged_inputs=inputs,
            dependencies={},
            primary_input=None,
        )
    assert not (project / "calculations/mgb6").exists()


def test_prepare_rejects_noncanonical_slug_and_paths_outside_workspace(tmp_path: Path) -> None:
    project = base_project(tmp_path / "project")
    outside = tmp_path / "outside.md"
    outside.write_text("not a project resource document\n", encoding="utf-8")

    with pytest.raises(cw.WorkflowError, match="slug"):
        cw.resolve_leaf(project, "MgB2", "ref_struct", "p2_scf", None)
    with pytest.raises(cw.WorkflowError, match="workspace"):
        cw.load_resource_profile(project, outside, "anything", "vasp")


def test_reconcile_before_readiness_delegates_to_input_reconciler(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    expected = {"status": "synchronized", "verdict": "ADVANCE"}
    calls: list[tuple[Path, Path, bool]] = []

    def fake_reconcile(task_root: Path, design_path: Path, *, write: bool) -> dict:
        calls.append((task_root, design_path, write))
        return expected

    monkeypatch.setattr(cw, "_reconcile_task", fake_reconcile)
    task_root = tmp_path / "task"
    design_path = tmp_path / "calculation_design.json"

    assert cw.reconcile_before_readiness(task_root, design_path) == expected
    assert calls == [(task_root, design_path, True)]


def test_submit_task_creates_immutable_snapshot_and_submits_without_second_approval(
    tmp_path: Path,
) -> None:
    project, task_root = submission_task_fixture(tmp_path)
    calls: list[tuple[str, ...]] = []

    class Result:
        def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    def runner(argv: list[str], **kwargs) -> Result:
        del kwargs
        command = tuple(argv)
        calls.append(command)
        if command[:2] == ("bash", "-lc") and "DFT_PREFLIGHT_V1" in command[2]:
            return Result(0, _batched_success(command))
        if command[:2] == ("bash", "-n"):
            return Result(0)
        if command == ("sbatch", "--parsable", "job.sh"):
            return Result(0, "12345\n")
        return Result(127, "", "unexpected command")

    job_id = cw.submit_task(task_root, runner=runner)

    assert job_id == "12345"
    assert len(calls) == 3
    assert calls[0][:2] == ("bash", "-lc") and "DFT_PREFLIGHT_V1" in calls[0][2]
    assert calls[1:] == [("bash", "-n", "job.sh"), ("sbatch", "--parsable", "job.sh")]
    snapshot = task_root / "attempts/attempt-001/submission_snapshot"
    assert all((snapshot / name).is_file() for name in ("INCAR", "KPOINTS", "POSCAR", "POTCAR", "job.sh"))
    manifest = json.loads((snapshot / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["attempt_id"] == "attempt-001"
    assert manifest["baseline_parameter_hash"]
    assert set(manifest["files"]) == {"INCAR", "KPOINTS", "POSCAR", "POTCAR", "job.sh"}
    original_snapshot_incar = (snapshot / "INCAR").read_bytes()
    (task_root / "INCAR").write_text("ENCUT = 999\n", encoding="utf-8")
    assert (snapshot / "INCAR").read_bytes() == original_snapshot_incar

    workflow = json.loads((task_root / "workflow.json").read_text(encoding="utf-8"))
    assert workflow["status"] == "submitted"
    assert workflow["submission"]["state"] == "submitted"
    assert workflow["submission"]["allowed"] is True
    assert workflow["submission"]["job_id"] == "12345"
    assert workflow["submission"]["receipt"] == (
        "task_root:attempts/attempt-001/sbatch.receipt.json"
    )
    assert workflow["attempts"][0]["attempt_id"] == "attempt-001"
    assert workflow["attempts"][0]["scheduler"]["receipt"] == (
        "task_root:attempts/attempt-001/sbatch.receipt.json"
    )


def test_submit_task_persists_sbatch_receipt_before_ledger_write_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project, task_root = submission_task_fixture(tmp_path)

    class Result:
        def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    def runner(argv: list[str], **kwargs) -> Result:
        del kwargs
        command = tuple(argv)
        if command[:2] == ("bash", "-lc") and "DFT_PREFLIGHT_V1" in command[2]:
            return Result(0, _batched_success(command))
        if command[:2] == ("bash", "-n"):
            return Result(0)
        if command == ("sbatch", "--parsable", "job.sh"):
            return Result(0, "12345\n", "scheduler warning\n")
        return Result(127, "", f"unexpected command: {command}")

    def fail_ledger_write(path: Path, workflow: dict) -> None:
        del path, workflow
        raise RuntimeError("injected ledger write failure")

    monkeypatch.setattr(cw, "_write_submission_workflow", fail_ledger_write)

    with pytest.raises(RuntimeError, match="injected ledger write failure"):
        cw.submit_task(task_root, runner=runner)

    attempt = task_root / "attempts/attempt-001"
    assert (attempt / "submission_snapshot/manifest.json").is_file()
    receipt_path = attempt / "sbatch.receipt.json"
    assert receipt_path.is_file()
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["job_id"] == "12345"
    assert receipt["argv"] == ["sbatch", "--parsable", "job.sh"]
    assert receipt["stdout"] == "12345\n"
    assert receipt["stderr"] == "scheduler warning\n"
    assert receipt["returncode"] == 0
    assert receipt["recorded_at"]

    workflow = json.loads((task_root / "workflow.json").read_text(encoding="utf-8"))
    assert workflow["status"] != "submitted"
    assert workflow["submission"]["state"] == "not_submitted"
    assert workflow["attempts"] == []


def test_submit_task_reuses_ready_project_cache_without_preflight_runner_calls(
    tmp_path: Path,
) -> None:
    project, first_task = submission_task_fixture(tmp_path)
    second_task = first_task.parent / "p2_scf"
    shutil.copytree(first_task, second_task)
    second_workflow_path = second_task / "workflow.json"
    second_workflow = json.loads(second_workflow_path.read_text(encoding="utf-8"))
    second_workflow["task_slug"] = "p2_scf"
    second_workflow_path.write_text(
        json.dumps(second_workflow, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    class Result:
        def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    first_calls: list[tuple[str, ...]] = []

    def first_runner(argv: list[str], **kwargs) -> Result:
        del kwargs
        command = tuple(argv)
        first_calls.append(command)
        if command[:2] == ("bash", "-lc") and "DFT_PREFLIGHT_V1" in command[2]:
            return Result(0, _batched_success(command))
        if command[:2] == ("bash", "-n"):
            return Result(0)
        if command == ("sbatch", "--parsable", "job.sh"):
            return Result(0, "12345\n")
        return Result(127, "", "unexpected command")

    assert cw.submit_task(first_task, runner=first_runner) == "12345"
    assert first_calls[-1] == ("sbatch", "--parsable", "job.sh")

    cached_calls: list[tuple[str, ...]] = []

    def cached_runner(argv: list[str], **kwargs) -> Result:
        del kwargs
        command = tuple(argv)
        cached_calls.append(command)
        if command[:2] == ("bash", "-n"):
            return Result(0)
        if command == ("sbatch", "--parsable", "job.sh"):
            return Result(0, "12346\n")
        raise AssertionError(f"ready cache must prevent preflight command: {command}")

    assert cw.submit_task(second_task, runner=cached_runner) == "12346"
    assert cached_calls == [("bash", "-n", "job.sh"), ("sbatch", "--parsable", "job.sh")]


def test_submit_task_revalidates_ready_cache_when_approved_profile_changes(
    tmp_path: Path,
) -> None:
    project, first_task = submission_task_fixture(tmp_path)
    second_task = first_task.parent / "p2_scf"
    shutil.copytree(first_task, second_task)
    second_workflow_path = second_task / "workflow.json"
    second_workflow = json.loads(second_workflow_path.read_text(encoding="utf-8"))
    second_workflow["task_slug"] = "p2_scf"
    second_workflow["resources"] = {
        "partition": "gpu",
        "executable": "vasp_gpu",
        "activation_command": "source /opt/vasp-gpu/env.sh",
    }
    second_workflow_path.write_text(
        json.dumps(second_workflow, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    class Result:
        def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    def first_runner(argv: list[str], **kwargs) -> Result:
        del kwargs
        command = tuple(argv)
        if command[:2] == ("bash", "-lc") and "DFT_PREFLIGHT_V1" in command[2]:
            return Result(0, _batched_success(command))
        if command[:2] == ("bash", "-n"):
            return Result(0)
        if command == ("sbatch", "--parsable", "job.sh"):
            return Result(0, "12345\n")
        return Result(127, "", f"unexpected profile-A command: {command}")

    assert cw.submit_task(first_task, runner=first_runner) == "12345"
    profile_a_cache = json.loads(
        (project / ".dft/resource-profile.json").read_text(encoding="utf-8")
    )
    assert profile_a_cache["cache_status"] == "ready"
    assert profile_a_cache["approved_profile"]["partition"] == "compute"

    profile_b_calls: list[tuple[str, ...]] = []

    def profile_b_runner(argv: list[str], **kwargs) -> Result:
        del kwargs
        command = tuple(argv)
        profile_b_calls.append(command)
        if command[:2] == ("bash", "-lc") and "DFT_PREFLIGHT_V1" in command[2]:
            return Result(0, _batched_success(command))
        if command[:2] == ("bash", "-n"):
            return Result(0)
        if command == ("sbatch", "--parsable", "job.sh"):
            return Result(0, "12346\n")
        return Result(127, "", f"unexpected profile-B command: {command}")

    assert cw.submit_task(second_task, runner=profile_b_runner) == "12346"
    assert len(profile_b_calls) == 3
    assert "sinfo -h -p gpu " in profile_b_calls[0][2]
    assert profile_b_calls[1:] == [("bash", "-n", "job.sh"), ("sbatch", "--parsable", "job.sh")]
    profile_b_cache = json.loads(
        (project / ".dft/resource-profile.json").read_text(encoding="utf-8")
    )
    assert profile_b_cache["cache_status"] == "ready"
    assert profile_b_cache["approved_profile"] == second_workflow["resources"]


def test_submit_task_preserves_sbatch_stderr_and_invalidates_cache_on_rejection(
    tmp_path: Path,
) -> None:
    project, task_root = submission_task_fixture(tmp_path)

    class Result:
        def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    calls: list[tuple[str, ...]] = []

    def runner(argv: list[str], **kwargs) -> Result:
        del kwargs
        command = tuple(argv)
        calls.append(command)
        if command[:2] == ("bash", "-lc") and "DFT_PREFLIGHT_V1" in command[2]:
            return Result(0, _batched_success(command))
        if command[:2] == ("bash", "-n"):
            return Result(0)
        if command == ("sbatch", "--parsable", "job.sh"):
            return Result(1, "", "PartitionConfig: invalid partition\n")
        return Result(127, "", "unexpected command")

    with pytest.raises(cw.WorkflowError, match="sbatch rejected"):
        cw.submit_task(task_root, runner=runner)

    attempt = task_root / "attempts/attempt-001"
    assert (attempt / "submission_snapshot/manifest.json").is_file()
    assert (attempt / "sbatch.stderr").read_text(encoding="utf-8") == (
        "PartitionConfig: invalid partition\n"
    )
    workflow = json.loads((task_root / "workflow.json").read_text(encoding="utf-8"))
    assert workflow["status"] == "failed"
    assert workflow["submission"]["state"] == "failed"
    assert workflow["submission"]["allowed"] is False
    assert workflow["submission"]["job_id"] is None
    assert workflow["technical_failure"]["code"] == "SCHEDULER_REJECTED"
    cache = json.loads(
        (project / ".dft/resource-profile.json").read_text(encoding="utf-8")
    )
    assert cache["cache_status"] == "invalidated"
    assert cache["invalidation_reason"] == "scheduler_rejection"
    assert calls[-1] == ("sbatch", "--parsable", "job.sh")


def test_submit_task_returns_agent_status_before_resource_probe_for_unknown_input(
    tmp_path: Path,
) -> None:
    _, task_root = submission_task_fixture(tmp_path)
    (task_root / "INCAR").write_text(
        (task_root / "INCAR").read_text(encoding="utf-8") + "UNKNOWN_SETTING = 1\n",
        encoding="utf-8",
    )
    calls: list[tuple[str, ...]] = []

    def runner(argv: list[str], **kwargs):
        del kwargs
        calls.append(tuple(argv))
        raise AssertionError("resource and scheduler calls must wait for Agent resolution")

    assert cw.submit_task(task_root, runner=runner) == "NEEDS_AGENT"
    assert calls == []
    assert not (task_root / "attempts").exists()


def test_submit_task_returns_agent_status_when_dependency_evidence_is_incomplete(
    tmp_path: Path,
) -> None:
    _, task_root = submission_task_fixture(tmp_path)
    workflow_path = task_root / "workflow.json"
    workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
    workflow["status"] = "awaiting_upstream"
    workflow["dependencies"] = [
        {
            "task_ref": "p0_reference",
            "required_artifacts": ["CONTCAR"],
            "gate_status": "awaiting_upstream",
        }
    ]
    workflow_path.write_text(
        json.dumps(workflow, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    calls: list[tuple[str, ...]] = []

    def runner(argv: list[str], **kwargs):
        del kwargs
        calls.append(tuple(argv))
        raise AssertionError("resource and scheduler calls must wait for upstream evidence")

    assert cw.submit_task(task_root, runner=runner) == "NEEDS_AGENT"
    assert calls == []
    assert not (task_root / "attempts").exists()


def test_submit_task_stops_for_major_reconciliation_conflict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, task_root = submission_task_fixture(tmp_path)
    monkeypatch.setattr(
        cw,
        "reconcile_before_readiness",
        lambda *args, **kwargs: {"verdict": "MAJOR_CONFLICT"},
    )

    with pytest.raises(cw.WorkflowError, match="MAJOR_CONFLICT"):
        cw.submit_task(task_root, runner=lambda *args, **kwargs: None)

    assert not (task_root / "attempts").exists()


def test_submit_task_rejects_missing_declared_input_before_snapshot(tmp_path: Path) -> None:
    _, task_root = submission_task_fixture(tmp_path)
    workflow_path = task_root / "workflow.json"
    workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
    workflow["inputs"]["files"][0]["path"] = "MISSING_INPUT"
    workflow["inputs"]["files"][0]["name"] = "MISSING_INPUT"
    workflow_path.write_text(
        json.dumps(workflow, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    with pytest.raises(cw.WorkflowError, match="missing declared input"):
        cw.submit_task(task_root, runner=lambda *args, **kwargs: None)

    assert not (task_root / "attempts").exists()


def test_submit_task_rejects_unsafe_declared_input_path(tmp_path: Path) -> None:
    _, task_root = submission_task_fixture(tmp_path)
    workflow_path = task_root / "workflow.json"
    workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
    workflow["inputs"]["files"][0]["path"] = "../outside"
    workflow["inputs"]["files"][0]["name"] = "outside"
    workflow_path.write_text(
        json.dumps(workflow, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    with pytest.raises(cw.WorkflowError, match="unsafe"):
        cw.submit_task(task_root, runner=lambda *args, **kwargs: None)

    assert not (task_root / "attempts").exists()
