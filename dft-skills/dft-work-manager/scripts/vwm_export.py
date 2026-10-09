#!/usr/bin/env python3
"""Export local DFT records as explicit, non-destructive interchange bundles."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from vwm_ledger import connect, init_db, provenance_graph, row_dict


PROFILES = ("nomad", "aiida", "atomate2", "research-teach", "talk-materials")


def parsed(value: str | None) -> Any:
    try:
        return json.loads(value or "{}")
    except json.JSONDecodeError:
        return {"unparsed": value}


def collect_bundle(ledger: Path, project: str) -> dict[str, Any]:
    init_db(ledger)
    with connect(ledger) as conn:
        tasks = [
            row_dict(row)
            for row in conn.execute(
                """
                SELECT t.*, p.name AS project_name FROM tasks t
                JOIN projects p ON p.id = t.project_id
                WHERE p.name = ? ORDER BY t.name
                """,
                (project,),
            )
        ]
        task_ids = [int(item["id"]) for item in tasks]
        files: list[dict[str, Any]] = []
        if task_ids:
            marks = ",".join("?" for _ in task_ids)
            files = [
                row_dict(row)
                for row in conn.execute(
                    f"SELECT * FROM file_records WHERE task_id IN ({marks}) ORDER BY task_id, relpath",
                    task_ids,
                )
            ]
        graph = provenance_graph(conn, project)
    by_task: dict[int, list[dict[str, Any]]] = {}
    for item in files:
        by_task.setdefault(int(item["task_id"]), []).append(item)
    for task in tasks:
        task["result"] = parsed(task.pop("result_json", "{}"))
        task["files"] = by_task.get(int(task["id"]), [])
    return {
        "schema": "dft.interchange.v1",
        "project": project,
        "source_ledger": str(ledger.resolve()),
        "tasks": tasks,
        "provenance": graph,
    }


def nomad_profile(bundle: dict[str, Any]) -> dict[str, Any]:
    return {
        "profile": "nomad-staging-v1",
        "note": "Staging metadata only; validate with the installed NOMAD version before upload.",
        "project": bundle["project"],
        "entries": [
            {
                "entry_name": task["name"],
                "mainfile_candidates": [
                    item["relpath"] for item in task["files"]
                    if Path(item["relpath"]).name in {"OUTCAR", "vasprun.xml", "pw.out", "scf.out"}
                ],
                "code_name": task["engine"],
                "source_archive": task.get("archive_path"),
                "design": {
                    "id": task.get("design_id"),
                    "revision": task.get("design_revision"),
                    "matrix_id": task.get("design_matrix_id"),
                },
            }
            for task in bundle["tasks"]
        ],
    }


def aiida_profile(bundle: dict[str, Any]) -> dict[str, Any]:
    return {
        "profile": "aiida-provenance-interchange-v1",
        "note": "Neutral provenance bundle; importing into an AiiDA profile requires a version-specific adapter.",
        "project": bundle["project"],
        "nodes": bundle["provenance"]["nodes"],
        "links": bundle["provenance"]["edges"],
    }


def atomate2_profile(bundle: dict[str, Any]) -> dict[str, Any]:
    return {
        "profile": "atomate2-task-document-interchange-v1",
        "note": "TaskDocument-like interchange, not a serialized atomate2 Python object.",
        "task_documents": [
            {
                "task_label": task["name"],
                "state": task["task_state"],
                "engine": task["engine"],
                "task_type": task.get("task_type"),
                "output": task["result"],
                "source_path": task.get("source_path"),
                "archive_path": task.get("archive_path"),
            }
            for task in bundle["tasks"]
        ],
    }


def research_markdown(bundle: dict[str, Any]) -> str:
    lines = [f"# {bundle['project']} — DFT Evidence Index", "", "本文件由本地 ledger 导出；所有结论需回到归档和原始输出核验。", ""]
    for task in bundle["tasks"]:
        lines.extend([
            f"## {task['name']}", "",
            f"- Engine: `{task['engine']}`",
            f"- State: `{task['task_state']}`",
            f"- Review: `{task['review_status']}`",
            f"- Design: `{task.get('design_id') or 'unknown'} / {task.get('design_revision') or 'unknown'} / {task.get('design_matrix_id') or 'unknown'}`",
            f"- Archive: `{task.get('archive_path') or 'not archived'}`", "",
        ])
        claims = task["result"].get("claims", []) if isinstance(task["result"], dict) else []
        for claim in claims:
            statement = claim.get("statement") if isinstance(claim, dict) else str(claim)
            lines.append(f"- Claim: {statement}")
        lines.append("")
    return "\n".join(lines)


def talk_profile(bundle: dict[str, Any]) -> dict[str, Any]:
    accepted = [task for task in bundle["tasks"] if task.get("review_status") == "ACCEPTED"]
    return {
        "profile": "dft-talk-materials-v1",
        "project": bundle["project"],
        "accepted_tasks": [
            {
                "task": task["name"],
                "engine": task["engine"],
                "result": task["result"],
                "figures": [
                    item["relpath"] for item in task["files"]
                    if Path(item["relpath"]).suffix.lower() in {".png", ".pdf", ".svg"}
                ],
                "archive_path": task.get("archive_path"),
            }
            for task in accepted
        ],
    }


def export(profile: str, bundle: dict[str, Any], output: Path) -> None:
    if output.exists():
        raise FileExistsError(f"refusing to overwrite: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    if profile == "research-teach":
        output.write_text(research_markdown(bundle), encoding="utf-8")
        return
    value = {
        "nomad": nomad_profile,
        "aiida": aiida_profile,
        "atomate2": atomate2_profile,
        "talk-materials": talk_profile,
    }[profile](bundle)
    output.write_text(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="vwm_export.py")
    parser.add_argument("profile", choices=PROFILES)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--project", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    export(args.profile, collect_bundle(args.ledger, args.project), args.output)
    print(f"[ok] {args.profile} export: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
