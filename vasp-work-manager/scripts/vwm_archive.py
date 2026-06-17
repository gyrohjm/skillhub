#!/usr/bin/env python3
"""Archive VASP task directories and update the VASP Work Manager ledger."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from hashlib import sha256

from vwm_ledger import add_event, connect, init_db, record_files, register_task, update_task


CORE_NAMES = {
    "POSCAR",
    "INCAR",
    "KPOINTS",
    "POTCAR",
    "job.sh",
    "submit.slurm",
    "run_vasp.sh",
    "OUTCAR",
    "OSZICAR",
    "CONTCAR",
    "vasp.out",
    "vasp.err",
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
LARGE_NAMES = {"WAVECAR", "CHGCAR", "vasprun.xml", "XDATCAR", "ELFCAR", "PARCHG"}
SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", ".mypy_cache"}
INTERNAL_ARCHIVE_NAMES = {"manifest.json", "SHA256SUMS"}

FLOAT = r"[+-]?(?:(?:\d+\.\d*)|(?:\.\d+)|(?:\d+))(?:[EeDd][+-]?\d+)?"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def safe_slug(value: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip())
    return clean.strip("-") or "unnamed"


def file_sha256(path: Path) -> str:
    h = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def tail_text(path: Path, limit: int = 4 * 1024 * 1024) -> str:
    if not path.exists() or not path.is_file():
        return ""
    size = path.stat().st_size
    with path.open("rb") as handle:
        if size > limit:
            handle.seek(size - limit)
        return handle.read().decode("utf-8", errors="replace")


def classify(path: Path, rel: Path, include_large: bool) -> str | None:
    name = path.name
    if rel.parent == Path(".") and name in INTERNAL_ARCHIVE_NAMES:
        return None
    if name in LARGE_NAMES and not include_large:
        return None
    if name in LARGE_NAMES:
        return "large"
    if name in CORE_NAMES:
        return "core"
    if name in PLOT_SOURCE_NAMES:
        return "plot_source"
    if path.suffix.lower() in PLOT_DATA_EXTS:
        return "plot_data"
    if path.suffix.lower() in METADATA_EXTS:
        return "metadata"
    return None


def collect(source: Path, include_large: bool, archive_root: Path | None = None) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    source = source.resolve()
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
            category = classify(path, rel, include_large)
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


def parse_oszicar(source: Path) -> dict[str, Any]:
    text = tail_text(source / "OSZICAR")
    if not text:
        return {}
    f_matches = re.findall(rf"\bF=\s*({FLOAT})", text)
    e0_matches = re.findall(rf"\bE0=\s*({FLOAT})", text)
    data: dict[str, Any] = {}
    if f_matches:
        data["final_energy"] = float(f_matches[-1].replace("D", "E").replace("d", "e"))
    if e0_matches:
        data["e0_energy"] = float(e0_matches[-1].replace("D", "E").replace("d", "e"))
    return data


def parse_outcar(source: Path) -> dict[str, Any]:
    text = tail_text(source / "OUTCAR")
    if not text:
        return {}
    data: dict[str, Any] = {}
    toten = re.findall(rf"TOTEN\s*=\s*({FLOAT})", text)
    if toten:
        data["outcar_toten"] = float(toten[-1].replace("D", "E").replace("d", "e"))
    efermi = re.findall(rf"E-fermi\s*:\s*({FLOAT})", text)
    if efermi:
        data["fermi_energy"] = float(efermi[-1].replace("D", "E").replace("d", "e"))
    nions = re.findall(r"NIONS\s*=\s*(\d+)", text)
    if nions:
        data["nions"] = int(nions[-1])
    data["converged_hint"] = "reached required accuracy" in text
    hints = []
    for needle in ("VERY BAD NEWS", "ZBRENT", "BRMIX", "ERROR", "Error"):
        if needle in text:
            hints.append(needle)
    if hints:
        data["error_hints"] = sorted(set(hints))
    return data


def load_or_create_result(source: Path) -> dict[str, Any]:
    result_path = source / "result.json"
    if result_path.exists():
        try:
            loaded = json.loads(result_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                return loaded
        except json.JSONDecodeError:
            pass
    result = {"generated_by": "vwm_archive.py", "source_path": str(source), "generated_at": utc_now()}
    result.update(parse_oszicar(source))
    result.update(parse_outcar(source))
    return result


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
    cluster: str | None,
    task_state: str,
    review_status: str,
    notes: str | None,
    copied: list[dict[str, Any]],
    result: dict[str, Any],
) -> dict[str, Any]:
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
    manifest = {
        "schema": "vasp-work-manager.archive.v1",
        "project": project,
        "task": task,
        "cluster": cluster,
        "task_state": task_state,
        "review_status": review_status,
        "notes": notes,
        "source_path": str(source),
        "archive_path": str(dest),
        "created_at": utc_now(),
        "files": copied,
        "plot_data": plot_data,
    }
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="vwm_archive.py")
    parser.add_argument("--source", required=True, help="VASP calculation directory.")
    parser.add_argument("--project", required=True)
    parser.add_argument("--task", required=True)
    parser.add_argument("--archive-root", required=True)
    parser.add_argument("--ledger", help="SQLite ledger path. Default: <archive-root>/vwm.sqlite")
    parser.add_argument("--cluster")
    parser.add_argument("--task-type")
    parser.add_argument("--state", default="COMPLETED")
    parser.add_argument("--vasp-status", default="UNKNOWN")
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
    ledger = Path(args.ledger).expanduser().resolve() if args.ledger else archive_root / "vwm.sqlite"
    dest = archive_root / safe_slug(args.project) / safe_slug(args.task) / stamp()

    selected = collect(source, args.include_large, archive_root=archive_root)
    print(f"Selected {len(selected)} file(s) from {source}")
    for item in selected:
        print(f"{item['category']:14s} {item['size']:10d} {item['relpath']}")
    if args.dry_run:
        print(f"Dry run only. Archive target would be: {dest}")
        return 0

    copied = copy_selected(selected, source, dest)
    result = load_or_create_result(source)
    manifest = write_archive_files(
        source=source,
        dest=dest,
        project=args.project,
        task=args.task,
        cluster=args.cluster,
        task_state=args.state,
        review_status=args.review_status,
        notes=args.notes,
        copied=copied,
        result=result,
    )
    zip_path = make_zip(dest) if args.zip else None

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
        )
        row = update_task(
            conn,
            project=args.project,
            task=args.task,
            fields={
                "archive_path": str(dest),
                "task_state": args.state,
                "vasp_status": args.vasp_status,
                "parse_status": args.parse_status,
                "review_status": args.review_status,
                "notes": args.notes,
                "result_json": json.dumps(result, sort_keys=True),
                "archived_at": utc_now(),
            },
            event_type="task.archived",
            message=f"Archived task to {dest}.",
        )
        record_files(conn, project=args.project, task=args.task, archive_path=str(dest), files=manifest["files"])
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
