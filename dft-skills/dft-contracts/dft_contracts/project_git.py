"""Local Git history and staged-content checks for scientific project records."""
from __future__ import annotations

import json
from pathlib import Path
import re
import shlex
import subprocess
import sys

from .layout import discover_workspace, final_directory
from .privacy import findings, markers


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], stderr=subprocess.PIPE)


def init_git(project_root):
    root = discover_workspace(project_root)
    try:
        owner = Path(git(root, "rev-parse", "--show-toplevel").decode().strip()).resolve()
    except subprocess.CalledProcessError:
        owner = None
    if owner and owner != root:
        raise ValueError("Project is inside another Git worktree; use a separate project repository")
    if owner is None:
        subprocess.run(["git", "init", "-q", str(root)], check=True)
    configured = subprocess.run(["git", "-C", str(root), "config", "--get", "core.hooksPath"], capture_output=True)
    if configured.returncode == 0:
        raise ValueError("Custom hooksPath preserved; integrate git-check into the existing hook configuration")
    path = Path(git(root, "rev-parse", "--git-path", "hooks/pre-commit").decode().strip())
    path = path if path.is_absolute() else root / path
    script = Path(__file__).resolve().parents[2] / "dft-work-manager/scripts/dft_project.py"
    content = ("#!/bin/sh\n# dft-project staged records check\n"
               f"exec {shlex.quote(sys.executable)} {shlex.quote(str(script))} git-check --project-root {shlex.quote(str(root))}\n")
    if path.is_symlink() or (path.exists() and path.read_text() != content):
        raise ValueError("Existing pre-commit hook preserved; integrate the git-check command into it explicitly")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    path.chmod(0o700)
    return path


def check_index(project_root):
    root = discover_workspace(project_root)
    issues = []
    final = final_directory(root).name
    signatures = markers()
    entries = git(root, "ls-files", "--stage", "-z").split(b"\0")
    for entry in entries:
        if not entry:
            continue
        metadata, raw_path = entry.split(b"\t", 1)
        mode, blob, stage = metadata.decode().split()
        name = raw_path.decode("utf-8", errors="replace")
        path = Path(name)
        if stage != "0":
            issues.append(f"{name}: unresolved index conflict")
            continue
        if (mode != "100644" and mode != "100755"):
            issues.append(f"{name}: project Git records must be regular files")
            continue
        if (any(p in {".dft", "attempts", "software", "tmp"} or p.endswith(".save") or p.startswith("tmp_") for p in path.parts)
                or path.name in {"POTCAR", "WAVECAR", "CHGCAR", "project-resources.md", "workflow.json", "job.sh", "qe.sh", "vasp.sh"}
                or path.suffix.lower() in {".upf", ".out"}):
            issues.append(f"{name}: runtime, large input or private environment record must stay outside Git")
            continue
        size = int(git(root, "cat-file", "-s", blob))
        if size > 20 * 1024 * 1024:
            issues.append(f"{name}: large artifact; keep it in calculation storage")
            continue
        content = git(root, "cat-file", "blob", blob)
        for line, category in findings(content, signatures):
            issues.append(f"{name}:{line}: {category}")
        if path.suffix == ".md":
            if (b"<!-- dft-role:main_report -->" in content or re.search(r"main_report|final_report|report_final|project_summary", path.stem, re.I)) and name != f"{final}/main_report.md":
                issues.append(f"{name}: duplicate main report")
            if re.search(r"(?:plan|readme|log)(?:_v\d+|_new|_final|_\d{8})", path.stem, re.I):
                issues.append(f"{name}: update the existing document; Git preserves previous versions")
        if path.parts[0] == final and name not in {f"{final}/README.md", f"{final}/main_report.md", f"{final}/manifest.json"}:
            if len(path.parts) not in {3, 4} or path.parts[1] not in {"figures", "tables"}:
                issues.append(f"{name}: unexpected file in final results")
    return issues
