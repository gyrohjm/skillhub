#!/usr/bin/env python3
"""Verify a VASP Work Manager archive directory."""

from __future__ import annotations

import argparse
import json
import re
from hashlib import sha256
from pathlib import Path
from typing import Any


SHA_LINE = re.compile(r"^([0-9a-fA-F]{64})\s+\*?(.+)$")


def file_sha256(path: Path) -> str:
    h = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def issue(code: str, path: str, message: str) -> dict[str, str]:
    return {"code": code, "path": path, "message": message}


def safe_child(root: Path, relpath: str) -> Path | None:
    candidate = (root / relpath).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate


def read_manifest(archive: Path, issues: list[dict[str, str]]) -> dict[str, Any]:
    path = archive / "manifest.json"
    if not path.exists():
        issues.append(issue("MISSING_MANIFEST", "manifest.json", "manifest.json is missing"))
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        issues.append(issue("BAD_MANIFEST_JSON", "manifest.json", str(exc)))
        return {}
    if not isinstance(loaded, dict):
        issues.append(issue("BAD_MANIFEST_TYPE", "manifest.json", "manifest root is not an object"))
        return {}
    return loaded


def read_sums(archive: Path, issues: list[dict[str, str]]) -> dict[str, str]:
    path = archive / "SHA256SUMS"
    if not path.exists():
        issues.append(issue("MISSING_SHA256SUMS", "SHA256SUMS", "SHA256SUMS is missing"))
        return {}
    sums: dict[str, str] = {}
    for line_no, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
        if not line.strip():
            continue
        match = SHA_LINE.match(line)
        if not match:
            issues.append(issue("BAD_SHA256_LINE", f"SHA256SUMS:{line_no}", line))
            continue
        digest, relpath = match.groups()
        sums[relpath.strip()] = digest.lower()
    return sums


def verify(archive: Path) -> tuple[dict[str, Any], list[dict[str, str]]]:
    archive = archive.expanduser().resolve()
    issues: list[dict[str, str]] = []
    summary: dict[str, Any] = {
        "archive": str(archive),
        "checked": 0,
        "ok": False,
    }
    if not archive.is_dir():
        return summary, [issue("ARCHIVE_NOT_FOUND", str(archive), "archive directory does not exist")]

    manifest = read_manifest(archive, issues)
    sums = read_sums(archive, issues)

    manifest_files: set[str] = set()
    for item in manifest.get("files", []) if isinstance(manifest.get("files"), list) else []:
        if isinstance(item, dict) and isinstance(item.get("relpath"), str):
            manifest_files.add(item["relpath"])

    for relpath, expected in sorted(sums.items()):
        target = safe_child(archive, relpath)
        if target is None:
            issues.append(issue("UNSAFE_PATH", relpath, "checksum path escapes archive"))
            continue
        if not target.exists():
            issues.append(issue("MISSING_FILE", relpath, "listed file is missing"))
            continue
        if not target.is_file():
            issues.append(issue("NOT_A_FILE", relpath, "listed path is not a regular file"))
            continue
        actual = file_sha256(target)
        summary["checked"] += 1
        if actual.lower() != expected.lower():
            issues.append(issue("HASH_MISMATCH", relpath, f"expected {expected}, got {actual}"))

    for relpath in sorted(manifest_files):
        if relpath not in sums:
            issues.append(issue("MANIFEST_FILE_NOT_IN_SUMS", relpath, "manifest file is not covered by SHA256SUMS"))

    if "manifest.json" not in sums and (archive / "manifest.json").exists():
        issues.append(issue("MANIFEST_NOT_IN_SUMS", "manifest.json", "manifest.json is not covered by SHA256SUMS"))

    summary["ok"] = not issues
    summary["issue_count"] = len(issues)
    summary["manifest_schema"] = manifest.get("schema")
    summary["project"] = manifest.get("project")
    summary["task"] = manifest.get("task")
    return summary, issues


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="vwm_verify.py")
    parser.add_argument("--archive", required=True, help="Archive version directory to verify.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    summary, issues = verify(Path(args.archive))
    if args.json:
        print(json.dumps({"summary": summary, "issues": issues}, indent=2, sort_keys=True))
    else:
        print(f"Archive: {summary['archive']}")
        if summary.get("project") or summary.get("task"):
            print(f"Task: {summary.get('project') or '-'} / {summary.get('task') or '-'}")
        print(f"Checked files: {summary['checked']}")
        if not issues:
            print("Archive verified.")
        else:
            print(f"Issues: {len(issues)}")
            for item in issues:
                print(f"{item['code']}: {item['path']} - {item['message']}")
    return 0 if not issues else 1


if __name__ == "__main__":
    raise SystemExit(main())
