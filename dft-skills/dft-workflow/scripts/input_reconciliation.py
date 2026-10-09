#!/usr/bin/env python3
"""Reconcile current engine inputs with the latest workflow parameter snapshot.

The reconciler is deliberately file-preserving.  It reads the input files in a
task leaf, compares normalized engine semantics with the snapshot recorded in
``workflow.json``, and only updates planning ledgers when ``write=True``.
Engine input files are never generated or rewritten here.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


class ReconciliationError(ValueError):
    """Raised when a task or one of its planning records cannot be read."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _canonical_hash(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normal_scalar(value: Any) -> Any:
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        return value
    if not isinstance(value, str):
        return value
    text = value.strip().strip("'\"")
    lowered = text.lower()
    if lowered in {".true.", "true", "t", ".t."}:
        return True
    if lowered in {".false.", "false", "f", ".f."}:
        return False
    try:
        number = float(re.sub(r"[dD]", "e", text))
    except ValueError:
        return re.sub(r"\s+", " ", text).lower()
    if number.is_integer() and re.fullmatch(r"[+-]?\d+", text):
        return int(number)
    return number


def _normalize_nested(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _normalize_nested(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalize_nested(item) for item in value]
    if isinstance(value, tuple):
        return [_normalize_nested(item) for item in value]
    if isinstance(value, str):
        text = value.strip().strip("'\"")
        lowered = text.lower()
        if lowered in {".true.", "true", "t", ".t."}:
            return True
        if lowered in {".false.", "false", "f", ".f."}:
            return False
        try:
            number = float(re.sub(r"[dD]", "e", text))
        except ValueError:
            return re.sub(r"\s+", " ", text)
        if number.is_integer() and re.fullmatch(r"[+-]?\d+", text):
            return int(number)
        return number
    return value


def _same_value(left: Any, right: Any) -> bool:
    def comparable(value: Any) -> Any:
        if isinstance(value, Mapping):
            return {str(key): comparable(item) for key, item in value.items()}
        if isinstance(value, list):
            return [comparable(item) for item in value]
        if isinstance(value, tuple):
            return [comparable(item) for item in value]
        return _normal_scalar(value)

    return comparable(left) == comparable(right)


def _strip_comment(line: str, markers: str) -> str:
    positions = [line.find(marker) for marker in markers if marker in line]
    return line[: min(positions)] if positions else line


def _find_input(task_root: Path, name: str) -> Path | None:
    exact = task_root / name
    if exact.is_file():
        return exact
    wanted = name.casefold()
    for candidate in task_root.iterdir():
        if candidate.is_file() and candidate.name.casefold() == wanted:
            return candidate
    return None


def _parse_incar(text: str) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for raw_line in text.splitlines():
        line = _strip_comment(raw_line, "#!")
        for statement in line.split(";"):
            if "=" not in statement:
                continue
            key, value = statement.split("=", 1)
            key = key.strip().upper()
            if key:
                values[key] = _normal_scalar(value)
    return values


def _parse_mesh_line(line: str) -> str | None:
    numbers = re.findall(r"[+-]?\d+", line)
    if len(numbers) < 3:
        return None
    return "x".join(numbers[:3])


def _parse_vasp_kpoints(text: str) -> dict[str, Any]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) < 4:
        return {"parse_error": "KPOINTS is too short"}
    mesh = _parse_mesh_line(lines[3])
    if mesh is None:
        return {"parse_error": "automatic KPOINTS mesh is not parseable"}
    offset = _parse_mesh_line(lines[4]) if len(lines) >= 5 else None
    result: dict[str, Any] = {"mesh": mesh}
    if offset is not None:
        result["offset"] = offset
    return result


def _float_row(text: str, width: int = 3) -> list[float] | None:
    parts = text.split()
    if len(parts) < width:
        return None
    try:
        return [float(re.sub(r"[dD]", "e", part)) for part in parts[:width]]
    except ValueError:
        return None


def _parse_poscar(text: str) -> dict[str, Any]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) < 8:
        return {"parse_error": "POSCAR is too short"}
    try:
        scale = float(re.sub(r"[dD]", "e", lines[1].split()[0]))
    except (IndexError, ValueError):
        return {"parse_error": "POSCAR scale is not parseable"}
    cell: list[list[float]] = []
    for line in lines[2:5]:
        row = _float_row(line)
        if row is None:
            return {"parse_error": "POSCAR lattice is not parseable"}
        cell.append([scale * value for value in row])

    species_index = 5
    species = lines[species_index].split()
    counts_index = 6
    try:
        counts = [int(item) for item in lines[counts_index].split()]
    except (IndexError, ValueError):
        # VASP-4 format has no species line; retain the count semantics even
        # though element identity must then be supplied by the plan.
        try:
            counts = [int(item) for item in lines[5].split()]
        except (IndexError, ValueError):
            return {"parse_error": "POSCAR atom counts are not parseable"}
        species = []
        counts_index = 5
    if len(species) != len(counts) and species:
        return {"parse_error": "POSCAR species/count columns do not match"}
    natoms = sum(counts)
    coordinate_index = counts_index + 1
    selective = False
    if coordinate_index < len(lines) and lines[coordinate_index].lower().startswith("s"):
        selective = True
        coordinate_index += 1
    if coordinate_index >= len(lines):
        return {"parse_error": "POSCAR coordinate mode is missing"}
    coordinate_mode = lines[coordinate_index].split()[0].lower()
    coordinate_index += 1
    positions: list[list[float]] = []
    constraints: list[list[str]] = []
    for line in lines[coordinate_index : coordinate_index + natoms]:
        row = _float_row(line)
        if row is None:
            return {"parse_error": "POSCAR positions are not parseable"}
        positions.append(row)
        if selective:
            flags = [item.upper() for item in line.split()[3:6]]
            constraints.append(flags)
    if len(positions) != natoms:
        return {"parse_error": "POSCAR contains fewer positions than its atom count"}
    result: dict[str, Any] = {
        "species": species,
        "counts": counts,
        "natoms": natoms,
        "cell": cell,
        "coordinate_mode": coordinate_mode,
        "positions": positions,
        "selective_dynamics": selective,
    }
    if selective:
        result["constraints"] = constraints
    return _normalize_nested(result)


