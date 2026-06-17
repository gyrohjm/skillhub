#!/usr/bin/env python3
"""Small SQLite task ledger for VASP work directories."""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    source_path TEXT,
    archive_path TEXT,
    cluster TEXT,
    task_type TEXT,
    task_state TEXT NOT NULL DEFAULT 'IMPORTED',
    vasp_status TEXT NOT NULL DEFAULT 'UNKNOWN',
    parse_status TEXT NOT NULL DEFAULT 'NOT_PARSED',
    review_status TEXT NOT NULL DEFAULT 'NEEDS_REVIEW',
    review_note TEXT,
    notes TEXT,
    result_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    archived_at TEXT,
    UNIQUE(project_id, name),
    FOREIGN KEY(project_id) REFERENCES projects(id)
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    message TEXT,
    data_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY(task_id) REFERENCES tasks(id)
);

CREATE TABLE IF NOT EXISTS file_records (
    task_id INTEGER NOT NULL,
    archive_path TEXT NOT NULL,
    relpath TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    size INTEGER NOT NULL,
    category TEXT NOT NULL,
    archived_at TEXT NOT NULL,
    PRIMARY KEY (task_id, archive_path, relpath),
    FOREIGN KEY(task_id) REFERENCES tasks(id)
);
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def connect(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: str | Path) -> None:
    with connect(db_path) as conn:
        conn.executescript(SCHEMA)


def row_dict(row: sqlite3.Row | None) -> dict[str, Any]:
    if row is None:
        return {}
    return {key: row[key] for key in row.keys()}


def ensure_project(conn: sqlite3.Connection, name: str) -> int:
    now = utc_now()
    conn.execute(
        "INSERT OR IGNORE INTO projects (name, created_at) VALUES (?, ?)",
        (name, now),
    )
    row = conn.execute("SELECT id FROM projects WHERE name = ?", (name,)).fetchone()
    if row is None:
        raise RuntimeError(f"Could not create or find project: {name}")
    return int(row["id"])


def get_task(conn: sqlite3.Connection, project: str, task: str) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT t.*, p.name AS project_name
        FROM tasks t
        JOIN projects p ON p.id = t.project_id
        WHERE p.name = ? AND t.name = ?
        """,
        (project, task),
    ).fetchone()


def add_event(
    conn: sqlite3.Connection,
    task_id: int,
    event_type: str,
    message: str | None = None,
    data: dict[str, Any] | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO events (task_id, event_type, message, data_json, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (task_id, event_type, message, json.dumps(data or {}, sort_keys=True), utc_now()),
    )


def register_task(
    conn: sqlite3.Connection,
    *,
    project: str,
    task: str,
    source_path: str | None = None,
    cluster: str | None = None,
    task_type: str | None = None,
    task_state: str = "IMPORTED",
) -> sqlite3.Row:
    project_id = ensure_project(conn, project)
    now = utc_now()
    existing = get_task(conn, project, task)
    conn.execute(
        """
        INSERT INTO tasks
            (project_id, name, source_path, cluster, task_type, task_state,
             created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(project_id, name) DO UPDATE SET
            source_path = COALESCE(excluded.source_path, source_path),
            cluster = COALESCE(excluded.cluster, cluster),
            task_type = COALESCE(excluded.task_type, task_type),
            task_state = excluded.task_state,
            updated_at = excluded.updated_at
        """,
        (project_id, task, source_path, cluster, task_type, task_state, now, now),
    )
    row = get_task(conn, project, task)
    if row is None:
        raise RuntimeError(f"Could not register task: {project}/{task}")
    add_event(
        conn,
        int(row["id"]),
        "task.updated" if existing else "task.registered",
        f"{'Updated' if existing else 'Registered'} task {project}/{task}.",
        {"source_path": source_path, "cluster": cluster, "task_type": task_type, "task_state": task_state},
    )
    return row


def update_task(
    conn: sqlite3.Connection,
    *,
    project: str,
    task: str,
    fields: dict[str, Any],
    event_type: str = "task.updated",
    message: str | None = None,
) -> sqlite3.Row:
    row = get_task(conn, project, task)
    if row is None:
        raise KeyError(f"Task not found: {project}/{task}")
    allowed = {
        "source_path",
        "archive_path",
        "cluster",
        "task_type",
        "task_state",
        "vasp_status",
        "parse_status",
        "review_status",
        "review_note",
        "notes",
        "result_json",
        "archived_at",
    }
    clean = {key: value for key, value in fields.items() if key in allowed and value is not None}
    if clean:
        clean["updated_at"] = utc_now()
        set_clause = ", ".join(f"{key} = ?" for key in clean)
        conn.execute(
            f"UPDATE tasks SET {set_clause} WHERE id = ?",
            [*clean.values(), row["id"]],
        )
    refreshed = get_task(conn, project, task)
    if refreshed is None:
        raise RuntimeError(f"Could not refresh task: {project}/{task}")
    add_event(conn, int(row["id"]), event_type, message or f"Updated task {project}/{task}.", clean)
    return refreshed


def record_files(
    conn: sqlite3.Connection,
    *,
    project: str,
    task: str,
    archive_path: str,
    files: list[dict[str, Any]],
) -> None:
    row = get_task(conn, project, task)
    if row is None:
        raise KeyError(f"Task not found: {project}/{task}")
    task_id = int(row["id"])
    now = utc_now()
    conn.execute(
        "DELETE FROM file_records WHERE task_id = ? AND archive_path = ?",
        (task_id, archive_path),
    )
    for item in files:
        conn.execute(
            """
            INSERT INTO file_records
                (task_id, archive_path, relpath, sha256, size, category, archived_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task_id,
                archive_path,
                item["relpath"],
                item["sha256"],
                int(item["size"]),
                item.get("category") or "unknown",
                now,
            ),
        )


