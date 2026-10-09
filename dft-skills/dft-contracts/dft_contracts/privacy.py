"""Small local guard: inspect Git index bytes, never echo matching secrets."""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

from .local_config import config_dir, read_private_json


def markers() -> list[str]:
    values = read_private_json("privacy-markers.json", default=[])
    if not isinstance(values, list) or any(not isinstance(v, str) or not v for v in values):
        raise ValueError("privacy-markers.json must be a list of nonempty strings")
    # Paired roots are added only from private files, never hardcoded in public rules.
    for path in config_dir().glob('project-*.json'):
        binding = read_private_json(path.name)
        if not isinstance(binding, dict):
            raise ValueError('Invalid private project binding')
        for key in ('local_root', 'remote_root'):
            value = binding.get(key)
            if isinstance(value, str) and Path(value).is_absolute() and len(Path(value).parts) > 2:
                values.append(value)
    return list(dict.fromkeys(values))


def findings(content: bytes, private_values: list[str]) -> list[tuple[int, str]]:
    text = content.decode("utf-8", errors="replace")
    result = []
    for number, line in enumerate(text.splitlines(), 1):
        categories = set()
        if any(value in line for value in private_values):
            categories.add("private environment value")
        if re.search(r"-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----", line):
            categories.add("private key")
        if re.search(r'(?i)(?:^\s*(?:export\s+)?|[,{]\s*)[\x22\x27]?[\w]*(?:password|passwd|api_key|access_token|secret_key)[\w]*[\x22\x27]?\s*[:=]\s*[\x22\x27]?[A-Za-z0-9/+_-]{8,}', line):
            categories.add("credential assignment")
        for match in re.finditer(r"/(?:Users|home)/([A-Za-z0-9_.-]+)", line):
            if match[1] not in {"user", "example", "test", "username", "..."}:
                categories.add("personal home path")
        if (re.search(r"(?i)^\s*HostName\s+[a-z0-9]", line)
                or re.search(r"(?i)(?:^|\s)ssh\s+[^\n]*@[a-z0-9]", line)):
            if not any(x in line for x in ("example.org", "example.com", "example.invalid")):
                categories.add("SSH connection information")
        for endpoint in re.finditer(r"\b((?:\d{1,3}\.){3}\d{1,3}):\d{2,5}\b", line):
            address = endpoint[1]
            if address != "127.0.0.1" and not address.startswith(("192.0.2.", "198.51.100.", "203.0.113.")):
                categories.add("network endpoint")
        result.extend((number, category) for category in sorted(categories))
    return result


def _git(repo: Path, *args: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(repo), *args], stderr=subprocess.DEVNULL)


def scan_index(repo: Path, private_values: list[str]) -> list[tuple[str, int, str]]:
    results = []
    # Inspect all DFT files in the proposed commit, not working-tree copies.
    for entry in _git(repo, "ls-files", "--stage", "-z").split(b"\0"):
        if not entry:
            continue
        metadata, raw_path = entry.split(b"\t", 1)
        mode, oid, stage = metadata.split()
        path = raw_path.decode("utf-8", errors="replace")
        if "archived" in Path(path).parts:
            continue
        private_artifact = Path(path).name in {"privacy-markers.json", "project-resources.md"} or ".dft" in Path(path).parts
        if not private_artifact and not any(part.startswith("dft-") for part in Path(path).parts):
            continue
        if stage != b"0":
            results.append((path, 0, "unmerged index entry"))
            continue
        content = _git(repo, "cat-file", "blob", oid.decode())
        if mode == b"120000":
            results.append((path, 0, "DFT symlink requires manual review"))
        results.extend((path, line, category) for line, category in findings(content, private_values))
        if private_artifact or Path(path).name == "profiles.json":
            results.append((path, 0, "private configuration artifact"))
    return results


def scan_tree(root: Path, private_values: list[str]) -> list[tuple[str, int, str]]:
    results = []
    for path in sorted(root.rglob("*")):
        if any(part in {".git", "archived", "__pycache__", ".pytest_cache"} for part in path.parts):
            continue
        relative = str(path.relative_to(root))
        if path.is_symlink():
            results.append((relative, 0, "DFT symlink requires manual review"))
        elif path.is_file() and path.name != ".DS_Store":
            results.extend((relative, line, kind) for line, kind in findings(path.read_bytes(), private_values))
    return results


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--staged", action="store_true")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    try:
        config_dir()  # Reject configuration accidentally placed inside a checkout.
        results = (scan_index if args.staged else scan_tree)(args.root.resolve(), markers())
        for path, line, category in results:
            print(f"{path}:{line}: {category}", file=sys.stderr)
        return int(bool(results))
    except (ValueError, OSError, subprocess.CalledProcessError):
        print("DFT privacy check failed; inspect local configuration and Git index", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
