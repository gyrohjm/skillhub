#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dft_contracts import capability_registry, validate_document  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="dft-contract-validate")
    parser.add_argument("contract")
    parser.add_argument("document", nargs="?", type=Path)
    args = parser.parse_args(argv)
    if args.contract == "capabilities":
        document = capability_registry() if args.document is None else json.loads(args.document.read_text(encoding="utf-8"))
        errors = [] if isinstance(document.get("engines"), dict) else ["<root>: engines object is required"]
    else:
        if args.document is None:
            parser.error("document is required")
        document = json.loads(args.document.read_text(encoding="utf-8"))
        errors = validate_document(args.contract, document)
    if errors:
        for error in errors:
            print(f"[error] {error}", file=sys.stderr)
        return 1
    print(f"[ok] valid {args.contract}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