def task_with_files(conn: sqlite3.Connection, project: str, task: str) -> dict[str, Any]:
    row = get_task(conn, project, task)
    if row is None:
        raise KeyError(f"Task not found: {project}/{task}")
    files = [
        row_dict(file_row)
        for file_row in conn.execute(
            """
            SELECT archive_path, relpath, sha256, size, category, archived_at
            FROM file_records
            WHERE task_id = ?
            ORDER BY archive_path DESC, relpath
            """,
            (row["id"],),
        )
    ]
    events = [
        row_dict(event_row)
        for event_row in conn.execute(
            """
            SELECT event_type, message, data_json, created_at
            FROM events
            WHERE task_id = ?
            ORDER BY id DESC
            LIMIT 20
            """,
            (row["id"],),
        )
    ]
    data = row_dict(row)
    data["files"] = files
    data["events"] = events
    return data


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="vwm_ledger.py")
    parser.add_argument(
        "--ledger",
        default="vwm-ledger.sqlite",
        help="SQLite ledger path. Default: ./vwm-ledger.sqlite",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="Initialize the ledger database.")

    register = sub.add_parser("register", help="Register or update a task.")
    register.add_argument("--project", required=True)
    register.add_argument("--task", required=True)
    register.add_argument("--source")
    register.add_argument("--cluster")
    register.add_argument("--task-type")
    register.add_argument("--state", default="IMPORTED")

    update = sub.add_parser("update", help="Update task status fields.")
    update.add_argument("--project", required=True)
    update.add_argument("--task", required=True)
    update.add_argument("--state")
    update.add_argument("--vasp-status")
    update.add_argument("--parse-status")
    update.add_argument("--archive-path")
    update.add_argument("--result-json")

    note = sub.add_parser("note", help="Set task notes.")
    note.add_argument("--project", required=True)
    note.add_argument("--task", required=True)
    note.add_argument("text", nargs="+")

    review = sub.add_parser("review", help="Record human review status.")
    review.add_argument("--project", required=True)
    review.add_argument("--task", required=True)
    review.add_argument("--status", required=True, choices=["NEEDS_REVIEW", "ACCEPTED", "REJECTED"])
    review.add_argument("--note")

    list_p = sub.add_parser("list", help="List tasks.")
    list_p.add_argument("--project")
    list_p.add_argument("--json", action="store_true")

    show = sub.add_parser("show", help="Show one task with files and events.")
    show.add_argument("--project", required=True)
    show.add_argument("--task", required=True)

    events = sub.add_parser("events", help="Show task events.")
    events.add_argument("--project", required=True)
    events.add_argument("--task", required=True)
    return parser


