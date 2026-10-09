#!/usr/bin/env python3
"""Compute DFT fingerprints, register provenance DAGs, and index reusable work."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping

CONTRACTS_ROOT = Path(__file__).resolve().parents[2] / "dft-contracts"
if str(CONTRACTS_ROOT) not in sys.path:
    sys.path.insert(0, str(CONTRACTS_ROOT))

from dft_contracts import sha256_file, sha256_json  # noqa: E402
from vwm_ledger import (  # noqa: E402
    add_provenance_edge,
    connect,
    get_task,
    init_db,
    provenance_graph,
    register_provenance_node,
)


SCIENTIFIC_INPUT_NAMES = {
    "POSCAR", "CONTCAR", "INCAR", "INCAR.fd", "KPOINTS", "POTCAR",
    "pw.in", "scf.in", "relax.in", "nscf.in", "bands.in", "ph.in",
}
EXECUTION_INPUT_NAMES = {"job.sh", "submit.slurm", "run_vasp.sh"}


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def normalized_hashes(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {
        str(name): str(digest)
        for name, digest in sorted(value.items())
        if isinstance(digest, str) and digest
    }


def local_input_hashes(task_dir: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for name in sorted(SCIENTIFIC_INPUT_NAMES | EXECUTION_INPUT_NAMES):
        path = task_dir / name
        if path.is_file():
            hashes[name] = sha256_file(path)
    input_dir = task_dir / "input"
    if input_dir.is_dir():
        for path in sorted(item for item in input_dir.iterdir() if item.is_file()):
            hashes[f"input/{path.name}"] = sha256_file(path)
    return hashes


def workflow_provenance(workflow: Mapping[str, Any]) -> dict[str, Any]:
    """Extract traceable v1/v2 workflow context for derived manager views."""

    attempts = workflow.get("attempts")
    attempt_records = (
        [item for item in attempts if isinstance(item, Mapping)]
        if isinstance(attempts, list)
        else []
    )
    attempt_ids = [str(item["attempt_id"]) for item in attempt_records if item.get("attempt_id")]

    lineage = workflow.get("lineage")
    lineage = lineage if isinstance(lineage, Mapping) else {}
    user_overrides: list[str] = []
    evidence: list[dict[str, Any]] = []

    authority = workflow.get("input_authority")
    if isinstance(authority, Mapping):
        for name, record in authority.items():
            if isinstance(record, Mapping) and record.get("authority") == "user_override":
                label = str(name)
                if label not in user_overrides:
                    user_overrides.append(label)
                evidence.append({"name": label, **dict(record)})

    inputs = workflow.get("inputs")
    files = inputs.get("files") if isinstance(inputs, Mapping) else None
    if isinstance(files, list):
        for record in files:
            if not isinstance(record, Mapping) or record.get("authority") != "user_override":
                continue
            label = str(record.get("name") or record.get("path") or "input")
            if label not in user_overrides:
                user_overrides.append(label)
            if not any(item.get("name") == label for item in evidence):
                evidence.append({"name": label, **dict(record)})

    return {
        "contract": workflow.get("contract"),
        "schema_version": workflow.get("schema_version"),
        "task_slug": workflow.get("task_slug"),
        "status": workflow.get("status"),
        "attempt_ids": attempt_ids,
        "lineage": {
            "derived_from": lineage.get("derived_from"),
            "supersedes": lineage.get("supersedes"),
        },
        "user_overrides": user_overrides,
        "user_override_evidence": evidence,
    }


def pseudopotential_records(spec: dict[str, Any], hashes: dict[str, str]) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    source = spec.get("pseudopotential_components") or spec.get("POTCAR_components")
    if isinstance(source, list):
        for item in source:
            if not isinstance(item, dict):
                continue
            digest = item.get("sha256") or item.get("hash")
            if digest:
                records.append({
                    "element": str(item.get("element") or ""),
                    "label": str(item.get("label") or item.get("path") or ""),
                    "sha256": str(digest),
                })
    pseudo_map = spec.get("pseudopotential_sha256")
    if isinstance(pseudo_map, dict):
        records.extend(
            {"element": "", "label": str(name), "sha256": str(digest)}
            for name, digest in pseudo_map.items()
        )
    if not records:
        for name, digest in hashes.items():
            if Path(name).name == "POTCAR" or Path(name).suffix.lower() in {".upf", ".psp8", ".psp"}:
                records.append({"element": "", "label": name, "sha256": digest})
    return sorted(records, key=lambda item: (item["element"], item["label"], item["sha256"]))


def scientific_input_hashes(hashes: dict[str, str]) -> dict[str, str]:
    return {
        name: digest
        for name, digest in hashes.items()
        if Path(name).name not in EXECUTION_INPUT_NAMES
    }


def compute_fingerprint(
    task_dir: str | Path,
    result_document: dict[str, Any] | None = None,
) -> dict[str, Any]:
    root = Path(task_dir).expanduser().resolve()
    workflow = load_json(root / "workflow.json")
    uses_workflow = workflow.get("contract", "").startswith("dft.workflow.")
    spec = workflow if uses_workflow else load_json(root / "task_spec.json")
    result = result_document or load_json(root / "result.json")
    hashes = normalized_hashes(spec.get("input_hashes") or spec.get("input_sha256"))
    if uses_workflow:
        inputs = spec.get("inputs")
        files = inputs.get("files") if isinstance(inputs, Mapping) else None
        if isinstance(files, list):
            for item in files:
                if not isinstance(item, Mapping):
                    continue
                name = item.get("path") or item.get("name")
                digest = item.get("sha256")
                if name and isinstance(digest, str) and digest:
                    hashes[str(name)] = digest
    for name in list(hashes):
        path = root / name
        if path.is_file():
            hashes[name] = sha256_file(path)
    hashes.update(local_input_hashes(root))
    for pattern in ("*.upf", "*.UPF", "*.psp8", "*.psp"):
        for path in root.glob(pattern):
            if path.is_file():
                hashes[path.name] = sha256_file(path)
    design = spec.get("design") if isinstance(spec.get("design"), Mapping) else None
    if design is None:
        design = spec.get("design_provenance") if isinstance(spec.get("design_provenance"), dict) else {}
    parents = sorted(str(value) for value in spec.get("parent_fingerprints", []) if value)
    structure_hash = None
    if isinstance(spec.get("structure"), dict):
        structure_hash = spec["structure"].get("sha256")
    if not structure_hash:
        structure_hash = next(
            (digest for name, digest in hashes.items() if Path(name).name in {"POSCAR", "CONTCAR"}),
            None,
        )
    scientific_payload = {
        "engine": spec.get("engine") or result.get("engine") or "unknown",
        "task_kind": spec.get("task_kind") or spec.get("stage") or spec.get("task_class") or spec.get("task_slug") or "unknown",
        "structure_hash": structure_hash,
        "scientific_input_hashes": scientific_input_hashes(hashes),
        "pseudopotentials": pseudopotential_records(spec, hashes),
        "kpoints": spec.get("kpoints") or {},
        "engine_parameters": (
            spec.get("engine_parameters")
            or spec.get("incar_defaults")
            or design.get("engine_parameters")
            or {}
        ),
        "design": {
            key: design.get(key)
            for key in (
                "design_id",
                "design_revision",
                "revision",
                "matrix_id",
                "matrix_sha256",
                "approval_ref",
                "baseline_parameter_hash",
            )
            if design.get(key) is not None
        },
        "domain_context": spec.get("domain_context") or {},
        "parent_fingerprints": parents,
    }
    execution_payload = {
        "backend": spec.get("backend") or "unknown",
        "engine_version": spec.get("engine_version") or result.get("engine_version"),
        "cluster": spec.get("cluster"),
        "resources": spec.get("resources") or {},
        "resource_hash": spec.get("resource_hash"),
        "remote": spec.get("remote") or {},
        "execution_input_hashes": {
            name: digest for name, digest in hashes.items() if Path(name).name in EXECUTION_INPUT_NAMES
        },
        "executable": spec.get("executable") or spec.get("command"),
        "module_identity": spec.get("module_identity") or spec.get("modules"),
    }
    workflow_context = workflow_provenance(workflow) if uses_workflow else {}
    if workflow_context:
        execution_payload["workflow"] = workflow_context
    scientific = sha256_json(scientific_payload)
    execution = sha256_json(execution_payload)
    exact_payload = {
        "scientific": scientific,
        "execution": execution,
        "all_input_hashes": hashes,
        "parents": parents,
    }
    if workflow_context:
        exact_payload["workflow"] = workflow_context
    return {
        "contract": "dft.calculation-fingerprint.v1",
        "exact": sha256_json(exact_payload),
        "scientific": scientific,
        "execution": execution,
        "engine": scientific_payload["engine"],
        "task_kind": scientific_payload["task_kind"],
        "structure_hash": structure_hash,
        "parent_fingerprints": parents,
        "workflow": workflow_context,
        "attempt_ids": workflow_context.get("attempt_ids", []),
        "lineage": workflow_context.get("lineage", {}),
        "user_overrides": workflow_context.get("user_overrides", []),
        "payloads": {
            "scientific": scientific_payload,
            "execution": execution_payload,
            "workflow": workflow_context,
        },
    }


def compatibility(left: dict[str, Any], right: dict[str, Any]) -> str:
    if left.get("exact") == right.get("exact"):
        return "exact_match"
    if left.get("scientific") == right.get("scientific"):
        return "scientifically_compatible"
    if (
        left.get("structure_hash")
        and left.get("structure_hash") == right.get("structure_hash")
        and left.get("task_kind") == right.get("task_kind")
    ):
        return "similar_only"
    return "incompatible"


def artifact_fingerprint(node_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Fingerprint a provenance artifact without pretending it is a calculation."""
    scientific = sha256_json({"node_type": node_type, "payload": payload})
    execution = sha256_json({"artifact_generation": payload.get("generator") or "recorded"})
    return {
        "contract": "dft.provenance-artifact-fingerprint.v1",
        "exact": sha256_json({"scientific": scientific, "execution": execution}),
        "scientific": scientific,
        "execution": execution,
        "engine": payload.get("engine") or "not_applicable",
        "task_kind": node_type,
        "structure_hash": None,
        "parent_fingerprints": [],
        "payloads": {"scientific": payload, "execution": {"generator": payload.get("generator")}},
    }


