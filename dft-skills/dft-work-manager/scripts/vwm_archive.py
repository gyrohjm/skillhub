#!/usr/bin/env python3
"""Archive DFT task directories and update the DFT Work Manager ledger."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from hashlib import sha256

CONTRACTS_ROOT = Path(__file__).resolve().parents[2] / "dft-contracts"
if str(CONTRACTS_ROOT) not in sys.path:
    sys.path.insert(0, str(CONTRACTS_ROOT))
from dft_contracts import validate_document

from vwm_ledger import (
    add_event,
    add_provenance_edge,
    connect,
    init_db,
    record_files,
    register_provenance_node,
    register_task,
    update_task,
)
from vwm_provenance import artifact_fingerprint, compute_fingerprint


COMMON_CORE_NAMES = {
    "job.sh",
    "submit.slurm",
    "task_manifest.json",
    "task_spec.json",
    "state.json",
    "submission_review.dat",
    "submission_approval.json",
    "queue.log",
    "fail_reason.txt",
    "result.json",
    "plot_manifest.json",
    "analysis_report.md",
}
VASP_CORE_NAMES = {
    "POSCAR",
    "INCAR",
    "KPOINTS",
    "POTCAR",
    "run_vasp.sh",
    "OUTCAR",
    "OSZICAR",
    "CONTCAR",
    "vasp.out",
    "vasp.err",
}
ENGINE_CORE_SUFFIXES = {
    "quantum-espresso": {".in", ".out", ".xml"},
    "cp2k": {".inp", ".out", ".restart", ".ener", ".forces", ".cell", ".xyz"},
    "abinit": {".abi", ".abo", ".files", ".in", ".out"},
    "gpaw": {".gpw"},
}
SCIENTIFIC_DESIGN_NAMES = {
    "calculation_design.json",
    "computation_plan.md",
    "approval.json",
    "design_change_request.json",
}
PLOT_SOURCE_NAMES = {
    "EIGENVAL",
    "DOSCAR",
    "PROCAR",
    "KLABELS",
    "REFORMATTED_BAND.dat",
    "band.yaml",
    "total_dos.dat",
    "projected_dos.dat",
    "COHPCAR.lobster",
    "ICOHPLIST.lobster",
    "COOPCAR.lobster",
    "COBICAR.lobster",
    "lobsterout",
}
PLOT_DATA_EXTS = {".dat", ".csv", ".png", ".pdf"}
METADATA_EXTS = {".json", ".md"}
LARGE_NAMES = {"WAVECAR", "CHGCAR", "vasprun.xml", "XDATCAR", "ELFCAR", "PARCHG", "charge-density.dat"}
SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", ".mypy_cache"}
INTERNAL_ARCHIVE_NAMES = {"manifest.json", "SHA256SUMS"}

LOWER_SNAKE_RE = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def safe_slug(value: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip())
    return clean.strip("-") or "unnamed"


def require_lower_snake(name: str, value: str) -> str:
    if not LOWER_SNAKE_RE.fullmatch(value):
        raise ValueError(f"{name} must use short English lowercase_snake_case; got {value!r}")
    return value


def archive_destination(
    archive_root: Path,
    project: str,
    task: str,
    stamp_value: str,
    system_slug: str | None = None,
    case_slug: str | None = None,
) -> Path:
    if bool(system_slug) != bool(case_slug):
        raise ValueError("--system-slug and --case-slug must be provided together")
    if system_slug and case_slug:
        require_lower_snake("project", project)
        return (
            archive_root
            / require_lower_snake("system_slug", system_slug)
            / require_lower_snake("case_slug", case_slug)
            / stamp_value
        )
    return archive_root / safe_slug(project) / safe_slug(task) / stamp_value


def file_sha256(path: Path) -> str:
    h = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def detect_engine(source: Path) -> str:
    spec = load_task_spec(source)
    engine = spec.get("engine") if isinstance(spec, dict) else None
    if isinstance(engine, str) and engine:
        return engine
    names = {path.name for path in source.iterdir() if path.is_file()}
    if names & {"INCAR", "POSCAR", "OUTCAR", "vasprun.xml"}:
        return "vasp"
    if any(name.endswith(".inp") for name in names):
        return "cp2k"
    if any(name.endswith((".abi", ".abo")) for name in names):
        return "abinit"
    if any(name.endswith(".gpw") for name in names):
        return "gpaw"
    if any(name in {"pw.in", "pw.out", "data-file-schema.xml"} for name in names):
        return "quantum-espresso"
    for path in source.iterdir():
        if not path.is_file() or path.suffix.lower() not in {".in", ".out"}:
            continue
        try:
            sample = path.read_text(encoding="utf-8", errors="replace")[:200_000].upper()
        except OSError:
            continue
        if "&CONTROL" in sample and "&SYSTEM" in sample and "ATOMIC_SPECIES" in sample:
            return "quantum-espresso"
        if "PROGRAM PWSCF" in sample or "QUANTUM ESPRESSO" in sample:
            return "quantum-espresso"
    return "other"


def classify(path: Path, rel: Path, include_large: bool, engine: str = "other") -> str | None:
    name = path.name
    if rel.parent == Path(".") and name in INTERNAL_ARCHIVE_NAMES:
        return None
    if name in LARGE_NAMES and not include_large:
        return None
    if name in LARGE_NAMES:
        return "large"
    if name in SCIENTIFIC_DESIGN_NAMES or "design_reviews" in rel.parts or "design" in rel.parts:
        return "scientific_design"
    if name in COMMON_CORE_NAMES:
        return "core"
    if engine == "vasp" and name in VASP_CORE_NAMES:
        return "core"
    if path.suffix.lower() in ENGINE_CORE_SUFFIXES.get(engine, set()):
        return "core"
    if name in PLOT_SOURCE_NAMES:
        return "plot_source"
    if path.suffix.lower() in PLOT_DATA_EXTS:
        return "plot_data"
    if path.suffix.lower() in METADATA_EXTS:
        return "metadata"
    return None


def collect(
    source: Path,
    include_large: bool,
    archive_root: Path | None = None,
    engine: str = "auto",
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    source = source.resolve()
    engine = detect_engine(source) if engine == "auto" else engine
    archive_root = archive_root.resolve() if archive_root else None
    for root, dirs, files in os.walk(source):
        root_path = Path(root)
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
        if archive_root and (root_path == archive_root or archive_root in root_path.parents):
            dirs[:] = []
            continue
        for filename in files:
            path = root_path / filename
            rel = path.relative_to(source)
            category = classify(path, rel, include_large, engine)
            if not category:
                continue
            selected.append(
                {
                    "source": path,
                    "relpath": rel.as_posix(),
                    "category": category,
                    "size": path.stat().st_size,
                    "sha256": file_sha256(path),
                }
            )
    return sorted(selected, key=lambda item: item["relpath"])


def load_or_create_result(source: Path, engine: str = "auto") -> dict[str, Any]:
    result_path = source / "result.json"
    if result_path.exists():
        try:
            loaded = json.loads(result_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                errors = validate_document("result-v1", loaded)
                if not errors:
                    return loaded
                legacy_result = loaded
            else:
                legacy_result = {"value": loaded}
        except json.JSONDecodeError:
            legacy_result = {"unparsed_result_path": str(result_path)}
    else:
        legacy_result = None
    engine = detect_engine(source) if engine == "auto" else engine
    result = {
        "schema_version": 1,
        "contract": "dft.result.v1",
        "generated_by": "vwm_archive.py",
        "engine": engine,
        "engine_version": None,
        "task_dir": str(source),
        "parser": {"name": "dft-work-manager.minimal-record", "version": "1.0.0"},
        "termination": {"normal": False, "status": "unknown"},
        "convergence": {"electronic": None, "ionic": None},
        "source_files": [],
        "warnings": ["no validated dft-analysis result.json was available at archive time"],
        "confidence": "provisional",
        "generated_at": utc_now(),
    }
    if legacy_result is not None:
        result["legacy_result"] = legacy_result
        result["warnings"].append("existing result.json did not satisfy dft.result.v1 and was retained under legacy_result")
    errors = validate_document("result-v1", result)
    if errors:
        raise RuntimeError("minimal result violates shared contract: " + "; ".join(errors))
    return result


def load_design_provenance(source: Path) -> dict[str, Any]:
    task_spec = load_task_spec(source)
    provenance = task_spec.get("design_provenance") if isinstance(task_spec, dict) else None
    return provenance if isinstance(provenance, dict) else {}


def load_task_spec(source: Path) -> dict[str, Any]:
    task_spec_path = source / "task_spec.json"
    if not task_spec_path.is_file():
        return {}
    try:
        loaded = json.loads(task_spec_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def load_json_file(path: Path) -> dict[str, Any]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def domain_archive_context(source: Path, copied: list[dict[str, Any]]) -> dict[str, Any]:
    task_spec = load_task_spec(source)
    provenance = task_spec.get("design_provenance") if isinstance(task_spec.get("design_provenance"), dict) else {}
    metadata = task_spec.get("domain_metadata") if isinstance(task_spec.get("domain_metadata"), dict) else {}
    context = task_spec.get("domain_context") if isinstance(task_spec.get("domain_context"), dict) else {}
    fixed = context.get("matrix_fixed_parameters") if isinstance(context.get("matrix_fixed_parameters"), dict) else {}
    reference_cases = metadata.get("reference_cases") if isinstance(metadata.get("reference_cases"), (dict, list)) else {}
    analysis_products = [
        item for item in copied
        if item["category"] in {"plot_data", "metadata"}
        and item["relpath"].startswith(("analysis/", "9analysis/", "6analysis/"))
    ]
    energy_tables = [
        item for item in copied
        if Path(item["relpath"]).name in {
            "formation_energy.dat",
            "surface_energy.dat",
            "adsorption_energy.dat",
            "interface_adhesion.dat",
            "work_function.dat",
            "bader_charge.dat",
            "charge_density_difference.dat",
        }
    ]
    structure_versions = [
        item for item in copied
        if Path(item["relpath"]).name in {
            "POSCAR", "POSCAR-ini", "CONTCAR", "structure.xyz", "structure.cif",
            "input_structure.xyz", "output_structure.xyz",
        }
    ]
    return {
        "domain_pack": task_spec.get("domain_pack") or provenance.get("domain_pack"),
        "reference_cases": reference_cases,
        "reference_case": fixed.get("reference_case") or (
            reference_cases.get("bulk_reference") if isinstance(reference_cases, dict) else None
        ),
        "variant_case": task_spec.get("case_slug"),
        "analysis_products": analysis_products,
        "energy_tables": energy_tables,
        "structure_versions": structure_versions,
    }


def copy_selected(selected: list[dict[str, Any]], source: Path, dest: Path) -> list[dict[str, Any]]:
    copied: list[dict[str, Any]] = []
    for item in selected:
        rel = Path(item["relpath"])
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item["source"], target)
        copied.append({key: value for key, value in item.items() if key != "source"})
    return copied


def write_archive_files(
    *,
    source: Path,
    dest: Path,
    project: str,
    task: str,
    system_slug: str | None,
    case_slug: str | None,
    cluster: str | None,
    task_state: str,
    review_status: str,
    notes: str | None,
    copied: list[dict[str, Any]],
    result: dict[str, Any],
    engine: str = "auto",
) -> dict[str, Any]:
    engine = detect_engine(source) if engine == "auto" else engine
    dest.mkdir(parents=True, exist_ok=True)
    result_path = dest / "result.json"
    if not result_path.exists():
        result_path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
        copied.append(
            {
                "relpath": "result.json",
                "category": "result_summary",
                "size": result_path.stat().st_size,
                "sha256": file_sha256(result_path),
            }
        )

    plot_data = [
        item for item in copied
        if item["category"] in {"plot_data", "plot_source", "metadata"}
        or Path(item["relpath"]).suffix.lower() in PLOT_DATA_EXTS
    ]
    scientific_design = load_design_provenance(source)
    scientific_design_files = [item for item in copied if item["category"] == "scientific_design"]
    domain_context = domain_archive_context(source, copied)
    calculation_fingerprint = compute_fingerprint(source, result)
    manifest = {
        "schema": "dft-work-manager.archive.v3",
        "engine": engine,
        "project": project,
        "task": task,
        "system_slug": system_slug,
        "case_slug": case_slug,
        "cluster": cluster,
        "task_state": task_state,
        "review_status": review_status,
        "notes": notes,
        "source_path": str(source),
        "archive_path": str(dest),
        "created_at": utc_now(),
        "files": copied,
        "plot_data": plot_data,
        "scientific_design": scientific_design,
        "scientific_design_files": scientific_design_files,
        "domain_context": domain_context,
        "calculation_fingerprint": calculation_fingerprint,
    }
    contract_errors = validate_document("archive-manifest-v3", manifest)
    if contract_errors:
        raise RuntimeError("archive manifest violates v3 contract: " + "; ".join(contract_errors))
    manifest_path = dest / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")

    sums = []
    for item in copied:
        sums.append(f"{item['sha256']}  {item['relpath']}")
    sums.append(f"{file_sha256(manifest_path)}  manifest.json")
    (dest / "SHA256SUMS").write_text("\n".join(sums) + "\n", encoding="utf-8")
    return manifest


def make_zip(dest: Path) -> Path:
    zip_path = dest.with_suffix(".zip")
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(p for p in dest.rglob("*") if p.is_file()):
            zf.write(path, path.relative_to(dest))
    return zip_path


def register_evidence_chain(
    conn: Any,
    *,
    project: str,
    task: str,
    calculation_node: Any,
    manifest: dict[str, Any],
    result: dict[str, Any],
    archive_dir: Path,
) -> None:
    def node(node_type: str, label: str, payload: dict[str, Any]) -> Any:
        return register_provenance_node(
            conn,
            project=project,
            task=task,
            fingerprint=artifact_fingerprint(node_type, payload),
            node_type=node_type,
            label=label,
        )

    matrix_node = None
    design_files = [
        archive_dir / item["relpath"]
        for item in manifest.get("scientific_design_files", [])
        if Path(item["relpath"]).name == "calculation_design.json"
    ]
    design = load_json_file(design_files[0]) if design_files and design_files[0].is_file() else {}
    provenance = manifest.get("scientific_design", {})
    matrix_id = provenance.get("matrix_id")
    matrices = [item for item in design.get("calculation_matrix", []) if item.get("id") == matrix_id]
    matrix = matrices[0] if matrices else ({"id": matrix_id} if matrix_id else None)
    if matrix:
        matrix_node = node(
            "design_matrix",
            f"{design.get('design_id') or provenance.get('design_id') or 'design'}:{matrix_id}",
            {"design_id": design.get("design_id") or provenance.get("design_id"), "revision": design.get("revision") or provenance.get("design_revision"), "matrix": matrix},
        )
        add_provenance_edge(
            conn, parent_node_id=int(matrix_node["id"]), child_node_id=int(calculation_node["id"]), relation="authorizes"
        )
        hypothesis_ids = matrix.get("hypothesis_ids", []) if isinstance(matrix, dict) else []
        for hypothesis in design.get("hypotheses", []):
            if hypothesis.get("id") not in hypothesis_ids:
                continue
            hypothesis_node = node("hypothesis", str(hypothesis.get("id")), hypothesis)
            add_provenance_edge(
                conn, parent_node_id=int(hypothesis_node["id"]), child_node_id=int(matrix_node["id"]), relation="motivates"
            )

    result_node = node(
        "parsed_result",
        f"{task}:result",
        {"engine": manifest.get("engine"), "result": result, "generator": result.get("parser")},
    )
    add_provenance_edge(
        conn, parent_node_id=int(calculation_node["id"]), child_node_id=int(result_node["id"]), relation="produces"
    )
    plot_nodes = []
    figure_nodes = []
    for item in manifest.get("files", []):
        suffix = Path(item["relpath"]).suffix.lower()
        if item.get("category") in {"plot_data", "plot_source"} and suffix not in {".png", ".pdf", ".svg"}:
            plot_node = node("plot_data", item["relpath"], item)
            plot_nodes.append(plot_node)
            add_provenance_edge(
                conn, parent_node_id=int(result_node["id"]), child_node_id=int(plot_node["id"]), relation="transforms_to"
            )
        if suffix in {".png", ".pdf", ".svg"}:
            figure_node = node("figure", item["relpath"], item)
            figure_nodes.append(figure_node)
            parents = plot_nodes or [result_node]
            for parent in parents:
                add_provenance_edge(
                    conn, parent_node_id=int(parent["id"]), child_node_id=int(figure_node["id"]), relation="visualizes"
                )
    claims = result.get("claims", []) if isinstance(result.get("claims"), list) else []
    for index, claim in enumerate(claims, start=1):
        payload = claim if isinstance(claim, dict) else {"statement": str(claim)}
        claim_node = node("scientific_claim", str(payload.get("statement") or f"claim-{index}"), payload)
        for parent in figure_nodes or plot_nodes or [result_node]:
            add_provenance_edge(
                conn, parent_node_id=int(parent["id"]), child_node_id=int(claim_node["id"]), relation="supports"
            )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="vwm_archive.py")
    parser.add_argument("--source", required=True, help="DFT calculation directory.")
    parser.add_argument(
        "--engine",
        choices=("auto", "vasp", "quantum-espresso", "cp2k", "abinit", "gpaw", "other"),
        default="auto",
    )
    parser.add_argument("--project", required=True)
    parser.add_argument("--task", required=True)
    parser.add_argument("--system-slug", help="Managed layout system slug (lowercase_snake_case).")
    parser.add_argument("--case-slug", help="Managed layout case slug (lowercase_snake_case).")
    parser.add_argument("--archive-root", required=True)
    parser.add_argument("--ledger", help="SQLite ledger path. Default: <archive-root>/vwm.sqlite")
    parser.add_argument("--cluster")
    parser.add_argument("--task-type")
    parser.add_argument("--state", default="COMPLETED")
    parser.add_argument("--engine-status", default="UNKNOWN")
    parser.add_argument("--vasp-status", default=None, help="Legacy alias for --engine-status.")
    parser.add_argument("--parse-status", default="NOT_PARSED")
    parser.add_argument("--review-status", default="NEEDS_REVIEW")
    parser.add_argument("--notes")
    parser.add_argument("--include-large", action="store_true", help="Include WAVECAR/CHGCAR/vasprun.xml/XDATCAR.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--zip", action="store_true", help="Also create a .zip copy of the archive version.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    source = Path(args.source).expanduser().resolve()
    if not source.is_dir():
        raise FileNotFoundError(f"Source directory not found: {source}")
    archive_root = Path(args.archive_root).expanduser().resolve()
    engine = detect_engine(source) if args.engine == "auto" else args.engine
    managed_layout = bool(args.system_slug or args.case_slug)
    ledger = (
        Path(args.ledger).expanduser().resolve()
        if args.ledger
        else (archive_root.parent / "ledger" / "vwm.sqlite" if managed_layout else archive_root / "vwm.sqlite")
    )
    dest = archive_destination(
        archive_root,
        args.project,
        args.task,
        stamp(),
        system_slug=args.system_slug,
        case_slug=args.case_slug,
    )

    selected = collect(source, args.include_large, archive_root=archive_root, engine=engine)
    print(f"Selected {len(selected)} file(s) from {source}")
    for item in selected:
        print(f"{item['category']:14s} {item['size']:10d} {item['relpath']}")
    if args.dry_run:
        print(f"Dry run only. Archive target would be: {dest}")
        return 0

    copied = copy_selected(selected, source, dest)
    result = load_or_create_result(source, engine)
    manifest = write_archive_files(
        source=source,
        dest=dest,
        project=args.project,
        task=args.task,
        system_slug=args.system_slug,
        case_slug=args.case_slug,
        cluster=args.cluster,
        task_state=args.state,
        review_status=args.review_status,
        notes=args.notes,
        copied=copied,
        result=result,
        engine=engine,
    )
    zip_path = make_zip(dest) if args.zip else None
    design_provenance = manifest.get("scientific_design", {})
    domain_context = manifest.get("domain_context", {})

    init_db(ledger)
    with connect(ledger) as conn:
        register_task(
            conn,
            project=args.project,
            task=args.task,
            source_path=str(source),
            cluster=args.cluster,
            task_type=args.task_type,
            task_state=args.state,
            engine=engine,
        )
        row = update_task(
            conn,
            project=args.project,
            task=args.task,
            fields={
                "archive_path": str(dest),
                "task_state": args.state,
                "engine": engine,
                "engine_status": args.vasp_status or args.engine_status,
                "vasp_status": args.vasp_status or (args.engine_status if engine == "vasp" else None),
                "parse_status": args.parse_status,
                "review_status": args.review_status,
                "notes": args.notes,
                "design_id": design_provenance.get("design_id"),
                "design_revision": design_provenance.get("design_revision"),
                "design_matrix_id": design_provenance.get("matrix_id"),
                "domain_pack": domain_context.get("domain_pack"),
                "reference_case": domain_context.get("reference_case"),
                "variant_case": domain_context.get("variant_case"),
                "result_json": json.dumps(result, sort_keys=True),
                "archived_at": utc_now(),
            },
            event_type="task.archived",
            message=f"Archived task to {dest}.",
        )
        record_files(conn, project=args.project, task=args.task, archive_path=str(dest), files=manifest["files"])
        fingerprint = manifest["calculation_fingerprint"]
        node = register_provenance_node(
            conn,
            project=args.project,
            task=args.task,
            fingerprint=fingerprint,
            label=args.task,
        )
        for parent_fingerprint in fingerprint.get("parent_fingerprints", []):
            parent_rows = conn.execute(
                "SELECT id FROM provenance_nodes WHERE project_id = ? AND fingerprint = ? ORDER BY id DESC",
                (node["project_id"], parent_fingerprint),
            ).fetchall()
            for parent_row in parent_rows:
                add_provenance_edge(
                    conn,
                    parent_node_id=int(parent_row["id"]),
                    child_node_id=int(node["id"]),
                )
        register_evidence_chain(
            conn,
            project=args.project,
            task=args.task,
            calculation_node=node,
            manifest=manifest,
            result=result,
            archive_dir=dest,
        )
        add_event(
            conn,
            int(row["id"]),
            "archive.created",
            f"Archive created at {dest}.",
            {"archive_path": str(dest), "zip_path": str(zip_path) if zip_path else None},
        )

    print(f"Archive: {dest}")
    print(f"Ledger: {ledger}")
    if zip_path:
        print(f"Zip: {zip_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
