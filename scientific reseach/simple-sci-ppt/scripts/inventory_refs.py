#!/usr/bin/env python
"""Create a markdown inventory for a folder of reference materials."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


PAPER_EXTS = {".pdf", ".docx", ".doc", ".tex"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp", ".svg", ".bmp"}
NOTE_EXTS = {".md", ".txt", ".rtf"}
DATA_EXTS = {".csv", ".tsv", ".xlsx", ".xls", ".json", ".yaml", ".yml"}
CODE_EXTS = {".py", ".ipynb", ".js", ".m", ".jl", ".R", ".r"}
SLIDE_EXTS = {".pptx", ".ppt", ".key", ".odp"}
BIB_EXTS = {".bib", ".ris", ".enw"}


@dataclass(frozen=True)
class RefFile:
    path: Path
    category: str
    role: str
    size_mb: float
    modified: str


def classify(path: Path) -> tuple[str, str]:
    ext = path.suffix.lower()
    if ext in PAPER_EXTS:
        return "paper", "extract metadata, question, method, main results, limitations"
    if ext in IMAGE_EXTS:
        return "figure", "inspect visual evidence; preserve aspect ratio in slides"
    if ext in NOTE_EXTS:
        return "note", "use as user-authored interpretation or slide storyline"
    if ext in DATA_EXTS:
        return "data", "use for tables, quantitative comparison, or generated plots"
    if ext in CODE_EXTS:
        return "code/notebook", "extract reproducible workflow, algorithm, or generated figures"
    if ext in SLIDE_EXTS:
        return "prior slides", "reuse style anchors or selected content with attribution"
    if ext in BIB_EXTS:
        return "bibliography", "extract citation metadata and related-paper list"
    return "other", "inspect only if relevant to the presentation objective"


def collect(root: Path) -> list[RefFile]:
    files: list[RefFile] = []
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        category, role = classify(path)
        stat = path.stat()
        files.append(
            RefFile(
                path=path,
                category=category,
                role=role,
                size_mb=stat.st_size / (1024 * 1024),
                modified=datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
            )
        )
    return files


def md_escape(text: str) -> str:
    return text.replace("|", "\\|")


def render(root: Path, files: list[RefFile]) -> str:
    counts: dict[str, int] = {}
    for item in files:
        counts[item.category] = counts.get(item.category, 0) + 1

    lines = [
        "# Reference Folder Inventory",
        "",
        f"- Folder: `{root}`",
        f"- File count: {len(files)}",
        f"- Categories: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())),
        "",
        "## Files",
        "",
        "| File | Category | Suggested role | Size (MB) | Modified |",
        "|---|---|---|---:|---|",
    ]
    for item in files:
        rel = item.path.relative_to(root)
        lines.append(
            f"| `{md_escape(str(rel))}` | {item.category} | {md_escape(item.role)} | {item.size_mb:.2f} | {item.modified} |"
        )

    lines.extend(
        [
            "",
            "## Planning Notes",
            "",
            "- Treat papers as claim sources and figures as evidence objects.",
            "- Extract metadata and main claims before designing slides.",
            "- Build a claim-evidence map before writing the generator script.",
            "- Use only figures that support the slide storyline; avoid filling pages with unrelated images.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Inventory a reference folder for simple-sci-ppt planning.")
    parser.add_argument("folder", help="Folder containing papers, images, notes, code, or prior slides.")
    parser.add_argument("--out", help="Optional markdown output path.")
    args = parser.parse_args()

    root = Path(args.folder).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise SystemExit(f"Reference folder does not exist or is not a directory: {root}")

    text = render(root, collect(root))
    if args.out:
        out = Path(args.out).expanduser().resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
