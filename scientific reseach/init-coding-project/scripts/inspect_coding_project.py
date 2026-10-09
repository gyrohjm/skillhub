#!/usr/bin/env python3
"""Read-only inspection of a coding project root."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


MANIFEST_ECOSYSTEMS = {
    "pyproject.toml": "python",
    "requirements.txt": "python",
    "setup.py": "python",
    "package.json": "node",
    "Cargo.toml": "rust",
    "go.mod": "go",
    "pom.xml": "jvm",
    "build.gradle": "jvm",
    "build.gradle.kts": "jvm",
    "Gemfile": "ruby",
    "composer.json": "php",
}
LOCKFILE_MANAGERS = {
    "uv.lock": "uv",
    "poetry.lock": "poetry",
    "Pipfile.lock": "pipenv",
    "pnpm-lock.yaml": "pnpm",
    "yarn.lock": "yarn",
    "package-lock.json": "npm",
    "bun.lock": "bun",
    "bun.lockb": "bun",
    "Cargo.lock": "cargo",
    "go.sum": "go",
    "Gemfile.lock": "bundler",
    "composer.lock": "composer",
}
MONOREPO_MARKERS = (
    "pnpm-workspace.yaml",
    "lerna.json",
    "nx.json",
    "turbo.json",
    "rush.json",
)
AGENT_FILES = ("AGENTS.md", "CLAUDE.md")
PROJECT_DOCS = (
    "PROJECT_CONTEXT.md",
    "CONTEXT.md",
    "CONTEXT-MAP.md",
    "README.md",
    "docs/product/product_brief.md",
    "docs/architecture/architecture.md",
    "docs/plans/implementation_plan.md",
)
LAYOUT_CANDIDATES = (
    "src",
    "tests",
    "test",
    "apps",
    "packages",
    "lib",
    "cmd",
    "internal",
    "infra",
    "migrations",
    "examples",
    "benchmarks",
)


def relative_files(root: Path, patterns: tuple[str, ...]) -> list[str]:
    return [pattern for pattern in patterns if (root / pattern).is_file()]


def read_package_scripts(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    scripts = data.get("scripts") if isinstance(data, dict) else None
    if not isinstance(scripts, dict):
        return {}
    return {str(key): str(value) for key, value in scripts.items()}


def read_make_targets(path: Path) -> list[str]:
    if not path.is_file():
        return []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    targets = []
    for line in text.splitlines():
        match = re.match(r"^([A-Za-z0-9][A-Za-z0-9_.-]*):(?:\s|$)", line)
        if match and not match.group(1).startswith("."):
            targets.append(match.group(1))
    return sorted(set(targets))


def git_remotes(root: Path) -> list[str]:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "remote", "-v"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if result.returncode != 0:
        return []
    return sorted(set(line.strip() for line in result.stdout.splitlines() if line.strip()))


def inspect(root: Path) -> dict[str, Any]:
    if not root.exists():
        return {
            "root": str(root),
            "exists": False,
            "classification": "new-project",
            "write_performed": False,
        }
    if not root.is_dir():
        raise ValueError(f"Root is not a directory: {root}")

    manifests = relative_files(root, tuple(MANIFEST_ECOSYSTEMS))
    lockfiles = relative_files(root, tuple(LOCKFILE_MANAGERS))
    ecosystems = sorted({MANIFEST_ECOSYSTEMS[name] for name in manifests})
    package_managers = sorted({LOCKFILE_MANAGERS[name] for name in lockfiles})
    monorepo_markers = relative_files(root, MONOREPO_MARKERS)
    package_data: dict[str, Any] = {}
    package_path = root / "package.json"
    if package_path.is_file():
        try:
            value = json.loads(package_path.read_text(encoding="utf-8"))
            package_data = value if isinstance(value, dict) else {}
        except (OSError, json.JSONDecodeError):
            package_data = {}
    if isinstance(package_data.get("workspaces"), (list, dict)):
        monorepo_markers.append("package.json#workspaces")

    ci_files: list[str] = []
    github_workflows = root / ".github" / "workflows"
    if github_workflows.is_dir():
        ci_files.extend(
            str(path.relative_to(root))
            for path in sorted(github_workflows.iterdir())
            if path.is_file() and path.suffix in {".yml", ".yaml"}
        )
    for candidate in (".gitlab-ci.yml", "Jenkinsfile", "azure-pipelines.yml", "bitbucket-pipelines.yml"):
        if (root / candidate).is_file():
            ci_files.append(candidate)

    git_marker = root / ".git"
    return {
        "root": str(root),
        "exists": True,
        "classification": "existing-project",
        "is_git_repository": git_marker.exists(),
        "git_remotes": git_remotes(root) if git_marker.exists() else [],
        "agent_files": relative_files(root, AGENT_FILES),
        "project_docs": relative_files(root, PROJECT_DOCS),
        "manifests": manifests,
        "lockfiles": lockfiles,
        "detected_ecosystems": ecosystems,
        "detected_package_managers": package_managers,
        "monorepo_markers": sorted(set(monorepo_markers)),
        "layout_directories": [name for name in LAYOUT_CANDIDATES if (root / name).is_dir()],
        "ci_files": ci_files,
        "quality_command_evidence": {
            "package_scripts": read_package_scripts(package_path),
            "make_targets": read_make_targets(root / "Makefile"),
        },
        "write_performed": False,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path, help="Project root to inspect")
    parser.add_argument("--compact", action="store_true", help="Emit compact JSON")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        root = args.root.expanduser().absolute()
        result = inspect(root)
        print(json.dumps(result, ensure_ascii=False, indent=None if args.compact else 2, sort_keys=True))
        return 0
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

