"""File-based project memory, task views and deterministic document destinations."""
from __future__ import annotations

import argparse
from contextlib import contextmanager, nullcontext
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import subprocess
import tempfile
from uuid import UUID

from .layout import (discover_workspace, ensure_within, PROJECT_FILE, project_routes,
                     route_for, workflow_paths, STAGE_RE, project_role, final_directory, stage_root)
from .privacy import findings, markers
from .core import validate_document, contract_path

NAME = re.compile(r"[a-z0-9]+(?:_[a-z0-9]+)*\Z")
TASK = re.compile(r"(?:p\d+(?:_[a-z0-9]+)*|rerun_\d{3,})\Z")
KINDS = {"report": "reports", "data": "plot_data", "figure": "figures"}
EXTENSIONS = {"report": {".md", ".json"}, "data": {".dat", ".csv", ".json", ".npz"},
              "figure": {".png", ".pdf", ".svg", ".jpg"}, "note": {".md"}}
START = "<!-- dft-project:start -->"
END = "<!-- dft-project:end -->"


def _safe(root: Path, relative: str | Path) -> Path:
    relative = Path(relative)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("Expected a workspace-relative path without parent traversal")
    target = root / relative
    for current in (target, *target.parents):
        if current == root:
            break
        if current.is_symlink():
            raise ValueError("Managed project paths must not contain symlinks")
    return ensure_within(root, target)


def _name(value: str) -> str:
    if not isinstance(value, str) or not NAME.fullmatch(value):
        raise ValueError("New names must use lowercase ASCII snake_case")
    return value


def _write(path: Path, text: str) -> None:
    if any(item.is_symlink() for item in (path, *path.parents)):
        raise ValueError("Managed writes must not follow symlinks")
    if path.is_file() and path.read_bytes() == text.encode("utf-8"):
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".dft-write-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


