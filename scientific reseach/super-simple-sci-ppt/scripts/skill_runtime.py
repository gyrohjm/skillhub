"""Validate the self-contained ``super-simple-sci-ppt`` skill package.

The published skill is portable: its runtime checks the files beside this
script and does not consult a maintained source tree, a global installation,
or an installation receipt.  The same checks therefore work when the package
is copied to a temporary directory and launched from an unrelated cwd.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
from pathlib import Path, PurePosixPath
from typing import Iterator
from urllib.parse import unquote, urlsplit


INSTALLATION_NAME = ".installation.json"

# Keep this list deliberately explicit.  A package can contain additional
# implementation files, but these files are the public contract required by
# the portable skill runtime.
REQUIRED_FILES = (
    "SKILL.md",
    "README.md",
    "agents/openai.yaml",
    "assets/beamer-template.tex",
    "assets/pptx-starter.mjs",
    "references/beamer.md",
    "references/pptx.md",
    "references/project-lifecycle.md",
    "references/validation.md",
    "scripts/skill_runtime.py",
    "scripts/select_workflow.py",
    "scripts/project_manifest.py",
    "scripts/visible_payload.py",
    "scripts/visible_text_lint.py",
    "scripts/pptx_slide_order.py",
    "scripts/render_and_check.py",
)


class SkillRuntimeError(RuntimeError):
    """The portable skill package is incomplete or unsafe to fingerprint."""


def _is_link_or_junction(path: Path, entry: os.DirEntry[str] | None = None) -> bool:
    """Return whether a path is a symlink or Windows reparse-point directory."""

    if path.is_symlink() or (entry is not None and entry.is_symlink()):
        return True
    is_junction = getattr(path, "is_junction", None)
    if callable(is_junction) and is_junction():
        return True
    # ``Path.is_junction`` is unavailable on some supported Python versions.
    # On Windows, the reparse-point attribute covers junctions and symlink
    # variants; on other systems the attribute is absent and this is a no-op.
    try:
        attributes = getattr(os.lstat(path), "st_file_attributes", 0)
    except OSError:
        attributes = 0
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def _root_path(root: Path | str) -> Path:
    """Return a resolved package root, rejecting a symlinked root itself."""

    candidate = Path(root)
    if _is_link_or_junction(candidate):
        raise SkillRuntimeError(f"skill root must not be a symbolic link or junction: {candidate}")
    if not candidate.exists():
        raise SkillRuntimeError(f"skill root does not exist: {candidate}")
    if not candidate.is_dir():
        raise SkillRuntimeError(f"skill root is not a directory: {candidate}")
    return candidate.resolve()


def _walk_files(root: Path) -> Iterator[tuple[str, Path]]:
    """Yield regular files in stable relative-name order.

    ``Path.rglob`` may skip a symlinked directory on some platforms.  Walking
    with ``os.scandir(..., follow_symlinks=False)`` lets us reject symlinks,
    including symlinked directories, before they can be silently omitted or
    followed.
    """

    pending = [root]
    while pending:
        directory = pending.pop()
        try:
            with os.scandir(directory) as iterator:
                entries = sorted(iterator, key=lambda item: item.name)
        except OSError as exc:
            raise SkillRuntimeError(f"cannot read skill directory: {directory}") from exc

        for entry in entries:
            path = Path(entry.path)
            relative = path.relative_to(root).as_posix()
            try:
                if _is_link_or_junction(path, entry):
                    raise SkillRuntimeError(
                        f"skill file must not be a symbolic link or junction: {relative}"
                    )
                if entry.is_dir(follow_symlinks=False):
                    pending.append(path)
                    continue
                if entry.is_file(follow_symlinks=False):
                    yield relative, path
                    continue
                raise SkillRuntimeError(f"skill tree contains a non-regular entry: {relative}")
            except OSError as exc:
                raise SkillRuntimeError(f"cannot inspect skill entry: {relative}") from exc


def _is_excluded(relative: str) -> bool:
    path = PurePosixPath(relative)
    return (
        "__pycache__" in path.parts
        or path.suffix.casefold() == ".pyc"
        or path.name == INSTALLATION_NAME
    )


def tree_files(root: Path | str) -> dict[str, Path]:
    """Return the fingerprinted files, keyed by portable relative filename.

    Caches and installation receipts are intentionally excluded.  Symlinks
    are rejected even when their names would otherwise be excluded.
    """

    package = _root_path(root)
    files: dict[str, Path] = {}
    for relative, path in _walk_files(package):
        if not _is_excluded(relative):
            files[relative] = path
    return dict(sorted(files.items()))


def tree_sha256(root: Path | str) -> str:
    """Fingerprint sorted relative filenames and their exact bytes.

    Length-prefixing the UTF-8 filename and file bytes avoids ambiguous
    concatenations while keeping the result independent of host paths,
    directory order, and mtimes.
    """

    digest = hashlib.sha256()
    for relative, path in tree_files(root).items():
        name = relative.encode("utf-8")
        data = path.read_bytes()
        digest.update(len(name).to_bytes(8, "big"))
        digest.update(name)
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
    return digest.hexdigest()


_MARKDOWN_LINK_RE = re.compile(
    r"!?\[[^\]]*\]\(\s*(?P<target><[^>]*>|(?:\\.|[^\s)])+)"
)
_MARKDOWN_REFERENCE_RE = re.compile(
    r"^\s{0,3}\[[^\]]+\]:\s*(?P<target><[^>]*>|(?:\\.|[^\s]+))"
)


def _markdown_targets(text: str) -> Iterator[str]:
    """Yield link destinations from Markdown outside fenced code blocks."""

    fenced = False
    fence_marker = ""
    for line in text.splitlines():
        stripped = line.lstrip()
        fence = re.match(r"(`{3,}|~{3,})", stripped)
        if fence:
            marker = fence.group(1)[0]
            if not fenced:
                fenced = True
                fence_marker = marker
            elif marker == fence_marker:
                fenced = False
            continue
        if fenced:
            continue

        for match in _MARKDOWN_LINK_RE.finditer(line):
            target = match.group("target").strip()
            yield target[1:-1] if target.startswith("<") and target.endswith(">") else target
        reference = _MARKDOWN_REFERENCE_RE.match(line)
        if reference:
            target = reference.group("target").strip()
            yield target[1:-1] if target.startswith("<") and target.endswith(">") else target


def _markdown_link_errors(root: Path, files: dict[str, Path]) -> list[str]:
    root = Path(root).resolve()
    errors: list[str] = []
    for relative, source in files.items():
        if source.suffix.casefold() != ".md":
            continue
        try:
            text = source.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeError) as exc:
            errors.append(f"{relative}: cannot read Markdown ({exc})")
            continue

        for raw_target in _markdown_targets(text):
            target = raw_target.strip()
            if not target or target.startswith("#"):
                continue
            # Check native absolute paths before URL parsing: on Windows,
            # ``urlsplit('C:/...')`` reports ``C`` as a URL scheme.
            decoded_target = unquote(target)
            if decoded_target.startswith("//"):
                # Protocol-relative web URLs are external links.
                continue
            if decoded_target.startswith(("/", "\\")) or re.match(
                r"^[A-Za-z]:[\\/]", decoded_target
            ):
                errors.append(f"{relative}: local link is not relative: {raw_target}")
                continue
            parsed = urlsplit(target)
            # Schemes, protocol-relative URLs, and query-only/fragment-only
            # links are not package-local files.
            if parsed.scheme or parsed.netloc:
                continue
            target_path = unquote(parsed.path)
            if not target_path:
                continue
            if target_path.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:[\\/]", target_path):
                errors.append(f"{relative}: local link is not relative: {raw_target}")
                continue
            if "\\" in target_path:
                errors.append(f"{relative}: local link must use '/': {raw_target}")
                continue
            candidate = (source.parent / Path(*PurePosixPath(target_path).parts)).resolve()
            try:
                candidate.relative_to(root)
            except ValueError:
                errors.append(f"{relative}: local link escapes the skill package: {raw_target}")
                continue
            if not candidate.is_file():
                errors.append(f"{relative}: local link target is missing: {raw_target}")
    return errors


def _invalid_result(root: Path | None, reason: str) -> dict:
    return {
        "status": "invalid",
        "skill_root": str(root) if root is not None else None,
        "project_skill_sha256": None,
        "skill_sha256": None,
        "reason": reason,
    }


def preflight(skill_root: Path | str | None = None) -> dict:
    """Validate the current portable package and return a JSON-safe report."""

    requested = Path(skill_root) if skill_root is not None else Path(__file__).resolve().parents[1]
    root: Path | None = None
    try:
        root = _root_path(requested)
        files = tree_files(root)
        missing = [name for name in REQUIRED_FILES if name not in files]
        if missing:
            raise SkillRuntimeError("missing required bundled files: " + ", ".join(missing))
        link_errors = _markdown_link_errors(root, files)
        if link_errors:
            raise SkillRuntimeError("broken relative Markdown links: " + " | ".join(link_errors))
        fingerprint = tree_sha256(root)
    except (OSError, UnicodeError, SkillRuntimeError, ValueError) as exc:
        return _invalid_result(root or requested, str(exc))

    return {
        "status": "passed",
        "skill_root": str(root),
        "project_skill_sha256": fingerprint,
        # Keep the historical manifest key while exposing a package-local name
        # for callers that do not need to know the old terminology.
        "skill_sha256": fingerprint,
        "required_files": list(REQUIRED_FILES),
    }


def require_current(skill_root: Path | str | None = None) -> dict:
    """Return a passing preflight report or raise a useful JSON error."""

    result = preflight(skill_root)
    if result["status"] != "passed":
        raise SkillRuntimeError(json.dumps(result, ensure_ascii=False))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skill-root",
        type=Path,
        help="package root to validate (defaults to the directory containing this script)",
    )
    args = parser.parse_args()
    result = preflight(args.skill_root)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["status"] == "passed" else 1)


if __name__ == "__main__":
    main()
