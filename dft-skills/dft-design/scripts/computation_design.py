#!/usr/bin/env python3
"""Bootstrap, validate, approve, and verify compact DFT design records."""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping


SKILL_ROOT = Path(__file__).resolve().parents[1]
CONTRACTS_ROOT = SKILL_ROOT.parent / "dft-contracts"
if str(CONTRACTS_ROOT) not in sys.path:
    sys.path.insert(0, str(CONTRACTS_ROOT))
from dft_contracts import design_plan_root, discover_workspace, validate_document
from dft_contracts.core import sha256_json as canonical_json_sha256
from dft_contracts.layout import plan_readme_path, route_for

ASSET_DIR = SKILL_ROOT / "assets"
SLUG_RE = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")
TASK_SLUG_RE = re.compile(r"^(?:p[0-9]+|[0-9]{2,})(?:_[a-z0-9][a-z0-9_-]*)?$")
README_SYNC_RE = re.compile(r"<!--\s*dft-design-sync:\s*(\{.*?\})\s*-->")
SUMMARY_START = "<!-- dft-design-summary:start -->"
SUMMARY_END = "<!-- dft-design-summary:end -->"
STATUSES = {"draft", "ready_for_review", "superseded"}
TASK_CLASSES = {"exploratory", "convergence", "validation", "production"}
EVIDENCE_STATUSES = {"verified", "pending"}
PARAMETER_STATUSES = {"pending", "candidate", "validated"}
TASK_PARAMETER_STATUS = "user_specified"
DESIGN_MODES = {"task", "research"}
REQUIRED_PARAMETER_SELECTIONS = ("basis_cutoff", "occupations", "kpoints")
PARAMETER_SELECTION_FIELDS = (
    "status",
    "method",
    "source_metadata",
    "candidate_values",
    "units",
    "fixed_conditions",
    "target_observable_ids",
    "acceptance_rule",
    "selected_value",
    "evidence_refs",
)
SUPPORTED_SCHEMA_VERSIONS = {1, 2}
KNOWN_ENGINES = {"vasp", "quantum-espresso", "cp2k", "abinit", "gpaw", "other"}
DOMAIN_PACKS = {"defects-surfaces-interfaces", "migration-neb", "phonon-thermodynamics"}
DSI_PACK = "defects-surfaces-interfaces"
DSI_STAGES = {
    "bulk_reference",
    "defect_relax",
    "surface_relax",
    "adsorption_relax",
    "interface_relax",
    "static_energy",
    "charge_density",
    "locpot",
    "bader",
}
DSI_LOCK_REQUIRED = {
    "k_mesh",
    "smearing",
    "dipole_correction",
    "charge_state",
    "chemical_potential",
    "finite_size_correction",
    "reference_structure",
}
EXECUTION_RESERVED_NAMES = {
    "README.md",
    "workflow.json",
    "job.sh",
    "task_spec.json",
    "state.json",
    "submission.json",
    "submission_approval.json",
    "preflight.json",
    "parse.json",
}

TOP_LEVEL_FIELDS = {
    "schema_version": int,
    "design_id": str,
    "revision": int,
    "status": str,
    "project_slug": str,
    "title": str,
    "research_questions": list,
    "hypotheses": list,
    "systems": list,
    "observables": list,
    "controls": list,
    "convergence_studies": list,
    "validation_checks": list,
    "calculation_matrix": list,
    "evidence": list,
    "uncertainty_budget": list,
    "resource_budget": dict,
    "stop_conditions": list,
    "pending_decisions": list,
}

TASK_TOP_LEVEL_FIELDS = {
    "schema_version": int,
    "design_id": str,
    "revision": int,
    "status": str,
    "project_slug": str,
    "title": str,
    "systems": list,
    "calculation_matrix": list,
    "stop_conditions": list,
    "pending_decisions": list,
}

RESEARCH_OPTIONAL_FIELD_TYPES = {
    field: expected_type
    for field, expected_type in TOP_LEVEL_FIELDS.items()
    if field not in TASK_TOP_LEVEL_FIELDS
}


def engine_envelopes(design: dict[str, Any]) -> list[Any]:
    """Return schema-v2 envelopes or adapt schema-v1 VASP envelopes in memory."""
    current = design.get("engine_stage_envelopes")
    if isinstance(current, list):
        return current
    legacy = design.get("vasp_stage_envelopes")
    if not isinstance(legacy, list):
        return []
    adapted: list[Any] = []
    for item in legacy:
        if not isinstance(item, dict):
            adapted.append(item)
            continue
        adapted.append(
            {
                "matrix_id": item.get("matrix_id"),
                "engine": "vasp",
                "structure_source": item.get("structure_source"),
                "parameter_policy": item.get("incar_policy"),
                "kpoints_policy": item.get("kpoints_policy"),
                "pseudopotential_policy": item.get("potcar_labels"),
                "resource_profile": item.get("resource_profile"),
                "completion_gates": item.get("completion_gates"),
                "engine_parameters": {"legacy_schema": "vasp_stage_envelopes"},
            }
        )
    return adapted