@contextmanager
def _lock(root: Path):
    path = _safe(root, ".dft/records.lock")
    path.parent.mkdir(exist_ok=True)
    with path.open("a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield


def _block(text: str, body: str, start=START, end=END) -> str:
    if text.count(start) != text.count(end) or text.count(start) > 1:
        raise ValueError("Malformed managed block; preserve and repair the existing document")
    block = f"{start}\n{body.rstrip()}\n{end}"
    if start in text:
        before, rest = text.split(start)
        _, after = rest.split(end)
        return before + block + after
    return text.rstrip() + "\n\n" + block + "\n"


def init_project(project_root: str | Path, layout=None) -> Path:
    root = Path(project_root).expanduser().resolve()
    if not root.is_dir():
        raise ValueError("Project root must already exist")
    role = project_role(root)
    if role == "cluster":
        raise ValueError("Initialize the cluster side through its paired local project")
    if role == "local":
        from .paired import endpoint_for, init_pair
        from .local_config import read_private_json
        binding = read_private_json(f"project-{json.loads((root / PROJECT_FILE).read_text())['project_id']}.json")
        endpoint = endpoint_for(root)
        init_pair(root, endpoint.root, ssh=endpoint.ssh, cluster=binding['cluster'])
        return root
    with _lock(root):
        if layout is None:
            layout = "routes" if (root / PROJECT_FILE).exists() or not (root / "calculations").exists() else "legacy"
        if layout not in {"routes", "legacy"}:
            raise ValueError("Unknown project layout")
        if layout == "routes" and not (root / PROJECT_FILE).exists():
            _write(root / PROJECT_FILE, json.dumps({"schema_version": 1, "routes": []}, indent=2) + "\n")
        for rel in (("calculations", "plans", "logs", "code", "docs") if layout == "legacy" else ()):
            _safe(root, rel).mkdir(exist_ok=True)
        memory = _safe(root, "MEMORY.md")
        if not memory.exists():
            _write(memory, "# Project Memory\n\nProject decisions, verified findings, open questions and next actions.\n"
                   "Task status comes from workflow.json; environment details stay in private local profiles.\n")
        agents = _safe(root, "AGENTS.md")
        old = agents.read_text() if agents.exists() else "# Project Instructions\n"
        body = """## DFT project records

At session start, read MEMORY.md and use dft-work-manager's scripts/dft_project.py
context --project-root . to retrieve current tasks from workflow.json.
Read dft-project.json for registered routes. Keep numbered stages directly under
each route; create shared/ only for actual common inputs. Legacy calculations trees
remain readable. Task analysis stays with its source task. results/ holds only the
unique main_report.md and selected final figures/tables with source provenance.
Use read then document --expected-sha256 to update fixed document roles in place;
use --section for one stable section, and event --key for idempotent log entries.
README explains purpose, dependencies, reading order and links; main_report owns the
project synthesis. Keep input snapshots immutable and Git history instead of copies.
Run screen before selecting, publishing or archiving results; rework-impact follows
dependencies but never decides scientific compatibility. Changes apply within the
current authorization; history and document updates do not grant permission to run.
After a meaningful decision or finding, use remember with a stable key and relative
evidence; revise that key when superseded. Save pending work as a next/question entry.
At handoff run sync then check. Keep unmarked human text intact. Read task status live;
MEMORY.md and README indexes do not authorize jobs or override scientific inputs.
Keep environment addresses, accounts, paths and resource details outside public records.
"""
        _write(agents, _block(old, body))
        readme = _safe(root, "README.md")
        if not readme.exists():
            _write(readme, "# DFT Project\n")
        for rel, body in {
            "results/README.md": "# Final results\n\nRead [the unique main report](main_report.md). Only selected final figures and tables belong here.\nSource data, scripts, intermediate conclusions and attempts remain in their task.\n",
            "results/main_report.md": "# Main report\n\n<!-- dft-role:main_report -->\n\nNo project conclusions have been published yet. Update stable sections with evidence.\n",
        }.items():
            path = _safe(root, rel)
            if not path.exists():
                _write(path, body)
        ignore = _safe(root, ".gitignore")
        text = ignore.read_text() if ignore.exists() else ""
        for rule in (".dft/", "/docs/project-resources.md", "*.local.*", "*.save/", "tmp/", "tmp_*/",
                     "WAVECAR", "CHGCAR", "POTCAR", "*.upf", "*.UPF", "*.wfc*", "epmat*", "*.out", "slurm-*", "job.sh", "qe.sh", "vasp.sh", "workflow.json", "attempts/"):
            if rule not in text.splitlines():
                text = text.rstrip() + "\n" + rule + "\n"
        _write(ignore, text)
    return root


def register_route(project_root, relative, composition, structure, *, locked=False) -> Path:
    root = discover_workspace(project_root)
    if project_role(root) == "cluster":
        raise ValueError("Register routes through the paired local initializer")
    route = {"path": Path(relative).as_posix(), "composition": _name(composition), "structure": _name(structure)}
    with nullcontext() if locked else _lock(root):
        path = _safe(root, PROJECT_FILE)
        if not path.exists():
            raise ValueError("Initialize a routes project before registering a route")
        data = json.loads(path.read_text())
        routes = project_routes(root)
        if route not in routes:
            target = _safe(root, relative)
            if not (target / "docs/plan.md").exists() and (target / "docs").is_dir():
                if any("plan" in p.stem.lower() and p.name != "README.md" for p in (target / "docs").rglob("*.md")):
                    raise ValueError("Existing plan documents need explicit consolidation before registering this route")
            for old in routes:
                other = root / old["path"]
                if target == other or target in other.parents or other in target.parents:
                    raise ValueError("Route registration conflicts with an existing route")
            if not Path(relative).parts or any(not NAME.fullmatch(p) for p in Path(relative).parts):
                raise ValueError("Route path requires lowercase snake_case components")
            if Path(relative).parts[0] in {"results", "analysis", "archive", "docs", "code", "shared"}:
                raise ValueError("Reserved route directory")
            data["routes"].append(route)
            _write(path, json.dumps(data, indent=2) + "\n")
        target = _safe(root, relative)
        for rel, description in {
            "README.md": "Research route. Describe purpose, stage order, dependencies, selected results and blockers.\n",
            "docs/plan.md": "Current route plan. Record the question, parameter choices, dependencies, acceptance and stopping criteria.\n",
            "docs/log.md": "Derived event timeline. workflow.json owns execution status.\n",
        }.items():
            dest = _safe(root, Path(relative) / rel)
            if not dest.exists():
                _write(dest, f"# {Path(rel).stem}\n\n{description}")
        return target


def task_context(task_root: str | Path) -> tuple[Path, Path, tuple[str, ...], dict]:
    task = Path(task_root).expanduser().absolute()
    root = discover_workspace(task)
    lexical_root = next((p for p in (task, *task.parents) if p.resolve() == root), None)
    if lexical_root is None:
        raise ValueError("Task path crosses a symlink outside its workspace")
    relative = task.relative_to(lexical_root)
    task = _safe(root, relative)
    parts = relative.parts
    route = route_for(task)
    if route:
        route_root, identity = route
        task_parts = task.relative_to(route_root).parts
        if not task_parts or not STAGE_RE.fullmatch(task_parts[0]):
            raise ValueError("Route tasks start with a numbered stage such as 03_scf")
        for part in task_parts:
            _name(part)
        if any(p in {"shared", "docs", "analysis", "scripts", "attempts"} for p in task_parts):
            raise ValueError("Not a live task directory")
        workflow = json.loads(_safe(root, relative / "workflow.json").read_text())
        if (not isinstance(workflow, dict) or workflow.get("composition_slug") != identity["composition"]
                or workflow.get("structure_slug") != identity["structure"]):
            raise ValueError("Workflow scope differs from registered route")
        return root, route_root, task_parts, workflow
    if len(parts) < 4 or parts[0] != "calculations":
        raise ValueError("Task must be inside calculations/<composition>/<structure>/<task>")
    for part in parts[1:]:
        _name(part)
    task_parts = parts[3:]
    if len(task_parts) > (3 if task_parts[0] == "failed" else 2):
        raise ValueError("Task paths allow one variant level")
    first = task_parts[1] if task_parts[0] == "failed" and len(task_parts) > 1 else task_parts[0]
    if not TASK.fullmatch(first):
        raise ValueError("Task directory must use pN_name or an existing rerun_NNN branch")
    workflow_path = _safe(root, relative / "workflow.json")
    workflow = json.loads(workflow_path.read_text())
    if not isinstance(workflow, dict):
        raise ValueError("workflow.json must be an object")
    if workflow.get("composition_slug") != parts[1] or workflow.get("structure_slug") != parts[2]:
        raise ValueError("Workflow scope differs from the task location")
    return root, root.joinpath(*parts[:3]), task_parts, workflow


def artifact_path(task_root: str | Path, kind: str, topic: str, extension: str) -> Path:
    root, structure, parts, _ = task_context(task_root)
    _name(topic)
    if kind not in KINDS or extension not in EXTENSIONS[kind]:
        raise ValueError("Unsupported artifact kind or extension")
    if route_for(task_root):
        base = Path(task_root).resolve().relative_to(root)
        if project_role(root) != "cluster":
            base = base / "analysis"
        elif kind == "report":
            stage = stage_root(task_root)
            if stage is None or extension != ".md":
                raise ValueError("Stage reports require a registered numbered stage and Markdown")
            return _safe(root, stage.relative_to(root) / "README.md")
        if kind == "report" and extension == ".md":
            return _safe(root, base / "README.md")
        return _safe(root, base / ("data" if kind in {"data", "report"} else "figures") / (topic + extension))
    relative = structure.relative_to(root) / "analysis" / KINDS[kind]
    return _safe(root, relative.joinpath(*parts, topic + extension))


def document_path(project_root: str | Path, kind: str, topic: str, extension: str, task_root=None) -> Path:
    root = discover_workspace(project_root)
    if kind == "main_report":
        if extension != ".md":
            raise ValueError("Main report must be Markdown")
        if project_role(root) == "cluster":
            raise ValueError("Main report belongs to the local project")
        return _safe(root, final_directory(root).relative_to(root) / "main_report.md")
    if kind == "report" and project_role(root) in {"local", "cluster"}:
        stage = stage_root(task_root) if task_root else None
        if not stage or extension != ".md":
            raise ValueError("Stage reports require a registered numbered stage and Markdown")
        return _safe(root, stage.relative_to(root) / "README.md")
    if project_role(root) == "cluster" and kind in {"plan", "log", "note"}:
        raise ValueError("Planning and human logs belong to the local project")
    if kind in {"plan", "log", "readme"}:
        scope = Path(task_root).resolve() if task_root else root
        route = route_for(scope)
        if kind == "readme":
            if (root / PROJECT_FILE).exists():
                scope = stage_root(scope) or (route[0] if route else root)
            return _safe(root, scope.relative_to(root) / "README.md")
        if not route:
            raise ValueError("Select a registered route for plan/log documents")
        return _safe(root, route[0].relative_to(root) / "docs" / f"{kind}.md")
    _name(topic)
    if kind == "note":
        if (extension != ".md" or topic in {"readme", "project_resources", "plan", "log"}
                or re.search(r"main_report|final_report|report_final|project_summary|(?:plan|log)_", topic)):
            raise ValueError("Project notes require a non-reserved .md topic")
        return _safe(root, Path("docs") / (topic + extension))
    if task_root is None:
        raise ValueError("Task artifacts require --task-root")
    target = artifact_path(task_root, kind, topic, extension)
    return ensure_within(root, target)


def save_document(project_root, kind, topic, extension, content: bytes, *, task_root=None,
                  replace=False, expected_sha256=None, section=None) -> Path:
    root = discover_workspace(project_root)
    target = document_path(root, kind, topic, extension, task_root)
    if findings(content, markers()):
        raise ValueError("Private environment information cannot be saved in shared documents")
    with _lock(root):
        old = target.read_bytes() if target.exists() else b""
        if target.exists() and old == content and not section:
            return target
        managed = (root / PROJECT_FILE).exists() or kind in {"main_report", "plan", "log", "readme"}
        if expected_sha256 is not None and hashlib.sha256(old).hexdigest() != expected_sha256:
            raise ValueError("Document changed since read; reread and merge the existing file")
        if target.exists() and expected_sha256 is None and (managed or not replace):
            raise FileExistsError("Document exists; read it and supply --expected-sha256 to update in place")
        if section:
            _name(section)
            if extension != ".md":
                raise ValueError("Sections require Markdown")
            content = _block(old.decode(), content.decode(), f"<!-- dft-section:{section}:start -->",
                             f"<!-- dft-section:{section}:end -->").encode()
        if kind == "main_report" and b"<!-- dft-role:main_report -->" not in content:
            content = b"<!-- dft-role:main_report -->\n" + content
        target.parent.mkdir(parents=True, exist_ok=True)
        explain_directories(root, target.parent)
        # Binary figures/data use the same atomic replacement as Markdown.
        fd, tmp = tempfile.mkstemp(dir=target.parent, prefix=".dft-write-")
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(content)
            os.replace(tmp, target)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
        if (root / PROJECT_FILE).exists():
            from .readmes import refresh
            refresh(root, locked=True)
    if project_role(root) == "local" and kind in {"plan", "report", "readme"} and route_for(target):
        append_event(root, stage_root(target) or route_for(target)[0],
            "document_" + hashlib.sha256(str(target.relative_to(root)).encode() + content).hexdigest()[:20],
            f"Updated {kind}: {target.relative_to(root)}.", [str(target.relative_to(root))])
    return target


def remember(project_root, key: str, kind: str, text: str, evidence: list[str]) -> Path:
    root = discover_workspace(project_root)
    _name(key)
    if kind not in {"decision", "finding", "question", "next"}:
        raise ValueError("Unknown memory kind")
    if not text.strip() or "<!--" in text:
        raise ValueError("Memory text must be nonempty and contain no managed markers")
    if kind in {"decision", "finding"} and not evidence:
        raise ValueError("Decisions and findings require relative evidence")
    for ref in evidence:
        if not _safe(root, ref).is_file():
            raise ValueError("Memory evidence must be an existing workspace file")
    if findings((text + "\n" + "\n".join(evidence)).encode(), markers()):
        raise ValueError("Keep private environment details out of project memory")
    target = _safe(root, "MEMORY.md")
    if not target.exists():
        raise ValueError("Initialize project memory first")
    when = datetime.now(timezone.utc).isoformat(timespec="seconds")
    body = f"## {key}\n\nKind: {kind} | Updated: {when}\n\n{text.strip()}\n"
    if evidence:
        body += "\nEvidence: " + ", ".join(f"[{ref}]({ref})" for ref in evidence) + "\n"
    with _lock(root):
        existing = target.read_text()
        updated = _block(existing, body, f"<!-- dft-memory:{key}:start -->", f"<!-- dft-memory:{key}:end -->")
        _write(target, updated)
    return target


def explain_directories(root, directory):
    if (root / PROJECT_FILE).exists():
        from .readmes import ensure
        ensure(root, directory)


def append_event(project_root, scope, key, text, evidence, *, refresh_views=True):
    root = discover_workspace(project_root)
    _name(key)
    target = document_path(root, "log", "log", ".md", scope)
    for ref in evidence:
        if not _safe(root, ref).is_file():
            raise ValueError("Event evidence must exist")
    body = "Scope: " + Path(scope).resolve().relative_to(root).as_posix() + "\n\n" + text.strip() + "\n\nEvidence: " + ", ".join(evidence)
    body = body.rstrip()
    if not text.strip() or "<!--" in text or findings(body.encode(), markers()):
        raise ValueError("Invalid or private event text")
    marker = f"<!-- dft-event:{key}:start -->"
    end = f"<!-- dft-event:{key}:end -->"
    with _lock(root):
        old = target.read_text() if target.exists() else "# Route log\n"
        if marker in old:
            existing = old.split(marker, 1)[1].split(end, 1)[0].strip()
            if existing.startswith("Recorded: "):
                existing = existing.partition("\n")[2].strip()
            if existing != body:
                raise ValueError("Event ID already records different content; preserve it and use a correction event")
            return target
        _write(target, _block(old, "Recorded: " + datetime.now(timezone.utc).isoformat(timespec="microseconds") + "\n\n" + body, marker, end))
        if refresh_views and (root / PROJECT_FILE).exists():
            from .readmes import refresh
            refresh(root, locked=True)
    return target


def publish_result(project_root, task_root, source, kind, topic, evidence, expected_sha256=None):
    from .lifecycle import screen
    from .core import sha256_file
    root, _, _, workflow = task_context(task_root)
    if root != discover_workspace(project_root):
        raise ValueError("Task belongs to another project")
    _name(topic)
    if kind not in {"figure", "table"}:
        raise ValueError("Publish only final figures or tables")
    raw_source = Path(source).expanduser()
    if raw_source.is_absolute():
        lexical_root = next((parent for parent in raw_source.parents if parent.resolve() == root), None)
        if lexical_root is None:
            raise ValueError("Published source must stay inside this project")
        relative_source = raw_source.relative_to(lexical_root)
    else:
        relative_source = raw_source
    source = _safe(root, relative_source)
    task = Path(task_root).resolve()
    if task not in source.parents or "analysis" not in source.relative_to(task).parts:
        raise ValueError("Publish a selected artifact from this task's analysis directory")
    allowed = EXTENSIONS["figure"] if kind == "figure" else {".csv", ".dat", ".md"}
    if source.suffix not in allowed or not evidence:
        raise ValueError("Published artifact requires a supported format and source evidence")
    for ref in evidence:
        if not _safe(root, ref).is_file():
            raise ValueError("Publication evidence must exist")
    target = _safe(root, Path("results") / ("figures" if kind == "figure" else "tables") / (topic + source.suffix))
    with _lock(root):
        current = next(r for r in screen(root) if root / r["path"] == task)
        if current["category"] != "selected":
            raise ValueError("Publish only an explicitly selected, scientifically accepted result")
        content = source.read_bytes()
        if findings(content, markers()):
            raise ValueError("Publication contains private environment information")
        if target.exists() and target.read_bytes() != content:
            if expected_sha256 != sha256_file(target):
                raise ValueError("Final artifact exists; read it and supply --expected-sha256")
        manifest_path = _safe(root, "results/manifest.json")
        manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
        record = {"source": source.relative_to(root).as_posix(), "source_sha256": sha256_file(source),
                  "task": task.relative_to(root).as_posix(), "task_uuid": workflow.get("task_uuid"),
                  "design_revision": workflow.get("design", {}).get("revision"),
                  "evidence": {ref: sha256_file(root / ref) for ref in evidence}}
        target.parent.mkdir(parents=True, exist_ok=True)
        explain_directories(root, target.parent)
        fd, temporary = tempfile.mkstemp(dir=target.parent, prefix=".dft-publish-")
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(content)
            os.replace(temporary, target)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        manifest[target.relative_to(root).as_posix()] = record
        _write(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
        readme = _safe(root, "results/README.md")
        rows = ["## Published artifacts", ""]
        for name, item in sorted(manifest.items()):
            rows.append(f"- [{Path(name).name}]({Path(name).relative_to('results')}) — [source](../{item['source']})")
        _write(readme, _block(readme.read_text(), "\n".join(rows)))
    return target


def task_records(root: Path) -> list[dict]:
    if project_role(root) == "local":
        from .paired import read_json, REMOTE_STATE
        return read_json(root / REMOTE_STATE, {"tasks": []})["tasks"]
    records = []
    for path in sorted(workflow_paths(root)):
        parts = path.relative_to(root).parts
        if any(x in {"attempts", "analysis", "refs", "scripts"} or x.startswith(".") for x in parts):
            continue
        safe = _safe(root, path.relative_to(root))
        try:
            data = json.loads(safe.read_text())
            if not isinstance(data, dict):
                raise ValueError("not an object")
            if any(not isinstance(data.get(key, {}), dict) for key in ("completion", "management", "submission", "lineage", "design")):
                raise ValueError("invalid task metadata")
            completion = data.get("completion", {})
            records.append({"path": path.parent.relative_to(root).as_posix(),
                            "task_uuid": data.get("task_uuid"), "status": data.get("status", "unknown"),
                            "verified_at": data.get("updated_at", ""),
                            "completion": completion, "dependencies": data.get("dependencies", []),
                            "lineage": data.get("lineage", {}), "management": data.get("management", {}),
                            "task_slug": data.get("task_slug"), "design": data.get("design", {}),
                            "submission": data.get("submission", {})})
        except (ValueError, OSError):
            records.append({"path": path.parent.relative_to(root).as_posix(), "error": "invalid workflow.json"})
    for route in project_routes(root):
        base = root / route["path"]
        if not base.is_dir():
            continue
        for directory in sorted(base.iterdir()):
            if directory.is_dir() and not directory.is_symlink() and STAGE_RE.fullmatch(directory.name):
                relative = directory.relative_to(root).as_posix()
                if not any(r["path"] == relative or r["path"].startswith(relative + "/") for r in records):
                    manifest = json.loads((root / PROJECT_FILE).read_text())
                    if relative in manifest.get("planned_stages", []) and all(
                        child.name in {"README.md", "shared", "scripts", "data", "figures"} for child in directory.iterdir()
                    ):
                        continue  # A known stage skeleton is not an executable task ledger.
                    records.append({"path": relative, "error": "missing workflow.json"})
    return records


def project_context(project_root, limit=30) -> str:
    root = discover_workspace(project_root)
    memory = _safe(root, "MEMORY.md")
    text = memory.read_text() if memory.exists() else "Project memory missing; run init.\n"
    from .lifecycle import screen
    records = screen(root)
    # Status is read on demand; no second machine ledger or stale memory snapshot.
    return text + f"\n## Live tasks ({len(records)} total)\n\n" + json.dumps(records[:limit], ensure_ascii=False, indent=2) + "\n"


def sync_project(project_root) -> Path:
    root = discover_workspace(project_root)
    if (root / PROJECT_FILE).exists():
        if project_role(root) == "local":
            from .paired import sync_pair
            return sync_pair(root)
        from .readmes import refresh
        refresh(root)
        return root / "README.md"
    from .lifecycle import screen
    records = screen(root)
    body = "## DFT records\n\n[Project memory](MEMORY.md) · [Main report](results/main_report.md) · [Final results](results/README.md)\n\n"
    for route in project_routes(root):
        rel = route["path"]
        body += f"- [{rel}]({rel}/README.md): [plan]({rel}/docs/plan.md), [log]({rel}/docs/log.md)\n"
    body += "This index is derived. Use context for current status from workflow.json.\n\n"
    for record in records:
        path = record["path"]
        body += f"- [{path}]({path}/README.md) — {record.get('category', 'needs_review')} (execution: {record.get('status', 'unknown')})\n"
    body += "\n### Documents\n\n"
    for path in managed_files(root):
        if path.suffix != ".md":
            continue
        rel = path.relative_to(root)
        if rel.parts[0] == "docs" or "analysis" in rel.parts:
            if path.name == "project-resources.md":
                continue
            _safe(root, rel)
            body += f"- [{rel.as_posix()}]({rel.as_posix()})\n"
    target = _safe(root, "README.md")
    with _lock(root):
        old = target.read_text() if target.exists() else "# DFT Project\n"
        _write(target, _block(old, body))
        for route in project_routes(root):
            route_path = route["path"]
            selected_records = [r for r in records if r["path"].startswith(route_path + "/")]
            lines = ["## Task index", "", "Purpose and scientific conclusions stay in the human text; this view is derived.", ""]
            for record in selected_records:
                relative = Path(record["path"]).relative_to(route_path)
                lines.append(f"- [{relative}]({relative}/README.md): {record['category']} (execution: {record.get('status', 'unknown')})")
                readme = _safe(root, Path(record["path"]) / "README.md")
                if readme.is_file():
                    status = f"Disposition: {record['category']}\n\nExecution: {record.get('status', 'unknown')}\n\nSource: [workflow.json](workflow.json)"
                    _write(readme, _block(readme.read_text(), status, "<!-- dft-task-view:start -->", "<!-- dft-task-view:end -->"))
            readme = _safe(root, Path(route_path) / "README.md")
            _write(readme, _block(readme.read_text() if readme.exists() else "# Research route\n", "\n".join(lines)))
    return target


def managed_files(root):
    for folder, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if not d.startswith(".") and d not in
                         {"attempts", "software", "tmp", "archive", "archived", "__pycache__"}
                         and not d.startswith("tmp_") and not d.endswith(".save")
                         and not (Path(folder) / d).is_symlink())
        for name in sorted(files):
            path = Path(folder) / name
            if not path.is_symlink():
                yield path


def check_project(project_root) -> list[str]:
    root = discover_workspace(project_root)
    if project_role(root) == "local":
        from .paired import check_pair
        return check_pair(root)
    from .organization import pending_issues
    issues = pending_issues(root)
    if (root / ".dft/readme-refresh-required").exists():
        issues.append("README refresh pending; rerun sync after repairing the document conflict")
    if any((parent / ".git").exists() for parent in (root, *root.parents)):
        tracked = subprocess.check_output(
            ["git", "-C", str(root), "ls-files", "-z", "--", ".dft", "docs/project-resources.md"]
        )
        if tracked:
            issues.append("Private resource records are already Git-tracked; ignore rules alone cannot protect them")
    for name in (("AGENTS.md",) if project_role(root) == "cluster" else ("MEMORY.md", "AGENTS.md")):
        if not _safe(root, name).is_file():
            issues.append(f"{name}: missing project context")
    identities = set()
    selections = set()
    for record in task_records(root):
        path = record["path"]
        if "error" in record:
            issues.append(f"{path}: {record['error']}")
            continue
        try:
            _, _, _, workflow = task_context(root / path)
            route = route_for(root / path)
            if route:
                for directory in {route[0], stage_root(root / path)} - {None}:
                    if not (directory / "README.md").is_file():
                        issues.append(f"{directory.relative_to(root)}: missing directory README")
                management = workflow.get("management", {})
                if management.get("disposition") == "selected":
                    key = (route[0], management.get("selection_key"))
                    if key in selections:
                        issues.append(f"{path}: duplicate selection for one purpose")
                    selections.add(key)
                    if not all(workflow.get("completion", {}).get(k) is True for k in ("scheduler_complete", "artifact_complete", "scientifically_accepted")):
                        issues.append(f"{path}: selected result lacks recorded acceptance")
            version = workflow.get("schema_version")
            contract = f"workflow-v{version}"
            if type(version) is not int or version not in {1, 2} or validate_document(contract, workflow):
                issues.append(f"{path}: workflow contract validation failed")
            elif workflow.get("status") not in json.loads(contract_path(contract).read_text())["properties"]["status"]["enum"]:
                issues.append(f"{path}: invalid execution status")
            if record["task_uuid"] is None:
                issues.append(f"{path}: legacy task without UUID; preserve or explicitly migrate")
            else:
                if not isinstance(record["task_uuid"], str):
                    raise ValueError("Task UUID must be a string")
                UUID(record["task_uuid"])
                if record["task_uuid"] in identities:
                    issues.append(f"{path}: duplicate task UUID")
                identities.add(record["task_uuid"])
            if project_role(root) == "cluster":
                binding = workflow.get("execution", {})
                snapshot_path = _safe(root, binding.get("path", ""))
                if not snapshot_path.is_file() or hashlib.sha256(snapshot_path.read_bytes()).hexdigest() != binding.get("sha256"):
                    issues.append(f"{path}: missing or changed local-bound execution snapshot")
                else:
                    snapshot = json.loads(snapshot_path.read_text())
                    if (snapshot.get("project_id") != json.loads((root / PROJECT_FILE).read_text()).get("project_id")
                            or snapshot.get("task") != path
                            or snapshot.get("facts", {}).get("task_uuid") != record["task_uuid"]):
                        issues.append(f"{path}: execution identity requires local reconciliation")
        except (ValueError, TypeError, OSError):
            issues.append(f"{path}: noncanonical name or invalid task UUID")
    routes_mode = (root / PROJECT_FILE).exists()
    for path in managed_files(root):
        rel = path.relative_to(root)
        if any(part in {".git", ".dft", "attempts", "archived"} for part in rel.parts):
            continue
        if not path.is_file():
            continue
        _safe(root, rel)
        if path.suffix == ".md":
            text = path.read_text(errors="replace")
            if (("<!-- dft-role:main_report -->" in text or re.search(r"(?:main_report|report_final|final_report|project_summary)", path.stem, re.I))
                    and rel.as_posix() != "results/main_report.md"):
                issues.append(f"{rel}: duplicate main report; update results/main_report.md")
        if rel.parts[0] == "results":
            if path.name not in {"README.md", "main_report.md", "manifest.json"} and not (
                len(rel.parts) in {3, 4} and rel.parts[1] in {"figures", "tables"}
            ):
                issues.append(f"{rel}: results contains only the main report and final figures/tables")
            continue
        if routes_mode:
            route = route_for(path)
            if route and path.suffix == ".md" and path.name != "README.md":
                inside = path.relative_to(route[0])
                if inside.parts[0] == "docs" and path.name not in {"plan.md", "log.md"}:
                    issues.append(f"{rel}: update the existing route plan/log instead of a copy")
            continue
        if len(rel.parts) == 1 and path.suffix == ".md" and path.name not in {"README.md", "AGENTS.md", "MEMORY.md"}:
            issues.append(f"{rel}: project notes belong in docs/<topic>.md")
        if rel.parts[0] == "docs" and path.name not in {"README.md", "project-resources.md"}:
            if len(rel.parts) != 2 or path.suffix != ".md" or not NAME.fullmatch(path.stem):
                issues.append(f"{rel}: use docs/<snake_case_topic>.md")
        if "analysis" in rel.parts:
            i = rel.parts.index("analysis")
            if i != 3:
                issues.append(f"{rel}: analysis belongs directly under the structure")
            elif path.name != "README.md":
                after = rel.parts[i+1:]
                route = after[1:-1]
                if route and route[0] == "failed":
                    route = route[1:]
                kind = next((key for key, value in KINDS.items() if after and value == after[0]), None)
                if (not route or kind is None or not TASK.fullmatch(route[0])
                        or any(not NAME.fullmatch(part) for part in route[1:])
                        or not NAME.fullmatch(path.stem) or path.suffix not in EXTENSIONS.get(kind, set())):
                    issues.append(f"{rel}: use analysis/<kind>/<task>[/<variant>]/<topic>.<ext>")
    manifest_path = _safe(root, "results/manifest.json")
    if manifest_path.exists():
        from .core import sha256_file
        try:
            manifest = json.loads(manifest_path.read_text())
            for name, record in manifest.items():
                target = _safe(root, name)
                source = _safe(root, record["source"])
                if not source.is_file() or not target.is_file() or sha256_file(source) != record["source_sha256"] or sha256_file(target) != record["source_sha256"]:
                    issues.append(f"{name}: published artifact or source changed; republish after review")
                for ref, digest in record.get("evidence", {}).items():
                    evidence = _safe(root, ref)
                    if not evidence.is_file() or sha256_file(evidence) != digest:
                        issues.append(f"{name}: publication evidence changed")
                task_file = _safe(root, Path(record["task"]) / "workflow.json")
                task = json.loads(task_file.read_text())
                if task.get("management", {}).get("disposition") != "selected" or task.get("completion", {}).get("scientifically_accepted") is not True:
                    issues.append(f"{name}: published source is no longer a selected accepted result")
        except (ValueError, KeyError, TypeError, AttributeError, OSError):
            issues.append("results/manifest.json: invalid publication provenance")
    return issues


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("init", "route", "context", "read", "path", "document", "event", "remember", "sync", "check", "screen", "mark", "rework-impact", "publish", "git-init", "git-check", "deploy", "reconcile-remote", "organize-inventory", "organize-preview", "organize-apply", "organize-check"))
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--task-root", type=Path)
    parser.add_argument("--kind")
    parser.add_argument("--topic")
    parser.add_argument("--extension", default=".md")
    parser.add_argument("--source", type=Path)
    parser.add_argument("--replace", action="store_true")
    parser.add_argument("--layout", choices=("routes", "legacy"))
    parser.add_argument("--route")
    parser.add_argument("--remote-root", help="Absolute cluster project root; omitted --ssh means a mounted/test endpoint")
    parser.add_argument("--ssh", help="SSH host alias; credentials remain managed by SSH")
    parser.add_argument("--cluster", default="primary")
    parser.add_argument("--refs", default="docs/refs")
    parser.add_argument("--spec", type=Path, help="Agent-reviewed routes, known stages and reference moves")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-git", action="store_true", help="Explicitly defer local Git setup")
    parser.add_argument("--max-bytes", type=int, default=1_000_000_000)
    parser.add_argument("--event-id")
    parser.add_argument("--composition")
    parser.add_argument("--structure")
    parser.add_argument("--expected-sha256")
    parser.add_argument("--section")
    parser.add_argument("--disposition")
    parser.add_argument("--key")
    parser.add_argument("--text")
    parser.add_argument("--evidence", action="append", default=[])
    parser.add_argument("--limit", type=int, default=30)
    args = parser.parse_args(argv)
    args.project_root = args.project_root.expanduser().resolve()
    if args.task_root is not None and not args.task_root.is_absolute():
        args.task_root = args.project_root / args.task_root
    try:
        if args.dry_run and args.command not in {"init", "publish"}:
            raise ValueError("--dry-run is supported for init and publish only")
        if args.command.startswith("organize-"):
            from . import organization
            if args.command == "organize-inventory":
                result = organization.inventory(args.project_root)
            elif args.command == "organize-check":
                if not args.key:
                    raise ValueError("--key is required for organize-check")
                result = organization.check(args.project_root, args.key)
            else:
                if args.spec is None:
                    raise ValueError("--spec is required for organization preview/apply")
                spec = json.loads(args.spec.read_text())
                if args.command == "organize-preview":
                    result = organization.preview(args.project_root, spec)
                else:
                    if not args.expected_sha256:
                        raise ValueError("--expected-sha256 from the reviewed preview is required")
                    result = organization.apply(args.project_root, spec, args.expected_sha256)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return int(result.get("status") == "needs_review")
        elif args.command == "init":
            if args.remote_root:
                from .paired import init_pair
                result = init_pair(args.project_root, args.remote_root, ssh=args.ssh, cluster=args.cluster,
                    spec=json.loads(args.spec.read_text()) if args.spec else None,
                    refs=args.refs, dry_run=args.dry_run, git=not args.no_git)
                print(json.dumps(result, ensure_ascii=False, indent=2))
                if result.get("status") == "pending":
                    return 1
            elif args.dry_run:
                print(json.dumps({"mode": "single", "layout": args.layout or "auto", "action": "create missing project records"}))
            else:
                print(init_project(args.project_root, args.layout))
        elif args.command in {"deploy", "reconcile-remote"}:
            if args.task_root is None:
                raise ValueError("--task-root is required")
            scripts = Path(__file__).resolve().parents[2] / "dft-workflow/scripts"
            if str(scripts) not in sys.path:
                sys.path.insert(0, str(scripts))
            from paired_execution import deploy_task, reconcile_remote
            if args.command == "deploy":
                result = deploy_task(args.project_root, args.task_root)
            else:
                task = args.task_root.relative_to(args.project_root) if args.task_root.is_absolute() else args.task_root
                result = reconcile_remote(args.project_root, task.as_posix(), event_id=args.event_id)
            print(json.dumps(result, ensure_ascii=False, indent=2))
        elif args.command == "route":
            if not all((args.route, args.composition, args.structure)):
                raise ValueError("--route, --composition and --structure are required")
            print(register_route(args.project_root, args.route, args.composition, args.structure))
        elif args.command == "context":
            if args.limit < 1:
                raise ValueError("limit must be positive")
            print(project_context(args.project_root, args.limit))
        elif args.command in {"path", "document", "read"}:
            if not args.kind:
                raise ValueError("--kind is required")
            topic = args.topic or "summary"
            if args.command == "path":
                print(document_path(args.project_root, args.kind, topic, args.extension, args.task_root))
            elif args.command == "read":
                path = document_path(args.project_root, args.kind, topic, args.extension, args.task_root)
                content = path.read_bytes() if path.exists() else b""
                print(json.dumps({"path": str(path), "exists": path.exists(), "sha256": hashlib.sha256(content).hexdigest(),
                                  "text": content.decode() if path.suffix in {".md", ".json", ".dat", ".csv"} else None}, ensure_ascii=False))
            else:
                if args.source is None:
                    raise ValueError("--source is required")
                print(save_document(args.project_root, args.kind, topic, args.extension, args.source.read_bytes(), task_root=args.task_root, replace=args.replace, expected_sha256=args.expected_sha256, section=args.section))
        elif args.command == "event":
            if not args.task_root or not args.key or not args.text:
                raise ValueError("--task-root, --key and --text are required")
            print(append_event(args.project_root, args.task_root, args.key, args.text, args.evidence))
        elif args.command in {"screen", "mark", "rework-impact"}:
            from .lifecycle import screen, mark_task, rework_impact
            if args.command == "screen":
                print(json.dumps(screen(args.project_root), ensure_ascii=False, indent=2))
            elif project_role(discover_workspace(args.project_root)) == "local" and args.command == "mark":
                from .paired import mark_pair
                if args.task_root is None:
                    raise ValueError("--task-root is required")
                task = args.task_root.relative_to(args.project_root) if args.task_root.is_absolute() else args.task_root
                print(json.dumps(mark_pair(args.project_root, task.as_posix(), args.disposition,
                    args.text or "", args.evidence, args.key), ensure_ascii=False))
            else:
                if not args.task_root or discover_workspace(args.task_root) != discover_workspace(args.project_root):
                    raise ValueError("Select a task in this project")
                if args.command == "mark":
                    print(mark_task(args.task_root, args.disposition, args.text or "", args.evidence, args.key))
                    sync_project(args.project_root)
                else:
                    print(json.dumps(rework_impact(args.task_root), ensure_ascii=False, indent=2))
        elif args.command == "publish":
            if not args.task_root or not args.source or not args.topic:
                raise ValueError("--task-root, --source and --topic are required")
            if project_role(discover_workspace(args.project_root)) == "local":
                from .paired import publish_pair
                task = args.task_root.relative_to(args.project_root) if args.task_root.is_absolute() else args.task_root
                result = publish_pair(args.project_root, task.as_posix(), args.source.as_posix(), args.kind,
                    args.topic, args.evidence, max_bytes=args.max_bytes, expected_sha256=args.expected_sha256,
                    dry_run=args.dry_run)
                print(json.dumps(result, ensure_ascii=False, indent=2))
                if result["status"] == "needs_scope_approval":
                    return 1
            else:
                print(publish_result(args.project_root, args.task_root, args.source, args.kind, args.topic,
                                     args.evidence, args.expected_sha256))
        elif args.command in {"git-init", "git-check"}:
            from .project_git import init_git, check_index
            if args.command == "git-init":
                print(init_git(args.project_root))
            else:
                issues = check_index(args.project_root)
                print("\n".join(issues) if issues else "Staged project records OK")
                return int(bool(issues))
        elif args.command == "remember":
            if not args.key or not args.kind or not args.text:
                raise ValueError("--key, --kind and --text are required")
            print(remember(args.project_root, args.key, args.kind, args.text, args.evidence))
        elif args.command == "sync":
            print(sync_project(args.project_root))
        else:
            issues = check_project(args.project_root)
            print("\n".join(issues) if issues else "Project records OK")
            return int(bool(issues))
        return 0
    except (ValueError, OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
