from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any

CONTRACTS_ROOT = Path(__file__).resolve().parents[3] / "dft-contracts"
sys.path.insert(0, str(CONTRACTS_ROOT))

from dft_contracts import sha256_file, validate_document  # noqa: E402


PARSER_VERSION = "1.0.0"


def source_record(path: Path, root: Path) -> dict[str, Any]:
    return {
        "path": path.relative_to(root).as_posix(),
        "sha256": sha256_file(path),
        "size": path.stat().st_size,
    }


def source_records(root: Path, names: tuple[str, ...]) -> list[dict[str, Any]]:
    return [source_record(root / name, root) for name in names if (root / name).is_file()]


def max_norm(vectors: list[list[float]]) -> float | None:
    if not vectors:
        return None
    return max(math.sqrt(sum(component * component for component in vector)) for vector in vectors)


def parse_poscar(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    lines = [line.strip() for line in path.read_text(encoding="utf-8", errors="replace").splitlines() if line.strip()]
    if len(lines) < 8:
        return None
    try:
        scale = float(lines[1].split()[0])
        lattice = [[float(value) * scale for value in lines[index].split()[:3]] for index in range(2, 5)]
    except (ValueError, IndexError):
        return None
    symbols = lines[5].split()
    try:
        counts = [int(value) for value in lines[6].split()]
    except ValueError:
        return None
    cursor = 7
    selective = lines[cursor].lower().startswith("s")
    if selective:
        cursor += 1
    mode = lines[cursor]
    cursor += 1
    nions = sum(counts)
    positions: list[list[float]] = []
    for line in lines[cursor : cursor + nions]:
        try:
            positions.append([float(value) for value in line.split()[:3]])
        except ValueError:
            return None
    return {
        "comment": lines[0],
        "lattice_A": lattice,
        "elements": symbols,
        "counts": counts,
        "coordinate_mode": mode,
        "selective_dynamics": selective,
        "positions": positions,
    }


def result_skeleton(engine: str, task_dir: Path, parser_name: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "contract": "dft.result.v1",
        "engine": engine,
        "engine_version": None,
        "task_dir": str(task_dir),
        "parser": {"name": parser_name, "version": PARSER_VERSION},
        "termination": {"normal": False, "status": "incomplete"},
        "convergence": {"electronic": None, "ionic": None},
        "energy": None,
        "forces": None,
        "stress": None,
        "magnetization": None,
        "final_structure": None,
        "electronic_structure": None,
        "source_files": [],
        "warnings": [],
        "confidence": "provisional",
    }


def validate_result(result: dict[str, Any]) -> None:
    errors = validate_document("result-v1", result)
    if errors:
        raise ValueError("invalid dft.result.v1: " + " | ".join(errors))


def write_result(path: Path, result: dict[str, Any], *, overwrite: bool = False) -> None:
    validate_result(result)
    if path.exists() and not overwrite:
        raise FileExistsError(f"refusing to overwrite result: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

