#!/usr/bin/env python3
"""Export VASP Work Manager ledger rows as CSV, JSON, or Markdown."""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any


COLUMNS = [
    "project",
    "task",
    "cluster",
    "task_type",
    "task_state",
    "vasp_status",
    "parse_status",
    "review_status",
    "review_note",
    "notes",
    "source_path",
    "archive_path",
    "file_count",
    "plot_file_count",
    "analysis_files",
    "created_at",
    "updated_at",
    "archived_at",
]


def connect(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(Path(db_path).expanduser().resolve())
    conn.row_factory = sqlite3.Row
    return conn


def rows(conn: sqlite3.Connection, project: str | None = None) -> list[dict[str, Any]]:
    params: list[Any] = []
    where = ""
    if project:
        where = "WHERE p.name = ?"
        params.append(project)
    query = f"""
        SELECT
            p.name AS project,
            t.name AS task,
            t.cluster,
            t.task_type,
            t.task_state,
            t.vasp_status,
            t.parse_status,
            t.review_status,
            t.review_note,
            t.notes,
            t.source_path,
            t.archive_path,
            t.created_at,
            t.updated_at,
            t.archived_at,
            COUNT(fr.relpath) AS file_count,
            SUM(CASE WHEN fr.category IN ('plot_data', 'plot_source') THEN 1 ELSE 0 END) AS plot_file_count,
            GROUP_CONCAT(
                CASE
                    WHEN fr.category IN ('plot_data', 'plot_source')
                    THEN fr.relpath
                    ELSE NULL
                END,
                '; '
            ) AS analysis_files
        FROM tasks t
        JOIN projects p ON p.id = t.project_id
        LEFT JOIN file_records fr ON fr.task_id = t.id AND fr.archive_path = t.archive_path
        {where}
        GROUP BY t.id
        ORDER BY p.name, t.name
    """
    return [{key: row[key] for key in row.keys()} for row in conn.execute(query, params)]


def write_csv(data: list[dict[str, Any]], output: Path | None) -> None:
    handle = output.open("w", newline="", encoding="utf-8") if output else sys.stdout
    close = output is not None
    try:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(data)
    finally:
        if close:
            handle.close()


def write_json(data: list[dict[str, Any]], output: Path | None) -> None:
    text = json.dumps(data, indent=2, sort_keys=True)
    if output:
        output.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)


def markdown_cell(value: Any) -> str:
    return str(value or "").replace("|", "\\|").replace("\n", " ")


def write_markdown(data: list[dict[str, Any]], output: Path | None, project: str | None) -> None:
    lines = [
        f"# {project or 'VASP'} Project Summary",
        "",
        "| task | state | source_case | analysis_files | archive | review | conclusion/notes |",
        "|---|---|---|---|---|---|---|",
    ]
    for item in data:
        lines.append(
            "| "
            + " | ".join(
                markdown_cell(item.get(key))
                for key in (
                    "task",
                    "task_state",
                    "source_path",
                    "analysis_files",
                    "archive_path",
                    "review_status",
                    "notes",
                )
            )
            + " |"
        )
    text = "\n".join(lines) + "\n"
    if output:
        output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="vwm_report.py")
    parser.add_argument("--ledger", required=True)
    parser.add_argument("--project")
    parser.add_argument("--format", choices=["csv", "json", "markdown"], default="csv")
    parser.add_argument("--output")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output = Path(args.output).expanduser().resolve() if args.output else None
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
    with connect(args.ledger) as conn:
        data = rows(conn, args.project)
    if args.format == "csv":
        write_csv(data, output)
    elif args.format == "json":
        write_json(data, output)
    else:
        write_markdown(data, output, args.project)
    if output:
        print(f"Wrote {len(data)} row(s) to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