def _parse_potcar(text: str) -> dict[str, Any]:
    identities = []
    for pattern in (r"^\s*TITEL\s*=\s*(.+?)\s*$", r"^\s*VRHFIN\s*=\s*(.+?)\s*$"):
        identities.extend(match.group(1).strip() for match in re.finditer(pattern, text, flags=re.MULTILINE))
        if identities:
            break
    if not identities:
        identities = [f"sha256:{hashlib.sha256(text.encode('utf-8')).hexdigest()}"]
    return {"identity": [re.sub(r"\s+", " ", item).lower() for item in identities]}


def _parse_qe_blocks(texts: list[str]) -> tuple[dict[str, Any], dict[str, Any]]:
    parameters: dict[str, Any] = {}
    species: list[str] = []
    pseudopotentials: list[str] = []
    positions: list[list[Any]] = []
    cell: list[list[float]] = []
    constraints: list[Any] = []
    mesh: str | None = None
    section_re = re.compile(
        r"^(?:K_POINTS|ATOMIC_SPECIES|ATOMIC_POSITIONS|CELL_PARAMETERS|CONSTRAINTS|\s*&[A-Za-z])",
        flags=re.IGNORECASE,
    )

    for text in texts:
        lines = text.splitlines()
        for index, raw_line in enumerate(lines):
            line = _strip_comment(raw_line, "!").strip()
            if not line:
                continue
            for match in re.finditer(
                r"\b([A-Za-z][A-Za-z0-9_]*)\s*=\s*([^,\n/]+)", line
            ):
                parameters[match.group(1).lower()] = _normal_scalar(match.group(2))
            if re.match(r"K_POINTS\s+automatic", line, flags=re.IGNORECASE):
                if index + 1 < len(lines):
                    values = _strip_comment(lines[index + 1], "!").split()
                    mesh = _parse_mesh_line(" ".join(values[:3]))
                continue
            section = re.match(
                r"^(ATOMIC_SPECIES|ATOMIC_POSITIONS|CELL_PARAMETERS|CONSTRAINTS)\b",
                line,
                flags=re.IGNORECASE,
            )
            if not section:
                continue
            block = section.group(1).upper()
            cursor = index + 1
            while cursor < len(lines):
                candidate = _strip_comment(lines[cursor], "!").strip()
                if not candidate or section_re.match(candidate):
                    break
                parts = candidate.split()
                if block == "ATOMIC_SPECIES" and len(parts) >= 3:
                    species.append(parts[0])
                    pseudopotentials.append(parts[2])
                elif block == "ATOMIC_POSITIONS" and len(parts) >= 4:
                    row: list[Any] = [parts[0]]
                    numeric = _float_row(" ".join(parts[1:4]))
                    if numeric is not None:
                        row.extend(numeric)
                        positions.append(row)
                        if len(parts) > 4:
                            constraints.append(parts[4:7])
                elif block == "CELL_PARAMETERS":
                    numeric = _float_row(candidate)
                    if numeric is not None:
                        cell.append(numeric)
                elif block == "CONSTRAINTS":
                    constraints.append(parts)
                cursor += 1

    semantics: dict[str, Any] = {}
    if species:
        semantics["species"] = species
    if pseudopotentials:
        semantics["pseudopotential"] = pseudopotentials
    if positions:
        semantics["positions"] = positions
    if cell:
        semantics["cell"] = cell[:3]
    if constraints:
        semantics["constraints"] = constraints
    if mesh is not None:
        semantics["k_mesh"] = mesh
        parameters["KPOINTS"] = mesh
    return _normalize_nested(parameters), _normalize_nested(semantics)