def write_new_json(path: Path, value: dict[str, Any], overwrite: bool = False) -> None:
    if path.exists() and not overwrite:
        raise FileExistsError(f"refusing to overwrite: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def cache_store(cache_root: Path, fingerprint: dict[str, Any], source: Path) -> Path:
    entry = cache_root / "scientific" / fingerprint["scientific"] / "exact" / fingerprint["exact"]
    entry.mkdir(parents=True, exist_ok=True)
    metadata = {
        "fingerprint": fingerprint,
        "source_path": str(source.resolve()),
    }
    (entry / "cache_entry.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return entry


def cache_lookup(cache_root: Path, fingerprint: dict[str, Any]) -> dict[str, Any]:
    exact = cache_root / "scientific" / fingerprint["scientific"] / "exact" / fingerprint["exact"] / "cache_entry.json"
    if exact.is_file():
        return {"match": "exact_match", "entry": load_json(exact)}
    scientific = cache_root / "scientific" / fingerprint["scientific"] / "exact"
    candidates = sorted(scientific.glob("*/cache_entry.json")) if scientific.is_dir() else []
    if candidates:
        return {"match": "scientifically_compatible", "entries": [load_json(path) for path in candidates]}
    return {"match": "none", "entries": []}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="vwm_provenance.py")
    sub = parser.add_subparsers(dest="command", required=True)
    fingerprint = sub.add_parser("fingerprint")
    fingerprint.add_argument("--task-dir", type=Path, required=True)
    fingerprint.add_argument("--output", type=Path)
    fingerprint.add_argument("--overwrite", action="store_true")
    compare = sub.add_parser("compare")
    compare.add_argument("left", type=Path)
    compare.add_argument("right", type=Path)
    register = sub.add_parser("register")
    register.add_argument("--ledger", type=Path, required=True)
    register.add_argument("--project", required=True)
    register.add_argument("--task", required=True)
    register.add_argument("--task-dir", type=Path, required=True)
    graph = sub.add_parser("graph")
    graph.add_argument("--ledger", type=Path, required=True)
    graph.add_argument("--project")
    store = sub.add_parser("cache-store")
    store.add_argument("--cache-root", type=Path, required=True)
    store.add_argument("--task-dir", type=Path, required=True)
    lookup = sub.add_parser("cache-lookup")
    lookup.add_argument("--cache-root", type=Path, required=True)
    lookup.add_argument("--task-dir", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "fingerprint":
        value = compute_fingerprint(args.task_dir)
        if args.output:
            write_new_json(args.output, value, args.overwrite)
        print(json.dumps(value, indent=2, sort_keys=True))
        return 0
    if args.command == "compare":
        left, right = load_json(args.left), load_json(args.right)
        print(json.dumps({"compatibility": compatibility(left, right)}, indent=2))
        return 0
    if args.command == "register":
        value = compute_fingerprint(args.task_dir)
        init_db(args.ledger)
        with connect(args.ledger) as conn:
            if get_task(conn, args.project, args.task) is None:
                raise KeyError(f"Task not found: {args.project}/{args.task}")
            node = register_provenance_node(
                conn, project=args.project, task=args.task, fingerprint=value
            )
            for parent in value["parent_fingerprints"]:
                parent_rows = conn.execute(
                    "SELECT id FROM provenance_nodes WHERE project_id = ? AND fingerprint = ? ORDER BY id DESC",
                    (node["project_id"], parent),
                ).fetchall()
                for parent_row in parent_rows:
                    add_provenance_edge(
                        conn, parent_node_id=int(parent_row["id"]), child_node_id=int(node["id"])
                    )
            print(json.dumps({"node_id": node["id"], "fingerprint": value}, indent=2, sort_keys=True))
        return 0
    if args.command == "graph":
        init_db(args.ledger)
        with connect(args.ledger) as conn:
            print(json.dumps(provenance_graph(conn, args.project), indent=2, sort_keys=True))
        return 0
    value = compute_fingerprint(args.task_dir)
    if args.command == "cache-store":
        entry = cache_store(args.cache_root, value, args.task_dir)
        print(json.dumps({"stored": str(entry), "fingerprint": value["exact"]}, indent=2))
        return 0
    if args.command == "cache-lookup":
        print(json.dumps(cache_lookup(args.cache_root, value), indent=2, sort_keys=True))
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