class DesignError(ValueError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise DesignError(f"file does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise DesignError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise DesignError(f"JSON root must be an object: {path}")
    return value


def has_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def is_placeholder(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    normalized = value.strip().upper()
    return (
        normalized in {"TBD", "TODO", "UNKNOWN", "PENDING", "待补充", "待定", "未知"}
        or normalized.startswith("TBD ")
        or normalized.startswith("待补充")
    )


def placeholder_paths(value: Any, prefix: str = "") -> list[str]:
    found: list[str] = []
    if is_placeholder(value):
        found.append(prefix or "<root>")
    elif isinstance(value, dict):
        for key, item in value.items():
            found.extend(placeholder_paths(item, f"{prefix}.{key}" if prefix else str(key)))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(placeholder_paths(item, f"{prefix}[{index}]"))
    return found


def require_fields(item: Any, fields: tuple[str, ...], path: str, errors: list[str]) -> None:
    if not isinstance(item, dict):
        errors.append(f"{path} must be an object")
        return
    for field in fields:
        if field not in item:
            errors.append(f"{path}.{field} is required")
        elif isinstance(item[field], str) and not item[field].strip():
            errors.append(f"{path}.{field} must not be empty")


def collect_ids(items: Any, path: str, errors: list[str]) -> set[str]:
    result: set[str] = set()
    if not isinstance(items, list):
        return result
    for index, item in enumerate(items):
        if not isinstance(item, dict) or not has_text(item.get("id")):
            continue
        item_id = item["id"]
        if item_id in result:
            errors.append(f"{path}[{index}].id duplicates {item_id!r}")
        result.add(item_id)
    return result


def validate_parameter_selection(
    envelope: dict[str, Any],
    envelope_index: int,
    observable_ids: set[str],
    evidence_refs: set[str],
    errors: list[str],
    mode: str = "research",
) -> None:
    base = f"engine_stage_envelopes[{envelope_index}].parameter_selection"
    selection = envelope.get("parameter_selection")
    if not isinstance(selection, dict):
        errors.append(f"{base} is required and must be an object")
        return

    for category in REQUIRED_PARAMETER_SELECTIONS:
        path = f"{base}.{category}"
        entry = selection.get(category)
        if not isinstance(entry, dict):
            errors.append(f"{path} is required and must be an object")
            continue
        status = entry.get("status")
        if mode == "task" and status == TASK_PARAMETER_STATUS:
            require_fields(
                entry,
                ("status", "method", "source_metadata", "selected_value"),
                path,
                errors,
            )
            if not has_meaningful_value(entry.get("method")):
                errors.append(f"{path}.method must record how the value was supplied")
            source_metadata = entry.get("source_metadata")
            if not isinstance(source_metadata, dict) or not source_metadata:
                errors.append(f"{path}.source_metadata must be a non-empty object")
            elif placeholder_paths(source_metadata):
                errors.append(f"{path}.source_metadata must not contain placeholders")
            if not has_meaningful_value(entry.get("selected_value")):
                errors.append(f"{path}.selected_value is required for user_specified status")

            for field in (
                "candidate_values",
                "fixed_conditions",
                "target_observable_ids",
                "evidence_refs",
            ):
                if field not in entry:
                    continue
                value = entry[field]
                if not isinstance(value, list):
                    errors.append(f"{path}.{field} must be a list when provided")
                    continue
                if field == "target_observable_ids" and not set(value).issubset(observable_ids):
                    errors.append(f"{path}.target_observable_ids contains unknown IDs")
                if field == "evidence_refs" and not set(value).issubset(evidence_refs):
                    errors.append(f"{path}.evidence_refs contains unknown IDs")
            if "units" in entry and not has_text(entry.get("units")):
                errors.append(f"{path}.units must not be empty when provided")
            if "acceptance_rule" in entry and not has_meaningful_value(entry.get("acceptance_rule")):
                errors.append(f"{path}.acceptance_rule must not be empty when provided")
            continue
        if mode == "task" and status != "validated":
            require_fields(
                entry,
                ("status", "method", "source_metadata", "selected_value"),
                path,
                errors,
            )
            errors.append(
                f"{path}.status must be one of [{TASK_PARAMETER_STATUS!r}, 'validated']"
            )
            continue
        require_fields(entry, PARAMETER_SELECTION_FIELDS, path, errors)

        if status not in PARAMETER_STATUSES:
            errors.append(f"{path}.status must be one of {sorted(PARAMETER_STATUSES)}")
        source_metadata = entry.get("source_metadata")
        if not isinstance(source_metadata, dict) or not source_metadata:
            errors.append(f"{path}.source_metadata must be a non-empty object")
        candidates = entry.get("candidate_values")
        if not isinstance(candidates, list) or not candidates:
            errors.append(f"{path}.candidate_values must be a non-empty list")
        fixed = entry.get("fixed_conditions")
        if not isinstance(fixed, list) or not fixed:
            errors.append(f"{path}.fixed_conditions must be a non-empty list")
        targets = entry.get("target_observable_ids")
        if not isinstance(targets, list) or not targets:
            errors.append(f"{path}.target_observable_ids must be a non-empty list")
        elif not set(targets).issubset(observable_ids):
            errors.append(f"{path}.target_observable_ids contains unknown IDs")
        refs = entry.get("evidence_refs")
        if not isinstance(refs, list):
            errors.append(f"{path}.evidence_refs must be a list")
            refs = []
        elif not set(refs).issubset(evidence_refs):
            errors.append(f"{path}.evidence_refs contains unknown IDs")

        selected = entry.get("selected_value")
        if status == "validated":
            if not has_meaningful_value(selected):
                errors.append(f"{path}.selected_value is required when status is validated")
            elif isinstance(candidates, list) and selected not in candidates:
                errors.append(f"{path}.selected_value must be one of candidate_values")
            if not refs:
                errors.append(f"{path}.evidence_refs must not be empty when status is validated")


def lower_tokens(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value.lower()]
    if isinstance(value, dict):
        tokens: list[str] = []
        for key, item in value.items():
            tokens.append(str(key).lower())
            tokens.extend(lower_tokens(item))
        return tokens
    if isinstance(value, list):
        tokens = []
        for item in value:
            tokens.extend(lower_tokens(item))
        return tokens
    if value is None:
        return []
    return [str(value).lower()]


def has_meaningful_value(value: Any) -> bool:
    if is_placeholder(value):
        return False
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict)):
        return bool(value)
    return True


def has_reference_case(metadata: dict[str, Any], matrices: list[Any]) -> bool:
    reference_cases = metadata.get("reference_cases")
    if isinstance(reference_cases, dict):
        if has_meaningful_value(reference_cases.get("bulk_reference")):
            return True
        if has_meaningful_value(reference_cases.get("reference_structure")):
            return True
    if isinstance(reference_cases, list) and any("bulk_reference" in str(item) for item in reference_cases):
        return True
    for item in matrices:
        if not isinstance(item, dict):
            continue
        texts = lower_tokens([item.get("id"), item.get("case_slug"), item.get("purpose"), item.get("stages")])
        if any("bulk_reference" in text for text in texts):
            return True
    return False


def dsi_model_family(design: dict[str, Any], metadata: dict[str, Any]) -> set[str]:
    tokens = lower_tokens(metadata)
    tokens.extend(lower_tokens(design.get("calculation_matrix", [])))
    joined = " ".join(tokens)
    families: set[str] = set()
    if any(key in joined for key in ("defect", "vacancy", "substitution", "charge_state")):
        families.add("defect")
    if any(key in joined for key in ("surface", "slab", "miller", "adsorption", "adsorbate", "interface")):
        families.add("slab")
    return families or {"defect", "slab"}


def convergence_parameters(design: dict[str, Any]) -> str:
    values = []
    for item in design.get("convergence_studies", []):
        if isinstance(item, dict):
            values.append(item.get("parameter"))
    return " ".join(lower_tokens(values))


def validate_dsi_domain(design: dict[str, Any], errors: list[str]) -> None:
    metadata = design.get("domain_metadata")
    if not isinstance(metadata, dict) or not metadata:
        errors.append("domain_metadata must be a non-empty object for defects-surfaces-interfaces")
        return
    matrices = design.get("calculation_matrix", [])
    if not has_reference_case(metadata, matrices):
        errors.append("defects-surfaces-interfaces requires reference_cases.bulk_reference or a bulk_reference matrix")

    control_tokens = lower_tokens(design.get("controls", []))
    if not any(
        token in " ".join(control_tokens)
        for token in ("baseline", "reference", "control", "clean_slab", "bulk_reference")
    ):
        errors.append("defects-surfaces-interfaces requires a baseline/reference control")

    families = dsi_model_family(design, metadata)
    required_convergence: dict[str, tuple[str, ...]] = {
        "basis_cutoff": ("basis_cutoff", "encut", "ecutwfc", "cutoff"),
        "k_mesh": ("k_mesh", "kpoints", "k-point", "k mesh"),
        "smearing": ("smearing", "ismear", "sigma"),
    }
    if "defect" in families:
        required_convergence["supercell_size"] = ("supercell",)
    if "slab" in families:
        required_convergence["slab_size"] = ("slab",)
        required_convergence["vacuum"] = ("vacuum",)
    convergence_text = convergence_parameters(design)
    missing_convergence = [
        key for key, aliases in sorted(required_convergence.items())
        if not any(alias in convergence_text for alias in aliases)
    ]
    if missing_convergence:
        errors.append(
            "defects-surfaces-interfaces missing convergence coverage for: "
            + ", ".join(missing_convergence)
        )

    production_lock = metadata.get("production_lock")
    if not isinstance(production_lock, dict):
        errors.append("domain_metadata.production_lock must record locked production parameters")
        return
    required_lock = set(DSI_LOCK_REQUIRED)
    if "defect" in families:
        required_lock.add("supercell_size")
    if "slab" in families:
        required_lock.update({"slab_size", "vacuum"})
    missing_lock = [
        key for key in sorted(required_lock)
        if not has_meaningful_value(production_lock.get(key))
    ]
    if not any(
        has_meaningful_value(production_lock.get(key))
        for key in ("basis_cutoff", "ENCUT", "ecutwfc", "cutoff")
    ):
        missing_lock.append("basis_cutoff")
    if missing_lock:
        errors.append(
            "domain_metadata.production_lock missing values for: "
            + ", ".join(missing_lock)
        )


def validate_neb_domain(design: dict[str, Any], errors: list[str]) -> None:
    metadata = design.get("domain_metadata")
    if not isinstance(metadata, dict):
        errors.append("migration-neb requires domain_metadata")
        return
    required = (
        "initial_state", "final_state", "image_count", "interpolation_method",
        "climbing_image", "force_threshold_eV_per_A",
    )
    for key in required:
        if not has_meaningful_value(metadata.get(key)):
            errors.append(f"migration-neb domain_metadata.{key} is required")
    image_count = metadata.get("image_count")
    if image_count is not None and (not isinstance(image_count, int) or isinstance(image_count, bool) or image_count < 3):
        errors.append("migration-neb domain_metadata.image_count must be an integer >= 3")
    threshold = metadata.get("force_threshold_eV_per_A")
    if threshold is not None and (not isinstance(threshold, (int, float)) or isinstance(threshold, bool) or threshold <= 0):
        errors.append("migration-neb domain_metadata.force_threshold_eV_per_A must be positive")


def validate_phonon_domain(design: dict[str, Any], errors: list[str]) -> None:
    metadata = design.get("domain_metadata")
    if not isinstance(metadata, dict):
        errors.append("phonon-thermodynamics requires domain_metadata")
        return
    method = metadata.get("method")
    if method not in {"finite_displacement", "dfpt"}:
        errors.append("phonon-thermodynamics domain_metadata.method must be finite_displacement or dfpt")
    mesh_key = "supercell" if method == "finite_displacement" else "q_mesh"
    mesh = metadata.get(mesh_key)
    if not (
        isinstance(mesh, list) and len(mesh) == 3
        and all(isinstance(value, int) and not isinstance(value, bool) and value > 0 for value in mesh)
    ):
        errors.append(f"phonon-thermodynamics domain_metadata.{mesh_key} must be three positive integers")
    tolerance = metadata.get("imaginary_frequency_tolerance_cm1")
    if not isinstance(tolerance, (int, float)) or isinstance(tolerance, bool) or tolerance < 0:
        errors.append("phonon-thermodynamics domain_metadata.imaginary_frequency_tolerance_cm1 must be non-negative")
    if method == "finite_displacement":
        distance = metadata.get("displacement_distance_A")
        if not isinstance(distance, (int, float)) or isinstance(distance, bool) or distance <= 0:
            errors.append("phonon-thermodynamics domain_metadata.displacement_distance_A must be positive")


def _execution_safe_relative_path(value: Any, label: str, errors: list[str]) -> None:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{label} must be a safe relative path")
        return
    path = value.strip()
    parts = path.split("/")
    if (
        path != value
        or path.startswith(("/", "\\"))
        or re.match(r"^[A-Za-z]:", path)
        or "\\" in path
        or "\x00" in path
        or any(part in {"", ".", ".."} for part in parts)
        or re.search(r"[:<>|\"?*]", path)
    ):
        errors.append(f"{label} must be a safe relative path")


def _execution_safe_leaf_name(value: Any, label: str, errors: list[str]) -> None:
    if (
        not isinstance(value, str)
        or not value.strip()
        or value != value.strip()
        or value in {".", ".."}
        or "/" in value
        or "\\" in value
        or re.search(r"[:<>|\"?*\x00]", value)
        or value in EXECUTION_RESERVED_NAMES
    ):
        errors.append(f"{label} must be one safe leaf filename")


def validate_execution_plan(
    design: Mapping[str, Any],
    *,
    required_matrix_ids: Iterable[str] | None = None,
) -> list[str]:
    """Validate the explicit task DAG used by canonical initialization.

    When ``required_matrix_ids`` is supplied, it is the approval scope and
    determines which approved matrices must have every approved stage present.
    """

    errors: list[str] = []
    execution_plan = design.get("execution_plan")
    if not isinstance(execution_plan, Mapping):
        return ["execution_plan must be an object"]
    tasks = execution_plan.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        return ["execution_plan.tasks must be a non-empty list"]

    raw_matrices = design.get("calculation_matrix", [])
    matrices = {
        item.get("id"): item
        for item in (raw_matrices if isinstance(raw_matrices, list) else [])
        if isinstance(item, Mapping) and has_text(item.get("id"))
    }
    envelopes = {
        item.get("matrix_id"): item
        for item in engine_envelopes(dict(design))
        if isinstance(item, Mapping) and has_text(item.get("matrix_id"))
    }
    task_by_slug: dict[str, Mapping[str, Any]] = {}
    task_index_by_slug: dict[str, int] = {}
    dependency_graph: dict[str, list[str]] = {}
    stage_pairs: set[tuple[str, str]] = set()

    for index, raw_task in enumerate(tasks):
        path = f"execution_plan.tasks[{index}]"
        if not isinstance(raw_task, Mapping):
            errors.append(f"{path} must be an object")
            continue
        task = raw_task
        for field in ("task_slug", "matrix_id", "stage", "engine", "dependencies", "inputs"):
            if field not in task:
                errors.append(f"{path}.{field} is required")

        if "directory" in task:
            _execution_safe_relative_path(task["directory"], f"{path}.directory", errors)
        if "job_script" in task:
            _execution_safe_relative_path(task.get("job_script"), f"{path}.job_script", errors)

        task_slug = task.get("task_slug")
        if not isinstance(task_slug, str) or not TASK_SLUG_RE.fullmatch(task_slug):
            errors.append(f"{path}.task_slug must use pN[_name] lowercase format")
        elif task_slug in task_by_slug:
            errors.append(f"{path}.task_slug duplicates {task_slug!r}")
        else:
            task_by_slug[task_slug] = task
            task_index_by_slug[task_slug] = index

        matrix_id = task.get("matrix_id")
        stage = task.get("stage")
        matrix = matrices.get(matrix_id)
        if matrix is None:
            errors.append(f"{path}.matrix_id references unknown matrix {matrix_id!r}")
        elif not isinstance(matrix.get("stages"), list) or not isinstance(stage, str) or stage not in matrix.get("stages", []):
            errors.append(f"{path}.stage {stage!r} is not approved for matrix {matrix_id!r}")
        elif (matrix_id, stage) in stage_pairs:
            errors.append(f"{path} duplicates matrix/stage pair {matrix_id!r}/{stage!r}")
        else:
            stage_pairs.add((matrix_id, stage))

        engine = task.get("engine")
        if engine not in KNOWN_ENGINES:
            errors.append(f"{path}.engine must be one of {sorted(KNOWN_ENGINES)}")
        envelope = envelopes.get(matrix_id)
        if envelope is None:
            errors.append(f"{path}.matrix_id has no engine envelope")
        elif engine != envelope.get("engine"):
            errors.append(
                f"{path}.engine {engine!r} does not match approved matrix envelope {envelope.get('engine')!r}"
            )

        dependencies = task.get("dependencies")
        if not isinstance(dependencies, list):
            errors.append(f"{path}.dependencies must be a list")
            dependencies = []
        graph_key = task_slug if isinstance(task_slug, str) else f"<task-{index}>"
        dependency_graph[graph_key] = dependency_graph.get(graph_key, [])
        seen_dependencies: set[str] = set()
        for dep_index, dependency in enumerate(dependencies):
            dep_path = f"{path}.dependencies[{dep_index}]"
            if not isinstance(dependency, str) or not dependency.strip():
                errors.append(f"{dep_path} must name a task")
                continue
            if dependency in seen_dependencies:
                errors.append(f"{dep_path} duplicates dependency {dependency!r}")
            seen_dependencies.add(dependency)
            if dependency == task_slug:
                errors.append(f"{dep_path} cannot depend on itself")
            dependency_graph.setdefault(graph_key, []).append(dependency)

        inputs = task.get("inputs")
        if not isinstance(inputs, list) or not inputs:
            errors.append(f"{path}.inputs must be a non-empty list")
            inputs = []
        seen_names: set[str] = set()
        for input_index, raw_input in enumerate(inputs):
            input_path = f"{path}.inputs[{input_index}]"
            if not isinstance(raw_input, Mapping):
                errors.append(f"{input_path} must be an object")
                continue
            name = raw_input.get("name")
            _execution_safe_leaf_name(name, f"{input_path}.name", errors)
            if isinstance(name, str):
                if name in seen_names:
                    errors.append(f"{input_path}.name duplicates {name!r}")
                seen_names.add(name)
            mode = raw_input.get("mode")
            if mode not in {"static", "recipe"}:
                errors.append(f"{input_path}.mode must be static or recipe")
                continue
            if mode == "static":
                if "source" not in raw_input:
                    errors.append(f"{input_path}.source is required for static input")
                else:
                    _execution_safe_relative_path(raw_input.get("source"), f"{input_path}.source", errors)
                if "source_task" in raw_input or "artifact" in raw_input:
                    errors.append(f"{input_path} static and recipe fields are mutually exclusive")
            else:
                if "source" in raw_input:
                    errors.append(f"{input_path} recipe and static fields are mutually exclusive")
                source_task = raw_input.get("source_task")
                if not isinstance(source_task, str) or not source_task.strip():
                    errors.append(f"{input_path}.source_task is required for recipe input")
                elif source_task == task_slug:
                    errors.append(f"{input_path}.source_task cannot be the current task")
                elif source_task not in dependencies:
                    errors.append(
                        f"{input_path}.source_task must be a declared dependency"
                    )
                artifact = raw_input.get("artifact")
                if "artifact" not in raw_input:
                    errors.append(f"{input_path}.artifact is required for recipe input")
                else:
                    _execution_safe_relative_path(artifact, f"{input_path}.artifact", errors)

    for task_slug, task in task_by_slug.items():
        for dependency in dependency_graph.get(task_slug, []):
            if dependency not in task_by_slug:
                errors.append(
                    f"execution_plan.tasks[{task_index_by_slug[task_slug]}].dependencies references unknown dependency {dependency!r}"
                )

    visit_state: dict[str, int] = {}

    def visit(task_slug: str) -> None:
        state = visit_state.get(task_slug, 0)
        if state == 1:
            errors.append(f"execution_plan dependency cycle detected at {task_slug!r}")
            return
        if state == 2:
            return
        visit_state[task_slug] = 1
        for dependency in dependency_graph.get(task_slug, []):
            if dependency in task_by_slug:
                visit(dependency)
        visit_state[task_slug] = 2

    for task_slug in task_by_slug:
        visit(task_slug)

    if required_matrix_ids is None:
        required_ids = {matrix_id for matrix_id, _ in stage_pairs}
    else:
        required_ids: set[str] = set()
        for matrix_id in required_matrix_ids:
            if not isinstance(matrix_id, str) or not matrix_id.strip():
                errors.append("approval scope matrix IDs must be non-empty strings")
                continue
            required_ids.add(matrix_id)
    for matrix_id in sorted(required_ids):
        matrix = matrices.get(matrix_id, {})
        if not matrix:
            errors.append(
                f"execution_plan approval scope references unknown matrix {matrix_id!r}"
            )
            continue
        approved_stages = matrix.get("stages", []) if isinstance(matrix, Mapping) else []
        if not isinstance(approved_stages, list):
            continue
        planned_stages = {stage for pair_matrix, stage in stage_pairs if pair_matrix == matrix_id}
        for stage in approved_stages:
            if stage not in planned_stages:
                errors.append(
                    f"execution_plan is missing a task entry for approved stage {stage!r} of matrix {matrix_id!r}"
                )
    return errors


def validate_design(design: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    mode = design.get("design_mode", "research")
    if "design_mode" in design:
        if not isinstance(mode, str) or mode not in DESIGN_MODES:
            errors.append(f"design_mode must be one of {sorted(DESIGN_MODES)}")
            mode = "research"

    required_fields = TOP_LEVEL_FIELDS if mode == "research" else TASK_TOP_LEVEL_FIELDS
    for field, expected_type in required_fields.items():
        if field not in design:
            errors.append(f"{field} is required")
        elif not isinstance(design[field], expected_type) or (
            expected_type is int and isinstance(design[field], bool)
        ):
            errors.append(f"{field} must be {expected_type.__name__}")

    if mode == "task":
        if design.get("schema_version") != 2:
            errors.append("design_mode task requires schema_version 2")
        if "execution_plan" not in design:
            errors.append("execution_plan is required for task mode")
        elif not isinstance(design["execution_plan"], Mapping):
            errors.append("execution_plan must be an object for task mode")
        for field, expected_type in RESEARCH_OPTIONAL_FIELD_TYPES.items():
            if field in design and not isinstance(design[field], expected_type):
                errors.append(f"{field} must be {expected_type.__name__} when provided")

    if errors:
        return errors
    if design["schema_version"] == 2:
        errors.extend(
            f"shared contract: {message}"
            for message in validate_document("calculation-design-v2", design)
        )
    if design["schema_version"] not in SUPPORTED_SCHEMA_VERSIONS:
        errors.append(f"schema_version must be one of {sorted(SUPPORTED_SCHEMA_VERSIONS)}")
    if design["schema_version"] == 1 and not isinstance(design.get("vasp_stage_envelopes"), list):
        errors.append("schema_version 1 requires vasp_stage_envelopes")
    if design["schema_version"] == 2 and not isinstance(design.get("engine_stage_envelopes"), list):
        errors.append("schema_version 2 requires engine_stage_envelopes")
    if not SLUG_RE.fullmatch(design["design_id"]):
        errors.append("design_id must use lowercase_snake_case")
    if not SLUG_RE.fullmatch(design["project_slug"]):
        errors.append("project_slug must use lowercase_snake_case")
    if design["revision"] < 1:
        errors.append("revision must be a positive integer")
    if design["status"] not in STATUSES:
        errors.append(f"status must be one of {sorted(STATUSES)}")
    if not design["title"].strip():
        errors.append("title must not be empty")
    domain_pack = design.get("domain_pack")
    if domain_pack is not None:
        if not isinstance(domain_pack, str) or not domain_pack.strip():
            errors.append("domain_pack must be a string when provided")
        elif domain_pack not in DOMAIN_PACKS:
            errors.append(f"domain_pack must be one of {sorted(DOMAIN_PACKS)}")
    if "domain_metadata" in design and not isinstance(design["domain_metadata"], dict):
        errors.append("domain_metadata must be an object when provided")

    nonempty_lists = ("systems", "calculation_matrix", "stop_conditions")
    if mode == "research":
        nonempty_lists = (
            "research_questions",
            "hypotheses",
            "systems",
            "observables",
            "controls",
            "convergence_studies",
            "validation_checks",
            "calculation_matrix",
            "evidence",
            "stop_conditions",
        )
    for field in nonempty_lists:
        if not design.get(field):
            errors.append(f"{field} must not be empty")
    envelopes = engine_envelopes(design)
    if not envelopes:
        errors.append("engine_stage_envelopes must not be empty")

    for index, item in enumerate(design.get("research_questions", [])):
        require_fields(item, ("id", "question"), f"research_questions[{index}]", errors)
    for index, item in enumerate(design.get("hypotheses", [])):
        require_fields(item, ("id", "statement", "falsification"), f"hypotheses[{index}]", errors)
    for index, item in enumerate(design.get("systems", [])):
        require_fields(
            item,
            ("system_slug", "model", "structure_provenance", "assumptions"),
            f"systems[{index}]",
            errors,
        )
        if isinstance(item, dict) and has_text(item.get("system_slug")) and not SLUG_RE.fullmatch(item["system_slug"]):
            errors.append(f"systems[{index}].system_slug must use lowercase_snake_case")
        if isinstance(item, dict) and not isinstance(item.get("assumptions"), list):
            errors.append(f"systems[{index}].assumptions must be a list")
        if mode == "task" and isinstance(item, dict):
            for field in ("model", "structure_provenance"):
                value = item.get(field)
                if not has_meaningful_value(value) or placeholder_paths(value):
                    errors.append(f"systems[{index}].{field} must be an exact non-placeholder value")
    for index, item in enumerate(design.get("observables", [])):
        require_fields(
            item,
            ("id", "hypothesis_ids", "quantity", "decision_rule", "uncertainty_target"),
            f"observables[{index}]",
            errors,
        )
    for index, item in enumerate(design.get("controls", [])):
        require_fields(item, ("id", "type", "purpose", "fixed_or_varied"), f"controls[{index}]", errors)
    for index, item in enumerate(design.get("convergence_studies", [])):
        require_fields(
            item,
            (
                "id",
                "parameter",
                "candidate_values",
                "fixed_conditions",
                "target_observable_ids",
                "acceptance_rule",
                "selected_value",
            ),
            f"convergence_studies[{index}]",
            errors,
        )
    for index, item in enumerate(design.get("validation_checks", [])):
        require_fields(item, ("id", "type", "reference", "acceptance_rule"), f"validation_checks[{index}]", errors)

    hypotheses = design.get("hypotheses", [])
    observables = design.get("observables", [])
    convergence_studies = design.get("convergence_studies", [])
    validation_checks = design.get("validation_checks", [])
    evidence = design.get("evidence", [])
    calculation_matrix = design.get("calculation_matrix", [])
    hypothesis_ids = collect_ids(hypotheses, "hypotheses", errors)
    observable_ids = collect_ids(observables, "observables", errors)
    collect_ids(design.get("research_questions", []), "research_questions", errors)
    collect_ids(design.get("controls", []), "controls", errors)
    convergence_ids = collect_ids(convergence_studies, "convergence_studies", errors)
    collect_ids(validation_checks, "validation_checks", errors)
    matrix_ids = collect_ids(calculation_matrix, "calculation_matrix", errors)
    evidence_ids = collect_ids(evidence, "evidence", errors)
    system_ids = {
        item.get("system_slug")
        for item in design.get("systems", [])
        if isinstance(item, dict) and has_text(item.get("system_slug"))
    }

    for index, item in enumerate(observables):
        if not isinstance(item, dict):
            continue
        refs = item.get("hypothesis_ids")
        if not isinstance(refs, list) or not refs:
            errors.append(f"observables[{index}].hypothesis_ids must be a non-empty list")
        elif not set(refs).issubset(hypothesis_ids):
            errors.append(f"observables[{index}].hypothesis_ids contains unknown IDs")

    if mode == "research":
        matrix_fields = (
            "id",
            "class",
            "system_slug",
            "case_slug",
            "hypothesis_ids",
            "purpose",
            "variables",
            "fixed_parameters",
            "stages",
            "observable_ids",
            "completion_gate",
        )
    else:
        matrix_fields = (
            "id",
            "class",
            "system_slug",
            "case_slug",
            "purpose",
            "variables",
            "fixed_parameters",
            "stages",
            "completion_gate",
        )
    for index, item in enumerate(calculation_matrix):
        require_fields(item, matrix_fields, f"calculation_matrix[{index}]", errors)
        if not isinstance(item, dict):
            continue
        if item.get("class") not in TASK_CLASSES:
            errors.append(f"calculation_matrix[{index}].class must be one of {sorted(TASK_CLASSES)}")
        if item.get("system_slug") not in system_ids:
            errors.append(f"calculation_matrix[{index}].system_slug is unknown")
        if has_text(item.get("case_slug")) and not SLUG_RE.fullmatch(item["case_slug"]):
            errors.append(f"calculation_matrix[{index}].case_slug must use lowercase_snake_case")
        if not isinstance(item.get("stages"), list) or not item.get("stages"):
            errors.append(f"calculation_matrix[{index}].stages must be a non-empty list")
        if mode == "research" or "hypothesis_ids" in item:
            if not isinstance(item.get("hypothesis_ids"), list) or not set(item.get("hypothesis_ids", [])).issubset(hypothesis_ids):
                errors.append(f"calculation_matrix[{index}].hypothesis_ids contains unknown IDs")
        if mode == "research" or "observable_ids" in item:
            if not isinstance(item.get("observable_ids"), list) or not set(item.get("observable_ids", [])).issubset(observable_ids):
                errors.append(f"calculation_matrix[{index}].observable_ids contains unknown IDs")
        if mode == "task":
            for field in ("purpose", "completion_gate"):
                value = item.get(field)
                if not has_meaningful_value(value) or placeholder_paths(value):
                    errors.append(f"calculation_matrix[{index}].{field} must be an exact non-placeholder value")

    envelope_ids: set[str] = set()
    for index, item in enumerate(envelopes):
        require_fields(
            item,
            (
                "matrix_id",
                "engine",
                "structure_source",
                "parameter_policy",
                "kpoints_policy",
                "pseudopotential_policy",
                "resource_profile",
                "completion_gates",
            ),
            f"engine_stage_envelopes[{index}]",
            errors,
        )
        if not isinstance(item, dict):
            continue
        engine = item.get("engine")
        if engine not in KNOWN_ENGINES:
            errors.append(
                f"engine_stage_envelopes[{index}].engine must be one of {sorted(KNOWN_ENGINES)}"
            )
        matrix_id = item.get("matrix_id")
        if matrix_id not in matrix_ids:
            errors.append(f"engine_stage_envelopes[{index}].matrix_id is unknown")
        elif matrix_id in envelope_ids:
            errors.append(f"engine_stage_envelopes[{index}].matrix_id duplicates {matrix_id!r}")
        else:
            envelope_ids.add(matrix_id)
        if design["schema_version"] == 2:
            validate_parameter_selection(
                item,
                index,
                observable_ids,
                convergence_ids | evidence_ids,
                errors,
                mode,
            )
        if mode == "task":
            for field in (
                "structure_source",
                "parameter_policy",
                "kpoints_policy",
                "pseudopotential_policy",
                "resource_profile",
            ):
                value = item.get(field)
                if not has_meaningful_value(value) or placeholder_paths(value):
                    errors.append(
                        f"engine_stage_envelopes[{index}].{field} must be an exact non-placeholder value"
                    )
            completion_gates = item.get("completion_gates")
            if not isinstance(completion_gates, dict) or not completion_gates:
                errors.append(f"engine_stage_envelopes[{index}].completion_gates must be a non-empty object")
            else:
                matrix = next(
                    (
                        candidate
                        for candidate in calculation_matrix
                        if isinstance(candidate, dict) and candidate.get("id") == matrix_id
                    ),
                    None,
                )
                for stage in matrix.get("stages", []) if isinstance(matrix, dict) else []:
                    if stage not in completion_gates or not has_meaningful_value(completion_gates.get(stage)):
                        errors.append(
                            f"engine_stage_envelopes[{index}].completion_gates is missing stage {stage!r}"
                        )
            engine_parameters = item.get("engine_parameters")
            if not isinstance(engine_parameters, dict) or not engine_parameters:
                errors.append(
                    f"engine_stage_envelopes[{index}].engine_parameters must contain exact user-supplied values"
                )
            elif any(not has_meaningful_value(value) for value in engine_parameters.values()):
                errors.append(
                    f"engine_stage_envelopes[{index}].engine_parameters must not contain empty values"
                )
    if matrix_ids - envelope_ids:
        errors.append(f"missing DFT engine envelopes for matrix IDs: {sorted(matrix_ids - envelope_ids)}")

    for index, item in enumerate(evidence):
        require_fields(item, ("id", "claim", "source", "kind", "status", "supports"), f"evidence[{index}]", errors)
        if isinstance(item, dict) and item.get("status") not in EVIDENCE_STATUSES:
            errors.append(f"evidence[{index}].status must be one of {sorted(EVIDENCE_STATUSES)}")

    if mode == "task":
        for index, condition in enumerate(design["stop_conditions"]):
            if not has_meaningful_value(condition) or placeholder_paths(condition):
                errors.append(f"stop_conditions[{index}] must be an exact non-placeholder value")

    if not errors and design.get("domain_pack") == DSI_PACK:
        validate_dsi_domain(design, errors)
    if not errors and design.get("domain_pack") == "migration-neb":
        validate_neb_domain(design, errors)
    if not errors and design.get("domain_pack") == "phonon-thermodynamics":
        validate_phonon_domain(design, errors)

    if isinstance(design.get("execution_plan"), Mapping):
        errors.extend(validate_execution_plan(design))

    return errors


def matrix_by_id(design: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {item["id"]: item for item in design["calculation_matrix"] if isinstance(item, dict) and has_text(item.get("id"))}


def envelope_by_matrix(design: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        item["matrix_id"]: item
        for item in engine_envelopes(design)
        if isinstance(item, dict) and has_text(item.get("matrix_id"))
    }


def apply_engine_parameter_overrides(
    design: Mapping[str, Any], matrix_id: str, updates: Mapping[str, Any]
) -> dict[str, Any]:
    """Return a revised design with adopted engine values for one matrix.

    The immutable approval event is deliberately not changed by this helper.
    It produces a new planning record so callers can write the calculation
    design and its provenance atomically after reconciliation has classified
    the on-disk input change.
    """

    revised = copy.deepcopy(dict(design))
    envelopes = revised.get("engine_stage_envelopes")
    if not isinstance(envelopes, list):
        raise DesignError("engine_stage_envelopes must be a list for parameter overrides")
    matches = [
        item
        for item in envelopes
        if isinstance(item, dict) and item.get("matrix_id") == matrix_id
    ]
    if len(matches) != 1:
        raise DesignError(
            f"expected one engine envelope for matrix {matrix_id!r}, found {len(matches)}"
        )
    envelope = matches[0]
    parameters = envelope.setdefault("engine_parameters", {})
    if not isinstance(parameters, dict):
        raise DesignError("engine_parameters must be an object for parameter overrides")
    parameters.update(copy.deepcopy(dict(updates)))

    selection = envelope.get("parameter_selection")
    if isinstance(selection, dict):
        selection_names = {
            "ENCUT": "basis_cutoff",
            "ecutwfc": "basis_cutoff",
            "ecutrho": "basis_cutoff",
            "KPOINTS": "kpoints",
            "kpoints": "kpoints",
            "occupations": "occupations",
            "ISMEAR": "occupations",
            "SIGMA": "occupations",
            "degauss": "occupations",
        }
        for name, value in updates.items():
            category = selection_names.get(name)
            if category is None:
                category = selection_names.get(str(name).upper())
            if category is None:
                category = selection_names.get(str(name).lower())
            if category and isinstance(selection.get(category), dict):
                previous = copy.deepcopy(selection[category])
                previous.pop("previous_selection", None)
                selection[category].update({
                    "status": "user_specified" if revised.get("design_mode") == "task" else "candidate",
                    "previous_selection": previous,
                    "method": "user on-disk input override; precision not verified",
                    "source_metadata": {"source": "user on-disk input", "parameter": str(name)},
                })
                selection[category]["selected_value"] = copy.deepcopy(value)

    revision = revised.get("revision")
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
        raise DesignError("design revision must be a positive integer for parameter overrides")
    revised["revision"] = revision + 1
    return revised


def approval_errors(design: dict[str, Any], scope: list[str]) -> list[str]:
    errors = validate_design(design)
    if errors:
        return errors
    mode = design.get("design_mode", "research")
    if design["status"] != "ready_for_review":
        errors.append("design status must be ready_for_review before approval")
    if design.get("pending_decisions"):
        errors.append("pending_decisions must be empty before approval")
    matrices = matrix_by_id(design)
    envelopes = envelope_by_matrix(design)
    for matrix_id in scope:
        if matrix_id not in matrices:
            errors.append(f"approval scope contains unknown matrix ID: {matrix_id}")
            continue
        for path in placeholder_paths(matrices[matrix_id], f"calculation_matrix.{matrix_id}"):
            errors.append(f"approval scope contains placeholder: {path}")
        envelope = envelopes.get(matrix_id)
        if envelope:
            for path in placeholder_paths(envelope, f"engine_stage_envelopes.{matrix_id}"):
                errors.append(f"approval scope contains placeholder: {path}")
        if mode == "task":
            selection = envelope.get("parameter_selection", {}) if envelope else {}
            evidence_by_id = {
                item.get("id"): item
                for item in design.get("evidence", [])
                if isinstance(item, dict) and has_text(item.get("id"))
            }
            convergence_by_id = {
                item.get("id"): item
                for item in design.get("convergence_studies", [])
                if isinstance(item, dict) and has_text(item.get("id"))
            }
            if isinstance(selection, dict):
                for category in REQUIRED_PARAMETER_SELECTIONS:
                    entry = selection.get(category)
                    if not isinstance(entry, dict) or entry.get("status") != "validated":
                        continue
                    refs = entry.get("evidence_refs", [])
                    pending_evidence = [
                        ref
                        for ref in refs
                        if ref in evidence_by_id and evidence_by_id[ref].get("status") != "verified"
                    ]
                    unresolved_convergence = [
                        ref
                        for ref in refs
                        if ref in convergence_by_id
                        and (
                            convergence_by_id[ref].get("selected_value") is None
                            or is_placeholder(convergence_by_id[ref].get("selected_value"))
                        )
                    ]
                    if pending_evidence:
                        errors.append(
                            f"task mode parameter_selection.{category} requires referenced evidence "
                            f"to be verified; pending: {pending_evidence}"
                        )
                    if unresolved_convergence:
                        errors.append(
                            f"task mode parameter_selection.{category} requires referenced convergence "
                            f"studies to have selected values; unresolved: {unresolved_convergence}"
                        )
            continue
        if matrices[matrix_id].get("class") == "production":
            pending = [item.get("id", "unknown") for item in design.get("evidence", []) if item.get("status") != "verified"]
            if pending:
                errors.append(f"production scope requires verified evidence; pending: {pending}")
            unresolved = [
                item.get("id", "unknown")
                for item in design.get("convergence_studies", [])
                if item.get("selected_value") is None or is_placeholder(item.get("selected_value"))
            ]
            if unresolved:
                errors.append(f"production scope requires selected convergence values; unresolved: {unresolved}")
            for index, item in enumerate(design.get("validation_checks", [])):
                for path in placeholder_paths(item, f"validation_checks[{index}]"):
                    errors.append(f"production scope contains placeholder: {path}")
            if envelope:
                selection = envelope.get("parameter_selection", {})
                for category in REQUIRED_PARAMETER_SELECTIONS:
                    entry = selection.get(category, {}) if isinstance(selection, dict) else {}
                    if entry.get("status") != "validated":
                        errors.append(
                            f"production parameter_selection.{category} status must be validated"
                        )
                    if not has_meaningful_value(entry.get("selected_value")):
                        errors.append(
                            f"production parameter_selection.{category} selected_value is required"
                        )
                engine_parameters = envelope.get("engine_parameters")
                if not isinstance(engine_parameters, dict) or not engine_parameters:
                    errors.append(
                        "production engine_parameters must contain exact reviewed engine values"
                    )
    return errors


def normalize_scope(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        for item in value.split(","):
            item = item.strip()
            if item and item not in result:
                result.append(item)
    if not result:
        raise DesignError("at least one --scope matrix ID is required")
    return result


def project_slug(project: Path, explicit: str | None) -> str:
    if explicit:
        if not SLUG_RE.fullmatch(explicit):
            raise DesignError("--project-slug must use lowercase_snake_case")
        return explicit
    spec_path = project / "docs/project_spec.json"
    if spec_path.exists():
        spec = load_json(spec_path)
        value = spec.get("project_slug")
        if has_text(value) and SLUG_RE.fullmatch(value):
            return value
    if SLUG_RE.fullmatch(project.name):
        return project.name
    raise DesignError("cannot infer project_slug; pass --project-slug")


def workspace_root(project: Path) -> Path:
    resolved = project.expanduser().resolve()
    try:
        discovered = discover_workspace(resolved)
    except ValueError as exc:
        raise DesignError(str(exc)) from exc
    if discovered != resolved and route_for(resolved) is None:
        raise DesignError(
            f"--project must be the discovered workspace root {discovered}, not {resolved}"
        )
    return discovered


def scoped_plan_paths(
    project: Path, composition_slug: str, structure_slug: str
) -> tuple[Path, Path, Path]:
    root = workspace_root(project)
    try:
        plan_dir = design_plan_root(project, composition_slug, structure_slug)
    except ValueError as exc:
        raise DesignError(str(exc)) from exc
    return root, plan_dir, plan_dir / "calculation_design.json"


def readme_sync(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise DesignError(f"human-readable design README is missing: {path}") from exc
    if not text.strip():
        raise DesignError(f"human-readable design README is empty: {path}")
    match = README_SYNC_RE.search(text)
    if not match:
        raise DesignError(f"README is missing dft-design-sync marker: {path}")
    try:
        value = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise DesignError(f"README has invalid dft-design-sync marker: {path}") from exc
    if not isinstance(value, dict):
        raise DesignError(f"README dft-design-sync marker must be an object: {path}")
    return value


def approval_summary(design: dict[str, Any], event: dict[str, Any] | None = None) -> str:
    approval = "not approved"
    scope = "-"
    reviewer = "-"
    approved_at = "-"
    if event is not None:
        approval = "approved"
        scope = ", ".join(event["scope"])
        reviewer = str(event["reviewer"])
        approved_at = str(event["approved_at"])
    return (
        f"{SUMMARY_START}\n"
        "## 当前状态\n\n"
        "| 项目 | 当前值 |\n"
        "|---|---|\n"
        f"| Design ID | `{design['design_id']}` |\n"
        f"| Revision | `{design['revision']}` |\n"
        f"| Design status | `{design['status']}` |\n"
        f"| Design mode | `{design.get('design_mode', 'research')}` |\n"
        f"| Scientific approval | `{approval}` |\n"
        f"| Approved scope | `{scope}` |\n"
        f"| Reviewer | `{reviewer}` |\n"
        f"| Approved at | `{approved_at}` |\n"
        f"{SUMMARY_END}"
    )


def update_readme_summary(path: Path, design: dict[str, Any], event: dict[str, Any]) -> None:
    text = path.read_text(encoding="utf-8")
    block = approval_summary(design, event)
    start = text.find(SUMMARY_START)
    end = text.find(SUMMARY_END)
    if start >= 0 and end >= start:
        end += len(SUMMARY_END)
        updated = text[:start] + block + text[end:]
    else:
        marker = README_SYNC_RE.search(text)
        insert_at = marker.end() if marker else 0
        updated = text[:insert_at] + "\n\n" + block + text[insert_at:]
    path.write_text(updated.rstrip() + "\n", encoding="utf-8")


def load_history(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError as exc:
        raise DesignError(f"history file does not exist: {path}") from exc
    events: list[dict[str, Any]] = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise DesignError(f"invalid JSON in {path} line {line_number}: {exc}") from exc
        if not isinstance(event, dict):
            raise DesignError(f"history event must be an object: {path} line {line_number}")
        events.append(event)
    return events


def validate_plan_scope(design_path: Path, design: dict[str, Any]) -> list[str]:
    """Validate the compact sibling files for a managed calculation design."""
    if design_path.name != "calculation_design.json":
        return []
    errors: list[str] = []
    readme_path = plan_readme_path(design_path)
    history_path = design_path.parent / "history.jsonl"
    try:
        sync = readme_sync(readme_path)
    except DesignError as exc:
        errors.append(str(exc))
    else:
        if sync.get("design_id") != design.get("design_id"):
            errors.append("README sync marker design_id does not match calculation_design.json")
        if sync.get("revision") != design.get("revision"):
            errors.append("README sync marker revision does not match calculation_design.json")
    try:
        load_history(history_path)
    except DesignError as exc:
        errors.append(str(exc))
    return errors


def append_history(path: Path, event: dict[str, Any]) -> None:
    existing = path.read_text(encoding="utf-8")
    prefix = "" if not existing or existing.endswith("\n") else "\n"
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(prefix + json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")


def cmd_bootstrap(args: argparse.Namespace) -> int:
    project = args.project.expanduser().resolve()
    if not project.is_dir():
        raise DesignError(f"project directory does not exist: {project}")
    project, plan_dir, design_path = scoped_plan_paths(
        project, args.composition_slug, args.structure_slug
    )
    slug = project_slug(project, args.project_slug)
    readme_path = plan_readme_path(design_path)
    history_path = plan_dir / "history.jsonl"
    directories = [plan_dir]
    files = [design_path, readme_path, history_path]
    for directory in directories:
        state = "exists" if directory.exists() else "create"
        print(f"[{state}] directory {directory}")
    for destination in files:
        state = "keep" if destination.exists() else "create"
        print(f"[{state}] file {destination}")
    if args.dry_run:
        return 0
    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)
    if not design_path.exists():
        design = load_json(ASSET_DIR / "calculation_design.template.json")
        design["project_slug"] = slug
        design["design_id"] = f"{slug}_computation"
        design["title"] = f"{slug} 计算实验设计"
        design_path.write_text(
            json.dumps(design, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    else:
        design = load_json(design_path)
    if not readme_path.exists():
        marker = json.dumps(
            {"design_id": design["design_id"], "revision": design["revision"]},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        content = (ASSET_DIR / "plan_readme.template.md").read_text(encoding="utf-8")
        content = content.replace("{{sync_marker}}", marker)
        content = content.replace("{{title}}", str(design["title"]))
        content = content.replace("{{summary}}", approval_summary(design))
        readme_path.write_text(content.rstrip() + "\n", encoding="utf-8")
    if not history_path.exists():
        history_path.write_text("", encoding="utf-8")
    return 0


def print_errors(errors: list[str]) -> None:
    for error in errors:
        print(f"[error] {error}", file=sys.stderr)


def cmd_validate(args: argparse.Namespace) -> int:
    design_path = args.design.expanduser().resolve()
    design = load_json(design_path)
    errors = validate_design(design)
    errors.extend(validate_plan_scope(design_path, design))
    if errors:
        print_errors(errors)
        return 1
    print(f"[ok] valid calculation design: {args.design}")
    return 0


def cmd_render(args: argparse.Namespace) -> int:
    design = load_json(args.design.expanduser().resolve())
    errors = validate_design(design)
    if errors:
        print_errors(errors)
        return 1
    print(approval_summary(design))
    return 0


def cmd_approve(args: argparse.Namespace) -> int:
    project = args.project.expanduser().resolve()
    project, plan_dir, design_path = scoped_plan_paths(
        project, args.composition_slug, args.structure_slug
    )
    readme_path = plan_readme_path(design_path)
    history_path = plan_dir / "history.jsonl"
    design = load_json(design_path)
    if not has_text(args.reviewer):
        raise DesignError("--reviewer must not be empty")
    scope = normalize_scope(args.scope)
    errors = approval_errors(design, scope)
    if errors:
        print_errors(errors)
        return 1
    sync = readme_sync(readme_path)
    if sync.get("design_id") != design["design_id"] or sync.get("revision") != design["revision"]:
        raise DesignError("README sync marker does not match calculation_design.json")
    events = load_history(history_path)
    event_id = f"{design['design_id']}:r{design['revision']:04d}"
    if any(event.get("event_id") == event_id for event in events):
        raise DesignError(f"approval event already exists and cannot be overwritten: {event_id}")
    approval = {
        "history_schema_version": 1,
        "event_type": "scientific_design_approved",
        "event_id": event_id,
        "design_id": design["design_id"],
        "revision": design["revision"],
        "scope": scope,
        "reviewer": args.reviewer,
        "approved_at": utc_now(),
        "design_path": design_path.relative_to(project).as_posix(),
        "design_sha256": canonical_json_sha256(design),
        "design_snapshot": design,
    }
    append_history(history_path, approval)
    update_readme_summary(readme_path, design, approval)
    print(f"[ok] approved scientific design scope {scope}: {history_path}#{event_id}")
    return 0


def verify_approval(history_path: Path, event_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    history_path = history_path.expanduser().resolve()
    matches = [event for event in load_history(history_path) if event.get("event_id") == event_id]
    if len(matches) != 1:
        raise DesignError(f"expected exactly one approval event {event_id!r}, found {len(matches)}")
    approval = matches[0]
    required = {
        "history_schema_version",
        "event_type",
        "event_id",
        "design_id",
        "revision",
        "scope",
        "reviewer",
        "approved_at",
        "design_path",
        "design_sha256",
        "design_snapshot",
    }
    missing = sorted(required - set(approval))
    if missing:
        raise DesignError(f"approval is missing fields: {missing}")
    if approval["history_schema_version"] != 1 or approval["event_type"] != "scientific_design_approved":
        raise DesignError("approval header is invalid")
    design = approval["design_snapshot"]
    if not isinstance(design, dict):
        raise DesignError("approval design_snapshot must be an object")
    if canonical_json_sha256(design) != approval["design_sha256"]:
        raise DesignError("calculation design hash does not match approval")
    errors = validate_design(design)
    if errors:
        raise DesignError("approved design is invalid: " + "; ".join(errors))
    if design["design_id"] != approval["design_id"] or design["revision"] != approval["revision"]:
        raise DesignError("approval design ID or revision does not match snapshot")
    scope = approval["scope"]
    if not isinstance(scope, list) or not scope:
        raise DesignError("approval scope must be a non-empty list")
    unknown = sorted(set(scope) - set(matrix_by_id(design)))
    if unknown:
        raise DesignError(f"approval scope contains unknown matrix IDs: {unknown}")
    semantic_errors = approval_errors(design, list(scope))
    if semantic_errors:
        raise DesignError("approved design no longer satisfies approval rules: " + "; ".join(semantic_errors))
    return approval, design


def cmd_verify(args: argparse.Namespace) -> int:
    approval, _ = verify_approval(args.history, args.event_id)
    print(
        f"[ok] verified scientific design approval: {approval['design_id']} "
        f"revision {approval['revision']} scope {approval['scope']}"
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="computation_design.py")
    sub = parser.add_subparsers(dest="command", required=True)

    bootstrap = sub.add_parser("bootstrap", help="Create missing design files without overwriting existing work.")
    bootstrap.add_argument("--project", type=Path, required=True)
    bootstrap.add_argument("--project-slug")
    bootstrap.add_argument("--composition-slug", required=True)
    bootstrap.add_argument("--structure-slug", required=True)
    mode = bootstrap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    bootstrap.set_defaults(func=cmd_bootstrap)

    validate = sub.add_parser("validate", help="Validate a calculation_design.json contract.")
    validate.add_argument("--design", type=Path, required=True)
    validate.set_defaults(func=cmd_validate)

    render = sub.add_parser("render", help="Render a compact design summary.")
    render.add_argument("--design", type=Path, required=True)
    render.set_defaults(func=cmd_render)

    approve = sub.add_parser("approve", help="Append an immutable scientific approval event to history.jsonl.")
    approve.add_argument("--project", type=Path, required=True)
    approve.add_argument("--composition-slug", required=True)
    approve.add_argument("--structure-slug", required=True)
    approve.add_argument("--reviewer", required=True)
    approve.add_argument("--scope", action="append", required=True, help="Approved matrix ID; repeat or comma-separate.")
    approve.set_defaults(func=cmd_approve)

    verify = sub.add_parser("verify", help="Verify one scientific approval event from history.jsonl.")
    verify.add_argument("--history", type=Path, required=True)
    verify.add_argument("--event-id", required=True)
    verify.set_defaults(func=cmd_verify)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        return args.func(args)
    except (DesignError, OSError) as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