def print_rows(rows: list[dict[str, Any]]) -> None:
    if not rows:
        print("(none)")
        return
    columns = ["project_name", "name", "task_state", "vasp_status", "parse_status", "review_status", "archive_path"]
    widths = {col: max(len(col), *(len(str(row.get(col) or "")) for row in rows)) for col in columns}
    print("  ".join(col.ljust(widths[col]) for col in columns))
    print("  ".join("-" * widths[col] for col in columns))
    for row in rows:
        print("  ".join(str(row.get(col) or "").ljust(widths[col]) for col in columns))


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    init_db(args.ledger)
    with connect(args.ledger) as conn:
        if args.command == "init":
            print(f"Initialized ledger: {Path(args.ledger).expanduser().resolve()}")
            return 0

        if args.command == "register":
            row = register_task(
                conn,
                project=args.project,
                task=args.task,
                source_path=args.source,
                cluster=args.cluster,
                task_type=args.task_type,
                task_state=args.state,
            )
            print(json.dumps(row_dict(row), indent=2, sort_keys=True))
            return 0

        if args.command == "update":
            result_json = None
            if args.result_json:
                result_json = Path(args.result_json).read_text(encoding="utf-8")
            row = update_task(
                conn,
                project=args.project,
                task=args.task,
                fields={
                    "task_state": args.state,
                    "vasp_status": args.vasp_status,
                    "parse_status": args.parse_status,
                    "archive_path": args.archive_path,
                    "result_json": result_json,
                },
            )
            print(json.dumps(row_dict(row), indent=2, sort_keys=True))
            return 0

        if args.command == "note":
            row = update_task(
                conn,
                project=args.project,
                task=args.task,
                fields={"notes": " ".join(args.text)},
                event_type="task.notes",
                message="Notes updated.",
            )
            print(json.dumps(row_dict(row), indent=2, sort_keys=True))
            return 0

        if args.command == "review":
            row = update_task(
                conn,
                project=args.project,
                task=args.task,
                fields={"review_status": args.status, "review_note": args.note},
                event_type="task.reviewed",
                message=f"Review {args.status}.",
            )
            print(json.dumps(row_dict(row), indent=2, sort_keys=True))
            return 0

        if args.command == "list":
            params: list[Any] = []
            where = ""
            if args.project:
                where = "WHERE p.name = ?"
                params.append(args.project)
            rows = [
                row_dict(row)
                for row in conn.execute(
                    f"""
                    SELECT t.*, p.name AS project_name
                    FROM tasks t
                    JOIN projects p ON p.id = t.project_id
                    {where}
                    ORDER BY p.name, t.name
                    """,
                    params,
                )
            ]
            if args.json:
                print(json.dumps(rows, indent=2, sort_keys=True))
            else:
                print_rows(rows)
            return 0

        if args.command == "show":
            print(json.dumps(task_with_files(conn, args.project, args.task), indent=2, sort_keys=True))
            return 0

        if args.command == "events":
            task = get_task(conn, args.project, args.task)
            if task is None:
                raise KeyError(f"Task not found: {args.project}/{args.task}")
            rows = [
                row_dict(row)
                for row in conn.execute(
                    "SELECT * FROM events WHERE task_id = ? ORDER BY id DESC",
                    (task["id"],),
                )
            ]
            print(json.dumps(rows, indent=2, sort_keys=True))
            return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
