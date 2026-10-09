#!/usr/bin/env python3
"""Report validated DFT execution-backend capabilities."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

CONTRACTS_ROOT = Path(__file__).resolve().parents[2] / "dft-contracts"
sys.path.insert(0, str(CONTRACTS_ROOT))

from dft_contracts import capability_registry  # noqa: E402

BACKEND_RUNTIME: dict[str, dict[str, Any]] = {
    "vasp": {
        "helper": "python -m vwf",
        "required_commands": [],
        "note": "Use scripts/canonical_workflow.py prepare for canonical leaves; vwf remains legacy-only. Canonical submission is not yet implemented.",
    },
    "quantum-espresso": {
        "helper": "python -m qewf",
        "required_commands": [],
        "note": "Use scripts/canonical_workflow.py prepare for reviewed prebuilt QE inputs in canonical leaves; qewf remains legacy-only. Canonical submission is not yet implemented.",
    },
    "cp2k": {
        "helper": None,
        "required_commands": ["cp2k"],
        "note": "Design/records/analysis contracts are available; input generation and submission are not implemented.",
    },
    "abinit": {
        "helper": None,
        "required_commands": ["abinit"],
        "note": "Design/records/analysis contracts are available; input generation and submission are not implemented.",
    },
    "gpaw": {
        "helper": None,
        "required_commands": ["gpaw"],
        "note": "Design/records/analysis contracts are available; input generation and submission are not implemented.",
    },
}


def backend_specs() -> dict[str, dict[str, Any]]:
    registry = capability_registry()["engines"]
    return {
        name: {**capabilities, **BACKEND_RUNTIME.get(name, {})}
        for name, capabilities in registry.items()
    }


def report(engine: str | None = None) -> dict[str, Any]:
    backends = backend_specs()
    selected = backends if engine is None else {engine: backends[engine]}
    result: dict[str, Any] = {}
    for name, spec in selected.items():
        item = dict(spec)
        item["commands_found"] = {
            command: shutil.which(command) for command in item["required_commands"]
        }
        result[name] = item
    return result


def main(argv: list[str] | None = None) -> int:
    backends = backend_specs()
    parser = argparse.ArgumentParser(prog="dft_backend.py")
    parser.add_argument("engine", nargs="?", choices=sorted(backends))
    args = parser.parse_args(argv)
    print(json.dumps(report(args.engine), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
