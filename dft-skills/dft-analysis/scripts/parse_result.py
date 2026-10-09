#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from adapters import parse_quantum_espresso, parse_vasp
from adapters.base import write_result

CONTRACTS_ROOT = Path(__file__).resolve().parents[2] / "dft-contracts"
sys.path.insert(0, str(CONTRACTS_ROOT))
from dft_contracts.project import artifact_path


PARSERS = {
    "vasp": parse_vasp,
    "quantum-espresso": parse_quantum_espresso,
    "qe": parse_quantum_espresso,
}


def detect_engine(task_dir: Path) -> str:
    if (task_dir / "OUTCAR").is_file():
        return "vasp"
    for path in task_dir.glob("*.out"):
        sample = path.read_text(encoding="utf-8", errors="replace")[:200_000]
        if "Program PWSCF" in sample or "Quantum ESPRESSO" in sample:
            return "quantum-espresso"
    raise ValueError("cannot detect VASP or Quantum ESPRESSO output")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="dft-parse-result")
    parser.add_argument("--task-dir", type=Path, required=True)
    parser.add_argument("--engine", choices=("auto", *PARSERS), default="auto")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    task_dir = args.task_dir.expanduser().resolve()
    try:
        engine = detect_engine(task_dir) if args.engine == "auto" else args.engine
        result = PARSERS[engine](task_dir)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        if args.write or args.output:
            if (task_dir / "workflow.json").is_file():
                expected = artifact_path(task_dir, "data", "result", ".json")
                if args.output and args.output.expanduser().resolve() != expected:
                    raise ValueError("Canonical task results must use the routed task analysis location")
                output = expected
            else:
                output = (args.output or (task_dir / "result.json")).expanduser().resolve()
            write_result(output, result, overwrite=args.overwrite)
            print(f"[ok] wrote {output}")
        return 0 if result["termination"]["normal"] else 1
    except (OSError, ValueError) as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