def parse_current_inputs(
    engine: str, task_root: Path, primary_input: str | None = None,
    *, previous_snapshot: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Parse current on-disk inputs into normalized values and file hashes."""

    root = Path(task_root).expanduser().resolve()
    if not root.is_dir():
        raise ReconciliationError(f"task root does not exist: {root}")
    normalized_engine = engine.strip().lower()
    if normalized_engine == "qe":
        normalized_engine = "quantum-espresso"
    file_hashes: dict[str, str] = {}
    file_records: dict[str, dict[str, Any]] = {}
    file_semantics: dict[str, Any] = {}
    parameters: dict[str, Any] = {}
    errors: list[str] = []

    # Cache lives inside the existing input snapshot, not a parallel task ledger.
    # Hash the exact bytes we parse; mtimes alone cannot detect manual edits.
    previous_cache = (previous_snapshot or {}).get("parser_cache", {})
    if not isinstance(previous_cache, Mapping) or (
        previous_cache.get("version") != 1
        or previous_cache.get("engine") != normalized_engine
    ):
        previous_cache = {}
    cached_files = previous_cache.get("files", {})
    if not isinstance(cached_files, Mapping):
        cached_files = {}
    parsed_files: dict[str, Any] = {}

    def parse_file(name: str, path: Path, parser: Any) -> Any:
        data = path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        file_hashes[name] = digest
        prior = cached_files.get(name)
        if (isinstance(prior, Mapping) and prior.get("sha256") == digest
                and isinstance(prior.get("value"), dict)
                and prior.get("value_hash") == _canonical_hash(prior["value"])):
            value = copy.deepcopy(prior["value"])
        else:
            value = parser(data.decode("utf-8", errors="replace"))
        parsed_files[name] = {"sha256": digest, "value": copy.deepcopy(value),
                              "value_hash": _canonical_hash(value)}
        return value

    if normalized_engine == "vasp":
        names = ("INCAR", "KPOINTS", "POSCAR", "POTCAR")
        paths = {name: _find_input(root, name) for name in names}
        incar = paths["INCAR"]
        if incar is not None:
            incar_values = parse_file("INCAR", incar, _parse_incar)
            parameters.update(incar_values)
            file_semantics["INCAR"] = {"parameters": incar_values}
        else:
            errors.append("INCAR is missing")
        kpoints = paths["KPOINTS"]
        if kpoints is not None:
            kpoints_semantics = parse_file("KPOINTS", kpoints, _parse_vasp_kpoints)
            file_semantics["KPOINTS"] = kpoints_semantics
            if "mesh" in kpoints_semantics:
                parameters["KPOINTS"] = kpoints_semantics["mesh"]
            if "parse_error" in kpoints_semantics:
                errors.append(str(kpoints_semantics["parse_error"]))
        else:
            errors.append("KPOINTS is missing")
        poscar = paths["POSCAR"]
        if poscar is not None:
            file_semantics["POSCAR"] = parse_file("POSCAR", poscar, _parse_poscar)
        else:
            errors.append("POSCAR is missing")
        potcar = paths["POTCAR"]
        if potcar is not None:
            file_semantics["POTCAR"] = parse_file("POTCAR", potcar, _parse_potcar)
        else:
            errors.append("POTCAR is missing")
    elif normalized_engine == "quantum-espresso":
        input_paths: list[Path] = []
        if primary_input is not None:
            primary = _find_input(root, Path(primary_input).name)
            if primary is None:
                raise ReconciliationError(f"primary QE input does not exist: {root / primary_input}")
            input_paths.append(primary)
        for candidate in sorted(root.iterdir(), key=lambda item: item.name.casefold()):
            if candidate.is_file() and candidate.suffix.casefold() == ".in" and candidate not in input_paths:
                input_paths.append(candidate)
        if not input_paths:
            errors.append("no Quantum ESPRESSO .in input exists")
        def parse_qe_file(text: str) -> dict[str, Any]:
            values, semantic = _parse_qe_blocks([text])
            return {"parameters": values, "semantics": semantic}

        qe_parameters: dict[str, Any] = {}
        qe_semantics: dict[str, Any] = {}
        for path in input_paths:
            parsed = parse_file(path.name, path, parse_qe_file)
            qe_parameters.update(parsed["parameters"])
            for key, value in parsed["semantics"].items():
                if isinstance(value, list):
                    qe_semantics.setdefault(key, []).extend(value)
                else:
                    qe_semantics[key] = value
        if "cell" in qe_semantics:
            qe_semantics["cell"] = qe_semantics["cell"][:3]
        parameters.update(qe_parameters)
        if qe_semantics:
            file_semantics["QE_INPUT"] = qe_semantics
        for path in input_paths:
            file_semantics.setdefault(path.name, {"parameters": qe_parameters})
    else:
        raise ReconciliationError(f"input reconciliation is not implemented for engine {engine!r}")

    for name, file_hash in file_hashes.items():
        file_records[name] = {
            "path": name,
            "sha256": file_hash,
            "semantic": copy.deepcopy(file_semantics.get(name)),
        }
    semantic_snapshot = {
        "parameters": _normalize_nested(parameters),
        "file_semantics": _normalize_nested(file_semantics),
    }
    return {
        "engine": normalized_engine,
        "parameters": semantic_snapshot["parameters"],
        "file_semantics": semantic_snapshot["file_semantics"],
        "file_hashes": file_hashes,
        "files": file_records,
        "parameter_hash": _canonical_hash(semantic_snapshot),
        "primary_input": primary_input,
        "parse_errors": errors,
        "parser_cache": {"version": 1, "engine": normalized_engine, "files": parsed_files},
    }


def _snapshot_parameters(snapshot: Mapping[str, Any]) -> Mapping[str, Any]:
    parameters = snapshot.get("parameters")
    if isinstance(parameters, Mapping):
        return parameters
    if "file_semantics" not in snapshot and "file_hashes" not in snapshot:
        return snapshot
    return {}


def _snapshot_semantics(snapshot: Mapping[str, Any]) -> Mapping[str, Any]:
    semantics = snapshot.get("file_semantics")
    return semantics if isinstance(semantics, Mapping) else {}


def _snapshot_hashes(snapshot: Mapping[str, Any]) -> Mapping[str, Any]:
    hashes = snapshot.get("file_hashes")
    return hashes if isinstance(hashes, Mapping) else {}


def _append_diff(differences: list[dict[str, Any]], name: str, old: Any, new: Any) -> None:
    if not any(item["name"] == name for item in differences):
        differences.append({"name": name, "old": old, "new": new})


def _semantic_file_differences(
    baseline: Mapping[str, Any], current: Mapping[str, Any], differences: list[dict[str, Any]]
) -> None:
    old_semantics = _snapshot_semantics(baseline)
    new_semantics = _snapshot_semantics(current)
    for file_name in sorted(set(old_semantics) | set(new_semantics)):
        old_value = old_semantics.get(file_name)
        new_value = new_semantics.get(file_name)
        if _same_value(old_value, new_value):
            continue
        normalized_name = str(file_name).upper()
        if normalized_name == "POSCAR":
            _append_diff(differences, "POSCAR", old_value, new_value)
        elif normalized_name == "POTCAR":
            _append_diff(differences, "POTCAR", old_value, new_value)
        elif normalized_name == "KPOINTS":
            _append_diff(differences, "KPOINTS", old_value, new_value)
        elif normalized_name == "QE_INPUT" or str(file_name).lower().endswith(".in"):
            old_map = old_value if isinstance(old_value, Mapping) else {}
            new_map = new_value if isinstance(new_value, Mapping) else {}
            for key in ("pseudopotential", "species", "positions", "cell", "constraints"):
                if not _same_value(old_map.get(key), new_map.get(key)):
                    _append_diff(differences, key, old_map.get(key), new_map.get(key))


def semantic_diff(
    baseline: Mapping[str, Any], current: Mapping[str, Any]
) -> list[dict[str, Any]]:
    """Return deterministic parameter/structure differences, ignoring formatting."""

    differences: list[dict[str, Any]] = []
    old_parameters = _snapshot_parameters(baseline)
    new_parameters = _snapshot_parameters(current)
    for key in sorted(set(old_parameters) | set(new_parameters), key=lambda item: str(item).upper()):
        old_value = old_parameters.get(key)
        new_value = new_parameters.get(key)
        if not _same_value(old_value, new_value):
            _append_diff(differences, str(key), old_value, new_value)
    _semantic_file_differences(baseline, current, differences)

    # If an older workflow has no structural semantic snapshot, retain enough
    # information to classify a changed POSCAR/POTCAR as a major file change.
    old_hashes = _snapshot_hashes(baseline)
    new_hashes = _snapshot_hashes(current)
    for name in sorted(set(old_hashes) | set(new_hashes)):
        if old_hashes.get(name) == new_hashes.get(name):
            continue
        if str(name).upper() in {"POSCAR", "POTCAR"} and not any(
            item["name"] == name for item in differences
        ):
            _append_diff(differences, str(name), old_hashes.get(name), new_hashes.get(name))
    return differences


def _canonical_change_name(name: str) -> str:
    return re.sub(r"[\s_.-]+", "", str(name).strip().lower())


def classify_change(engine: str, name: str, old: Any, new: Any) -> str:
    """Classify one normalized engine or execution parameter change."""

    del old, new
    normalized_engine = engine.strip().lower()
    if normalized_engine == "qe":
        normalized_engine = "quantum-espresso"
    raw = str(name).strip()
    compact = _canonical_change_name(raw)
    if raw.lower().startswith("execution.") or compact in {
        "partition",
        "queue",
        "qos",
        "account",
        "nodes",
        "ntasks",
        "ntaskspernode",
        "cpuspertask",
        "walltime",
        "module",
        "modules",
        "executable",
    }:
        return "L0"

    if normalized_engine == "vasp":
        if (
            compact.startswith("poscar")
            or compact.startswith("potcar")
            or compact in {
                "gga",
                "metagga",
                "lhfcalc",
                "ispin",
                "magmom",
                "lsorbit",
                "lnoncollinear",
                "nelect",
                "isym",
                "symprec",
                "ibrion",
                "nsw",
                "ediffg",
            }
        ):
            return "L3"
        if compact in {"nelm", "nelmin", "nelmdl", "nwrite", "lwave", "lcharg", "lelf", "lorbit", "ldipol", "idipol", "algo"}:
            return "L1"
        if compact in {
            "encut",
            "ismear",
            "sigma",
            "ediff",
            "kpoints",
            "kmesh",
            "kspacing",
            "nbands",
            "ncore",
            "kpar",
            "npar",
            "lhfcorrection",
        }:
            return "L2"
        return "UNKNOWN"

    if normalized_engine == "quantum-espresso":
        if (
            compact.startswith("pseudopotential")
            or compact in {
            "inputdft",
            "species",
            "positions",
            "cell",
            "spin",
            "soc",
            "nspin",
            "noncolin",
            "lspinorb",
            "charge",
            "totcharge",
            "constraints",
            "startingmagnetization",
            }
        ):
            return "L3"
        if compact in {"electronmaxstep", "mixingbeta", "mixingmode", "diagonalization"}:
            return "L1"
        if compact in {
            "ecutwfc",
            "ecutrho",
            "convthr",
            "occupations",
            "smearing",
            "degauss",
            "kpoints",
            "kmesh",
            "kpointsautomatic",
        }:
            return "L2"
        return "UNKNOWN"

    return "UNKNOWN"


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ReconciliationError(f"JSON record does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ReconciliationError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ReconciliationError(f"JSON record must be an object: {path}")
    return value


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _atomic_write_json(path: Path, value: Mapping[str, Any]) -> None:
    _atomic_write_text(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def _stage_file(path: Path, content: str) -> Path:
    """Write one desired file to a sibling temporary path without replacing its target."""

    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.stage.", suffix=".tmp", dir=str(path.parent)
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        return temporary
    except BaseException:
        if temporary.exists():
            temporary.unlink()
        raise


def _commit_staged_file(staged: Path, target: Path) -> None:
    os.replace(staged, target)


def _restore_file_bytes(path: Path, original: bytes | None) -> None:
    """Restore a target to its exact original bytes or original nonexistence."""

    if original is None:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        return

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.rollback.", suffix=".tmp", dir=str(path.parent)
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(original)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _commit_file_transaction(files: Mapping[Path, str]) -> None:
    """Stage and commit several files, restoring every original on any failure."""

    ordered = sorted(((Path(path), content) for path, content in files.items()), key=lambda item: str(item[0]))
    originals = {
        path: path.read_bytes() if path.exists() else None
        for path, _ in ordered
    }
    staged: dict[Path, Path] = {}
    try:
        for path, content in ordered:
            staged[path] = _stage_file(path, content)
        for path, _ in ordered:
            _commit_staged_file(staged[path], path)
    except BaseException:
        rollback_error: BaseException | None = None
        for path, original in originals.items():
            try:
                _restore_file_bytes(path, original)
            except BaseException as exc:
                if rollback_error is None:
                    rollback_error = exc
        if rollback_error is not None:
            raise ReconciliationError(
                f"reconciliation transaction failed and rollback failed: {rollback_error}"
            ) from rollback_error
        raise
    finally:
        for temporary in staged.values():
            if temporary.exists():
                temporary.unlink()


def _design_helper_module():
    scripts = Path(__file__).resolve().parents[2] / "dft-design" / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    try:
        import computation_design  # type: ignore
    except Exception as exc:  # pragma: no cover - defensive import boundary
        raise ReconciliationError(f"cannot load dft-design helpers: {exc}") from exc
    return computation_design


def _matrix_id(workflow: Mapping[str, Any], design: Mapping[str, Any]) -> str:
    workflow_design = workflow.get("design")
    if isinstance(workflow_design, Mapping) and isinstance(workflow_design.get("matrix_id"), str):
        return workflow_design["matrix_id"]
    envelopes = design.get("engine_stage_envelopes")
    engine = workflow.get("engine")
    candidates = [
        item.get("matrix_id")
        for item in (envelopes if isinstance(envelopes, list) else [])
        if isinstance(item, Mapping) and item.get("engine") == engine
    ]
    if len(candidates) == 1 and isinstance(candidates[0], str):
        return candidates[0]
    raise ReconciliationError("workflow does not identify one design matrix")


def _baseline_snapshot(workflow: Mapping[str, Any]) -> dict[str, Any]:
    snapshot = workflow.get("input_snapshot")
    if isinstance(snapshot, Mapping):
        return copy.deepcopy(dict(snapshot))
    workflow_design = workflow.get("design")
    parameters = (
        workflow_design.get("engine_parameters", {})
        if isinstance(workflow_design, Mapping)
        else {}
    )
    hashes: dict[str, Any] = {}
    inputs = workflow.get("inputs")
    records = inputs.get("files", []) if isinstance(inputs, Mapping) else []
    if isinstance(records, list):
        for item in records:
            if isinstance(item, Mapping) and isinstance(item.get("name"), str):
                if item.get("sha256") is not None:
                    hashes[item["name"]] = item["sha256"]
    return {"parameters": copy.deepcopy(parameters), "file_hashes": hashes, "file_semantics": {}}


def _authority_is_generated(workflow: Mapping[str, Any]) -> bool:
    authority = workflow.get("input_authority")
    if isinstance(authority, Mapping):
        for value in authority.values():
            if isinstance(value, Mapping) and value.get("authority") == "user_override":
                return False
            if value == "user_override":
                return False
    inputs = workflow.get("inputs")
    records = inputs.get("files", []) if isinstance(inputs, Mapping) else []
    if isinstance(records, list):
        for item in records:
            if isinstance(item, Mapping) and item.get("authority") == "user_override":
                return False
    return True


def _descendant_task_roots(task_root: Path, task_slug: str) -> list[Path]:
    from dft_contracts.layout import PROJECT_FILE, discover_workspace
    try:
        workspace = discover_workspace(task_root)
    except ValueError:
        workspace = None
    if workspace and (workspace / PROJECT_FILE).exists():
        from dft_contracts.lifecycle import rework_impact
        return [workspace / item["path"] for item in rework_impact(task_root)["affected"]
                if workspace / item["path"] != task_root.resolve()]
    structure_root = task_root.parent
    if not structure_root.is_dir():
        return []
    workflows: dict[str, tuple[Path, dict[str, Any]]] = {}
    for workflow_path in structure_root.rglob("workflow.json"):
        if workflow_path.parent.resolve() == task_root.resolve():
            continue
        try:
            workflow = _load_json(workflow_path)
        except ReconciliationError:
            continue
        slug = workflow.get("task_slug")
        if isinstance(slug, str):
            workflows[slug] = (workflow_path.parent, workflow)

    direct: dict[str, set[str]] = {slug: set() for slug in workflows}
    for slug, (_, workflow) in workflows.items():
        dependencies = workflow.get("dependencies", [])
        if isinstance(dependencies, list):
            for dependency in dependencies:
                if isinstance(dependency, Mapping):
                    dependency = dependency.get("task_ref")
                if isinstance(dependency, str):
                    direct.setdefault(dependency, set()).add(slug)
    descendants: set[str] = set()
    frontier = [task_slug]
    while frontier:
        current = frontier.pop()
        for child in sorted(direct.get(current, set())):
            if child not in descendants:
                descendants.add(child)
                frontier.append(child)
    return [workflows[slug][0] for slug in sorted(descendants) if slug in workflows]


def _update_input_records(
    workflow: dict[str, Any],
    current: Mapping[str, Any],
    baseline: Mapping[str, Any],
    adoption: str,
    detected_at: str,
) -> None:
    current_hashes = current.get("file_hashes", {})
    old_hashes = baseline.get("file_hashes", {})
    if not isinstance(current_hashes, Mapping):
        return
    inputs = workflow.setdefault("inputs", {})
    if not isinstance(inputs, dict):
        inputs = {"materialization": "static", "files": []}
        workflow["inputs"] = inputs
    records = inputs.setdefault("files", [])
    if not isinstance(records, list):
        records = []
        inputs["files"] = records
    by_name = {
        item.get("name"): item
        for item in records
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    }
    authorities = workflow.setdefault("input_authority", {})
    if not isinstance(authorities, dict):
        authorities = {}
        workflow["input_authority"] = authorities
    for raw_name, raw_hash in current_hashes.items():
        name = str(raw_name)
        old_hash = old_hashes.get(name)
        changed = old_hash != raw_hash
        record = by_name.get(name)
        if record is None:
            record = {
                "base": "task_root",
                "path": name,
                "name": name,
                "role": "engine_input",
                "mode": "static",
            }
            records.append(record)
            by_name[name] = record
        record["sha256"] = raw_hash
        if changed:
            record["authority"] = "user_override"
            authorities[name] = {
                "authority": "user_override",
                "previous_sha256": old_hash,
                "current_sha256": raw_hash,
                "detected_at": detected_at,
                "adoption": adoption,
            }


def _render_task_readme(
    task_root: Path, result: Mapping[str, Any], *, rerun_required: bool = False
) -> str:
    path = task_root / "README.md"
    text = path.read_text(encoding="utf-8") if path.exists() else f"# {task_root.name}\n"
    start = "<!-- dft-input-reconciliation:start -->"
    end = "<!-- dft-input-reconciliation:end -->"
    block = (
        f"{start}\n"
        f"- Status: `{result['status']}`\n"
        f"- Verdict: `{result['verdict']}`\n"
        f"- Changed parameters: `{json.dumps(result['changed_parameters'], ensure_ascii=False, sort_keys=True)}`\n"
        f"- Affected tasks: `{', '.join(result['affected_tasks']) or 'none'}`\n"
        f"- Rerun required: `{str(rerun_required).lower()}`\n"
        f"{end}"
    )
    old_start = text.find(start)
    old_end = text.find(end)
    if old_start >= 0 and old_end >= old_start:
        old_end += len(end)
        text = text[:old_start] + block + text[old_end:]
    else:
        text = text.rstrip() + "\n\n" + block + "\n"
    return text.rstrip() + "\n"


def _write_task_readme(
    task_root: Path, result: Mapping[str, Any], *, rerun_required: bool = False
) -> None:
    _atomic_write_text(
        task_root / "README.md",
        _render_task_readme(task_root, result, rerun_required=rerun_required),
    )


def _render_design_readme(path: Path, design: Mapping[str, Any]) -> str | None:
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    marker = re.compile(r"<!--\s*dft-design-sync:\s*(\{.*?\})\s*-->")
    match = marker.search(text)
    if match:
        try:
            value = json.loads(match.group(1))
        except json.JSONDecodeError:
            value = {}
        if not isinstance(value, dict):
            value = {}
        value["design_id"] = design.get("design_id")
        value["revision"] = design.get("revision")
        replacement = f"<!-- dft-design-sync: {json.dumps(value, ensure_ascii=False, separators=(',', ':'))} -->"
        text = text[: match.start()] + replacement + text[match.end() :]
    return text.rstrip() + "\n"


def _update_design_readme(path: Path, design: Mapping[str, Any]) -> None:
    rendered = _render_design_readme(path, design)
    if rendered is not None:
        _atomic_write_text(path, rendered)


def _render_design_history(
    path: Path,
    *,
    design: Mapping[str, Any],
    task_root: Path,
    changed_parameters: list[dict[str, Any]],
    detected_at: str,
) -> None:
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    event = {
        "history_schema_version": 1,
        "event_type": "user_parameter_override_adopted",
        "event_id": f"user_parameter_override:{detected_at}:{task_root.name}",
        "at": detected_at,
        "design_id": design.get("design_id"),
        "revision": design.get("revision"),
        "task_slug": task_root.name,
        "changed_parameters": copy.deepcopy(changed_parameters),
        "source": "current_on_disk_inputs",
    }
    prefix = "" if not existing or existing.endswith("\n") else "\n"
    return existing + prefix + json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n"


def _append_design_history(
    path: Path,
    *,
    design: Mapping[str, Any],
    task_root: Path,
    changed_parameters: list[dict[str, Any]],
    detected_at: str,
) -> None:
    _atomic_write_text(
        path,
        _render_design_history(
            path,
            design=design,
            task_root=task_root,
            changed_parameters=changed_parameters,
            detected_at=detected_at,
        ),
    )


def _load_design_and_workflow(task_root: Path, design_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    workflow_path = task_root / "workflow.json"
    if not workflow_path.is_file():
        raise ReconciliationError(f"workflow.json does not exist: {workflow_path}")
    workflow = _load_json(workflow_path)
    design = _load_json(design_path)
    if workflow.get("contract") not in {"dft.workflow.v2", None} and workflow.get("schema_version") != 2:
        raise ReconciliationError("reconciliation requires a workflow-v2 task leaf")
    return workflow, design


def _parameter_updates(changes: list[dict[str, Any]]) -> dict[str, Any]:
    updates: dict[str, Any] = {}
    for change in changes:
        if change["impact"] in {"L0", "L1", "L2"} and change["name"] not in {"POSCAR", "POTCAR"}:
            updates[change["name"]] = change["new"]
    return updates


def _recipe_input_names(workflow: Mapping[str, Any]) -> set[str]:
    inputs = workflow.get("inputs")
    records = inputs.get("files", []) if isinstance(inputs, Mapping) else []
    return {
        str(item.get("name"))
        for item in records
        if isinstance(item, Mapping)
        and item.get("mode") == "recipe"
        and isinstance(item.get("name"), str)
    }


def snapshot_primary_input(task_root: Path, workflow: Mapping[str, Any]) -> str | None:
    """A declared future QE recipe need not exist while its upstream is pending."""
    primary = workflow.get("primary_input")
    if not isinstance(primary, str):
        return None
    if primary in _recipe_input_names(workflow) and _find_input(task_root, Path(primary).name) is None:
        return None
    return primary


def reconcile_task(task_root: Path, design_path: Path, *, write: bool) -> dict[str, Any]:
    """Reconcile a task and optionally persist only planning-record changes."""

    root = Path(task_root).expanduser().resolve()
    plan = Path(design_path).expanduser().resolve()
    workflow, design = _load_design_and_workflow(root, plan)
    engine = workflow.get("engine")
    if not isinstance(engine, str):
        raise ReconciliationError("workflow engine is missing")
    primary_input = snapshot_primary_input(root, workflow)
    baseline = _baseline_snapshot(workflow)
    current = parse_current_inputs(
        engine, root, primary_input=primary_input, previous_snapshot=baseline
    )
    differences = semantic_diff(baseline, current)
    recipe_names = _recipe_input_names(workflow)
    differences = [
        item
        for item in differences
        if not (
            item["name"] in recipe_names
            and item["old"] is None
            and item["name"] not in _snapshot_semantics(baseline)
        )
    ]
    changes = [
        {
            "name": item["name"],
            "old": item["old"],
            "new": item["new"],
            "impact": classify_change(engine, item["name"], item["old"], item["new"]),
        }
        for item in differences
    ]
    impacts = {item["impact"] for item in changes}
    state = str(workflow.get("status", "prepared"))
    detected_at = _utc_now()
    affected_tasks: list[str] = []
    rerun_required = False
    if not changes:
        status = "synchronized"
        verdict = "ADVANCE"
    elif "L3" in impacts:
        status = "major_conflict"
        verdict = "MAJOR_CONFLICT"
    elif "UNKNOWN" in impacts:
        status = "needs_agent"
        verdict = "NEEDS_AGENT"
    else:
        verdict = "ADVANCE"
        status = "adopted"

    if changes and state in {"submitted", "running"}:
        status = "pending_override"
    elif changes and state == "completed":
        rerun_required = True
        if "L3" not in impacts and "UNKNOWN" not in impacts:
            status = "pending_override"
    elif status == "adopted" and all(item["impact"] in {"L0", "L1", "L2"} for item in changes):
        affected_tasks = [
            path.name
            for path in _descendant_task_roots(root, str(workflow.get("task_slug", root.name)))
        ]
        if affected_tasks and any(item["impact"] == "L2" for item in changes):
            status = "propagated"
    elif status == "major_conflict":
        affected_tasks = [
            path.name
            for path in _descendant_task_roots(root, str(workflow.get("task_slug", root.name)))
        ]

    result: dict[str, Any] = {
        "status": status,
        "verdict": verdict,
        "changed_parameters": changes,
        "affected_tasks": affected_tasks,
        "current_parameter_hash": current["parameter_hash"],
        "rerun_required": rerun_required,
    }
    if current.get("parse_errors"):
        result["parse_errors"] = list(current["parse_errors"])

    if not write:
        return result

    workflow_path = root / "workflow.json"
    workflow_updated = copy.deepcopy(workflow)
    old_baseline = copy.deepcopy(baseline)
    design_updated = copy.deepcopy(design)
    _update_input_records(workflow_updated, current, baseline, status, detected_at)
    reconciliation = workflow_updated.setdefault("parameter_reconciliation", {})
    if not isinstance(reconciliation, dict):
        reconciliation = {}
        workflow_updated["parameter_reconciliation"] = reconciliation
    reconciliation.update(
        {
            "status": status,
            "changed_parameters": copy.deepcopy(changes),
            "affected_tasks": list(affected_tasks),
            "detected_at": detected_at,
            "current_parameter_hash": current["parameter_hash"],
        }
    )

    if not changes:
        workflow_updated["input_snapshot"] = copy.deepcopy(current)
    elif state in {"submitted", "running"}:
        workflow_updated["pending_input_snapshot"] = copy.deepcopy(current)
    elif state == "completed":
        workflow_updated["pending_input_snapshot"] = copy.deepcopy(current)
    elif verdict == "ADVANCE" and "UNKNOWN" not in impacts and "L3" not in impacts:
        updates = _parameter_updates(changes)
        workflow_design = workflow_updated.setdefault("design", {})
        if isinstance(workflow_design, dict):
            parameters = workflow_design.setdefault("engine_parameters", {})
            if isinstance(parameters, dict):
                for key, value in updates.items():
                    if value is None:
                        parameters.pop(key, None)
                    else:
                        parameters[key] = copy.deepcopy(value)
            workflow_design["baseline_parameter_hash"] = current["parameter_hash"]
        workflow_updated["input_snapshot"] = copy.deepcopy(current)
    if status == "major_conflict" and state not in {"submitted", "running", "completed"}:
        workflow_updated["status"] = "awaiting_user_decision"
        workflow_updated.setdefault("submission", {})["allowed"] = False
    elif state == "completed":
        workflow_updated["status"] = "completed"
    if state in {"submitted", "running"}:
        workflow_updated["status"] = state

    if changes or current.get("file_hashes") != old_baseline.get("file_hashes"):
        workflow_updated["updated_at"] = detected_at
    workflow_updated.setdefault("history", []).append(
        {
            "at": detected_at,
            "status": status,
            "note": "reconciled current on-disk inputs without rewriting engine files",
        }
    )

    design_changed = (
        bool(changes)
        and verdict == "ADVANCE"
        and state not in {"submitted", "running", "completed"}
        and "UNKNOWN" not in impacts
        and "L3" not in impacts
    )
    files_to_commit: dict[Path, str] = {}
    if design_changed:
        updates = _parameter_updates(changes)
        if updates:
            helper = _design_helper_module()
            design_updated = helper.apply_engine_parameter_overrides(
                design_updated, _matrix_id(workflow, design), updates
            )
            history_path = plan.parent / "history.jsonl"
            files_to_commit[history_path] = _render_design_history(
                history_path,
                design=design_updated,
                task_root=root,
                changed_parameters=changes,
                detected_at=detected_at,
            )
            from dft_contracts.layout import plan_readme_path
            design_readme_path = plan_readme_path(plan)
            design_readme = _render_design_readme(design_readme_path, design_updated)
            if design_readme is not None:
                files_to_commit[design_readme_path] = design_readme

    workflow_design = workflow_updated.get("design")
    if (
        design_changed
        and isinstance(workflow_design, dict)
        and isinstance(design_updated.get("revision"), int)
    ):
        workflow_design["revision"] = design_updated["revision"]

    # A major conflict is recorded on the affected branch but the current
    # input and the immutable approval history remain untouched.  All planning
    # records are rendered before any target is replaced so one transaction
    # can restore every original byte if a later commit fails.
    files_to_commit[workflow_path] = json.dumps(workflow_updated, ensure_ascii=False, indent=2) + "\n"
    if design_changed:
        files_to_commit[plan] = json.dumps(design_updated, ensure_ascii=False, indent=2) + "\n"
    from dft_contracts.layout import stage_root
    try:
        readme_root = stage_root(root) or root
    except ValueError:
        readme_root = root
    files_to_commit[readme_root / "README.md"] = _render_task_readme(
        readme_root, result, rerun_required=rerun_required
    )

    if status in {"propagated", "major_conflict"}:
        for descendant_root in _descendant_task_roots(root, str(workflow.get("task_slug", root.name))):
            descendant_path = descendant_root / "workflow.json"
            try:
                descendant = _load_json(descendant_path)
            except ReconciliationError:
                continue
            descendant_state = str(descendant.get("status", "planned"))
            submission = descendant.get("submission")
            submitted = isinstance(submission, Mapping) and submission.get("state") not in {
                None,
                "not_submitted",
                "not_requested",
            }
            if (
                descendant_state not in {"submitted", "running", "completed", "superseded"}
                and not submitted
                and _authority_is_generated(descendant)
            ):
                descendant_reconciliation = descendant.setdefault("parameter_reconciliation", {})
                if isinstance(descendant_reconciliation, dict):
                    descendant_reconciliation.update(
                        {
                            "status": "propagated" if status == "propagated" else "major_conflict",
                            "changed_parameters": copy.deepcopy(changes),
                            "affected_tasks": [descendant_root.name],
                            "stale_reason": (
                                "stale_due_to_upstream_parameter_change"
                                if status == "propagated"
                                else "awaiting_user_decision_due_to_upstream_major_conflict"
                            ),
                            "detected_at": detected_at,
                        }
                    )
                if status == "propagated":
                    descendant["stale_due_to_upstream_parameter_change"] = True
                else:
                    descendant["status"] = "awaiting_user_decision"
                descendant.setdefault("history", []).append(
                    {
                        "at": detected_at,
                        "status": "propagated" if status == "propagated" else "awaiting_user_decision",
                        "note": (
                            "stale_due_to_upstream_parameter_change"
                            if status == "propagated"
                            else "awaiting_user_decision_due_to_upstream_major_conflict"
                        ),
                    }
                )
                files_to_commit[descendant_path] = (
                    json.dumps(descendant, ensure_ascii=False, indent=2) + "\n"
                )

    _commit_file_transaction(files_to_commit)

    return result
