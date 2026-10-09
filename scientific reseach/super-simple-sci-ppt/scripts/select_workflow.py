"""Resolve the portable presentation format without modifying files."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


SUPPORTED_FORMATS = frozenset({"pptx", "beamer"})
_BEAMER_DOCUMENTCLASS_RE = re.compile(
    r"\\documentclass\s*(?:\[[^\]]*\])?\s*\{\s*beamer\s*\}",
    re.IGNORECASE | re.DOTALL,
)


def _existing_file(existing: str | Path) -> Path:
    path = Path(existing)
    if not path.is_file():
        raise ValueError(f"--existing must name an existing file: {path}")
    return path


def _infer_existing_format(path: Path) -> str:
    suffix = path.suffix.casefold()
    if suffix in {".pptx", ".ppt"}:
        # Legacy .ppt files are continued through the PPTX workflow; the
        # conversion step is documented by the package README.
        return "pptx"
    if suffix == ".tex":
        try:
            text = path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeError) as exc:
            raise ValueError(f"cannot read existing TeX source: {path}") from exc
        # Ignore ordinary TeX comments so an article that merely mentions a
        # Beamer documentclass in prose cannot be routed as a presentation.
        uncommented = re.sub(r"(?m)(?<!\\)%[^\r\n]*", "", text)
        if not _BEAMER_DOCUMENTCLASS_RE.search(uncommented):
            raise ValueError(
                "existing .tex is not a Beamer entry; article/report TeX cannot be used as a presentation source"
            )
        return "beamer"
    if suffix == ".pdf":
        raise ValueError("a PDF alone does not establish the source format; specify --format")
    raise ValueError(
        f"cannot infer presentation format from existing source {path.name!r}; specify --format"
    )


def select_format(explicit: str | None = None, existing: str | Path | None = None) -> str:
    """Choose ``pptx`` or ``beamer`` with explicit format precedence.

    An ``existing`` argument always has to name a real file.  Its extension is
    still validated when an explicit format is supplied so an article TeX file
    cannot silently enter the presentation workflow.  A PDF becomes usable
    only when the caller explicitly supplies the target format.
    """

    if explicit is not None:
        normalized = explicit.strip().casefold() if isinstance(explicit, str) else explicit
        if normalized not in SUPPORTED_FORMATS:
            raise ValueError("format must be pptx or beamer")
        if existing is not None:
            path = _existing_file(existing)
            if path.suffix.casefold() == ".tex":
                _infer_existing_format(path)  # validate Beamer class even with explicit output format
            elif path.suffix.casefold() == ".pdf":
                # Explicit format is the required disambiguation for a PDF.
                pass
        return normalized

    if existing is None:
        # New projects retain the package's documented PPTX default.  A
        # provided-but-missing source is handled by _existing_file below.
        return "pptx"
    return _infer_existing_format(_existing_file(existing))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--format", choices=sorted(SUPPORTED_FORMATS))
    parser.add_argument("--existing", help="existing editable presentation source")
    args = parser.parse_args()
    from skill_runtime import require_current

    try:
        installation = require_current()
        selected = select_format(args.format, args.existing)
    except (ValueError, RuntimeError) as error:
        parser.error(str(error))
    root = Path(__file__).resolve().parents[1]
    print(
        json.dumps(
            {
                "format": selected,
                "skill": str(root / "SKILL.md"),
                "preflight": installation,
                "format_rules": str(root / "references" / (selected + ".md")),
                "reason": "explicit"
                if args.format
                else "existing-source"
                if args.existing
                else "new-default",
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
