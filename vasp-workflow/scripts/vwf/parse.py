"""Result parsing for finished VASP calculations.

Self-contained (no third-party deps) so the skill can judge a run by its
*scientific outcome* — did it converge, what is the energy/force, did it crash —
instead of by exit code alone. Scalar results are metadata, so callers serialize
them as JSON (e.g. ``parse_result.json``); numeric plot arrays stay in ``.dat``
files and belong to the vasp-analysis skill, not here.

``parse_outcar`` streams the file line by line so multi-GB OUTCARs never load
into memory. Error scanning only reads the trailing slice of each log because
crash messages land at the end of a run.
"""
from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any


FLOAT = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][-+]?\d+)?"

# Crash messages sit at the end of a run, so only scan each log's tail.
MAX_LOG_BYTES = 4 * 1024 * 1024

# Genuine crash / scheduler failures only. "not reached required accuracy" is
# deliberately NOT here: non-convergence is reported through the
# converged_electronic / converged_ionic verdict, not as a hard error, so the
# status stays NOT_CONVERGED (recoverable) rather than ERROR.
ERROR_PATTERNS: list[tuple[str, "re.Pattern[str]", str]] = [
    (
        "ZHEGV_FAILED",
        re.compile(r"ZHEGV\s+failed|Call to ZHEGV failed", re.IGNORECASE),
        "Diagonalization failed. Check ALGO, ENCUT, electronic convergence, and structure quality.",
    ),
    (
        "ZBRENT_FAILED",
        re.compile(r"ZBRENT.*fatal error|fatal error in bracketing", re.IGNORECASE | re.DOTALL),
        "Ionic line search failed. Check forces, EDIFFG, POTCAR consistency, and starting geometry.",
    ),
    (
        "CHGCAR_READ_FAILED",
        re.compile(r"charge density could not be read|could not.*read.*CHGCAR", re.IGNORECASE | re.DOTALL),
        "CHGCAR was requested but is missing or incompatible. Check ICHARG and charge-density reuse.",
    ),
    (
        "LAPACK_ERROR",
        re.compile(r"(?<![a-z])LAPACK", re.IGNORECASE),
        "A LAPACK-level numerical failure occurred. Check parallel layout, structure, and electronic settings.",
    ),
    (
        "COMMAND_NOT_FOUND",
        re.compile(r"command not found|No such file or directory", re.IGNORECASE),
        "The VASP command or environment module was not available in the job shell.",
    ),
    (
        "TIME_LIMIT",
        re.compile(r"TIME LIMIT|TIMEOUT|DUE TO TIME LIMIT", re.IGNORECASE),
        "The scheduler killed the job because it reached the wall-time limit.",
    ),
    (
        "OUT_OF_MEMORY",
        re.compile(r"OUT_OF_MEMORY|oom-kill|Killed", re.IGNORECASE),
        "The job likely exceeded memory limits. Reduce size or request more memory.",
    ),
]


def parse_task_directory(task_dir: Path) -> dict[str, Any]:
    """Parse a finished (or in-progress) VASP task directory into a result dict.

    Always returns a dict with at least ``task_dir``, ``finished`` and
    ``status``; numeric fields appear only when found in the outputs.
    """
    task_dir = Path(task_dir).expanduser().resolve()
    result: dict[str, Any] = {
        "task_dir": str(task_dir),
        "files_seen": sorted(p.name for p in task_dir.iterdir() if p.is_file())
        if task_dir.exists()
        else [],
        "finished": False,
    }

    if not task_dir.exists():
        result.update(
            error_type="TASK_DIR_MISSING",
            error_message=f"Task directory does not exist: {task_dir}",
            status="ERROR",
        )
        return result

    nions = parse_poscar_nions(task_dir / "POSCAR")
    if nions is not None:
        result["nions"] = nions

    oszicar = task_dir / "OSZICAR"
    if oszicar.exists():
        result.update({k: v for k, v in parse_oszicar(oszicar).items() if v is not None})

    outcar = task_dir / "OUTCAR"
    if outcar.exists():
        free_mask = parse_free_mask(task_dir / "CONTCAR") or parse_free_mask(task_dir / "POSCAR")
        result.update({k: v for k, v in parse_outcar(outcar, free_mask=free_mask).items() if v is not None})

    error = classify_error_records(collect_log_records(task_dir))
    if error:
        result["error_type"] = error["type"]
        result["error_message"] = error["message"]
        result["error_source"] = error.get("source")
        result["error_excerpt"] = error.get("excerpt")

    nions = result.get("nions")
    if result.get("final_energy") is not None and nions:
        result["energy_per_atom"] = result["final_energy"] / nions
    if result.get("e0_energy") is not None and nions:
        result["e0_energy_per_atom"] = result["e0_energy"] / nions

    converged = _overall_converged(result)
    if converged is not None:
        result["converged"] = converged
    result["status"] = _infer_status(result)
    return result


# Backwards/intuitive alias.
parse_task_dir = parse_task_directory


_OSZ_F_RE = re.compile(r"\bF=\s*(%s)" % FLOAT)
_OSZ_E0_RE = re.compile(r"\bE0=\s*(%s)" % FLOAT)


def parse_oszicar(path: Path) -> dict[str, Any]:
    """Extract final F (free energy) and E0 (sigma->0) plus step counts.

    ``final_energy`` keeps F so it matches the OUTCAR "free energy TOTEN";
    ``e0_energy`` carries the sigma->0 extrapolated value.
    """
    text = read_text(path)
    ionic_lines = [line for line in text.splitlines() if re.match(r"\s*\d+\s+F=", line)]
    final_energy = e0_energy = None
    for line in ionic_lines:
        if (m := _OSZ_F_RE.search(line)):
            final_energy = float(m.group(1))
        if (m := _OSZ_E0_RE.search(line)):
            e0_energy = float(m.group(1))

    electronic_steps = None
    if text.strip():
        electronic_steps = len(
            [line for line in text.splitlines() if re.match(r"\s*(?:DAV|RMM|CG|BROYDEN|N)\s*:", line)]
        )

    return {
        "final_energy": final_energy,
        "e0_energy": e0_energy,
        "ionic_steps": len(ionic_lines) or None,
        "electronic_steps": electronic_steps,
    }


_NIONS_RE = re.compile(r"NIONS\s*=\s*(\d+)")
_NBANDS_RE = re.compile(r"NBANDS\s*=\s*(\d+)")
_NSW_RE = re.compile(r"NSW\s*=\s*(\d+)")
_IBRION_RE = re.compile(r"IBRION\s*=\s*(-?\d+)")
_FERMI_RE = re.compile(r"E-fermi\s*:\s*(%s)" % FLOAT)
_RUNTIME_RE = re.compile(r"Elapsed time \(sec\):\s*(%s)" % FLOAT)
_MAG_RE = re.compile(r"number of electron\s+%s\s+magnetization\s+(%s)" % (FLOAT, FLOAT))
_TOTEN_RE = re.compile(r"free\s+energy\s+TOTEN\s*=\s*(%s)" % FLOAT)
_SIGMA0_RE = re.compile(r"energy\(sigma->0\)\s*=\s*(%s)" % FLOAT)
_DASHES_RE = re.compile(r"-{5,}")


def parse_outcar(path: Path, free_mask: list[bool] | None = None) -> dict[str, Any]:
    """Stream OUTCAR for energy, max force, convergence verdict, and metadata.

    Single-line metrics keep their last occurrence. ``max_force`` comes from the
    last completed TOTAL-FORCE block; ``free_mask`` drops fully fixed atoms so
    selective-dynamics relaxations don't report held-layer forces.
    """
    nions = nbands = nsw = ibrion = fermi = runtime = total_mag = None
    final_energy = e0_energy = max_force = None
    finished = False
    has_not_reached = has_reached = has_ediff_reached = False

    collecting = skip_dashes = False
    force_atom_idx = 0
    current_forces: list[float] = []

    for line in iter_lines(path):
        lowered = line.lower()
        if "voluntary context switches" in lowered:
            finished = True
        if "reached required accuracy" in lowered:
            has_reached = True
            if "not reached required accuracy" in lowered:
                has_not_reached = True
        if "aborting loop because ediff is reached" in lowered:
            has_ediff_reached = True

        if "TOTAL-FORCE (eV/Angst)" in line:
            collecting = True
            skip_dashes = True
            force_atom_idx = 0
            current_forces = []
            continue
        if collecting:
            if _DASHES_RE.match(line.strip()):
                if skip_dashes:
                    skip_dashes = False
                    continue
                if current_forces:
                    max_force = max(current_forces)
                collecting = False
                continue
            values = re.findall(FLOAT, line)
            if len(values) >= 6:
                fx, fy, fz = map(float, values[-3:])
                magnitude = math.sqrt(fx * fx + fy * fy + fz * fz)
                if free_mask is None or (force_atom_idx < len(free_mask) and free_mask[force_atom_idx]):
                    current_forces.append(magnitude)
                force_atom_idx += 1
            continue

        if (m := _TOTEN_RE.search(line)):
            final_energy = float(m.group(1))
        elif (m := _SIGMA0_RE.search(line)):
            e0_energy = float(m.group(1))
        elif (m := _FERMI_RE.search(line)):
            fermi = float(m.group(1))
        elif (m := _MAG_RE.search(line)):
            total_mag = float(m.group(1))
        elif (m := _RUNTIME_RE.search(line)):
            runtime = float(m.group(1))
        elif (m := _NIONS_RE.search(line)):
            nions = int(m.group(1))
        elif (m := _NBANDS_RE.search(line)):
            nbands = int(m.group(1))
        elif (m := _NSW_RE.search(line)):
            nsw = int(m.group(1))
        elif (m := _IBRION_RE.search(line)):
            ibrion = int(m.group(1))

    if collecting and current_forces:
        max_force = max(current_forces)

    result: dict[str, Any] = {
        "nions": nions,
        "nbands": nbands,
        "nsw": nsw,
        "ibrion": ibrion,
        "fermi_energy": fermi,
        "runtime_seconds": runtime,
        "total_magnetization": total_mag,
        "final_energy": final_energy,
        "e0_energy": e0_energy,
        "max_force": max_force,
        "finished": finished,
    }
    if has_not_reached:
        result["converged_ionic"] = False
    elif has_reached:
        result["converged_ionic"] = True
    if has_ediff_reached:
        result["converged_electronic"] = True
    elif has_not_reached:
        result["converged_electronic"] = False
    return result


def _overall_converged(result: dict[str, Any]) -> bool | None:
    """Best-effort single convergence verdict.

    Static runs (NSW==0 or IBRION==-1) hinge on electronic convergence; relaxes
    require ionic convergence (and must not have a failed final SCF). Returns
    None when the outputs don't say enough to decide.
    """
    ce = result.get("converged_electronic")
    ci = result.get("converged_ionic")
    is_static = (result.get("nsw") == 0) or (result.get("ibrion") == -1)
    if is_static:
        return ce
    if ci is None:
        return None
    if ci is False:
        return False
    return False if ce is False else True


def _has_usable_result(result: dict[str, Any]) -> bool:
    if result.get("final_energy") is None:
        return False
    return (
        result.get("converged") is True
        or result.get("converged_electronic") is True
        or result.get("max_force") is not None
    )


def _infer_status(result: dict[str, Any]) -> str:
    if result.get("error_type"):
        return "FINISHED_WITH_WARNING" if _has_usable_result(result) else "ERROR"
    converged = result.get("converged")
    if converged is True:
        return "CONVERGED"
    if converged is False:
        return "NOT_CONVERGED"
    if result.get("finished") and result.get("final_energy") is not None:
        return "FINISHED_UNKNOWN"
    if result.get("final_energy") is not None or result.get("ionic_steps"):
        return "INCOMPLETE"
    return "UNKNOWN"


def parse_free_mask(path: Path) -> list[bool] | None:
    """Per-atom free flags from POSCAR/CONTCAR selective dynamics.

    True if an atom has any unconstrained direction, False if fully fixed; None
    when there is no selective dynamics block.
    """
    if not path.exists():
        return None
    raw = read_text(path).splitlines()
    if len(raw) < 9:
        return None
    try:
        counts = [int(x) for x in raw[6].split()]
    except (ValueError, IndexError):
        return None
    natoms = sum(counts)
    if not raw[7].strip()[:1].lower() == "s":
        return None
    atom_start = 9
    mask: list[bool] = []
    for i in range(natoms):
        if atom_start + i >= len(raw):
            break
        flags = raw[atom_start + i].split()[3:6]
        mask.append(any(f.upper() == "T" for f in flags) if flags else True)
    return mask if len(mask) == natoms else None


def parse_poscar_nions(path: Path) -> int | None:
    if not path.exists():
        return None
    lines = [line.split() for line in read_text(path).splitlines() if line.strip()]
    if len(lines) < 7:
        return None
    for row in (lines[5], lines[6]):
        try:
            counts = [int(value) for value in row]
        except ValueError:
            continue
        if counts:
            return sum(counts)
    return None


def collect_log_records(task_dir: Path) -> list[dict[str, str]]:
    names = ["OUTCAR", "vasp.out", "vasp.err"]
    records = [
        {"source": name, "text": read_tail(task_dir / name)}
        for name in names
        if (task_dir / name).exists()
    ]
    for path in sorted(task_dir.glob("slurm-*.out")) + sorted(task_dir.glob("slurm-*.err")):
        records.append({"source": path.name, "text": read_tail(path)})
    return records


def classify_error_records(records: list[dict[str, str]]) -> dict[str, str] | None:
    for error_type, pattern, message in ERROR_PATTERNS:
        for record in records:
            match = pattern.search(record["text"])
            if match:
                return {
                    "type": error_type,
                    "message": message,
                    "source": record["source"],
                    "excerpt": compact_excerpt(record["text"], match.start(), match.end()),
                }
    return None


def compact_excerpt(text: str, start: int, end: int, radius: int = 90) -> str:
    left = max(0, start - radius)
    right = min(len(text), end + radius)
    excerpt = re.sub(r"\s+", " ", text[left:right].replace("\r", " ").replace("\n", " ")).strip()
    if left > 0:
        excerpt = "..." + excerpt
    if right < len(text):
        excerpt = excerpt + "..."
    return excerpt


def format_summary(result: dict[str, Any]) -> list[str]:
    """Human-readable lines for `vwf parse` (no JSON)."""
    lines = [f"status: {result.get('status', 'UNKNOWN')}", f"task_dir: {result.get('task_dir', '')}"]
    ce, ci = result.get("converged_electronic"), result.get("converged_ionic")
    lines.append(
        f"converged: overall={result.get('converged')} electronic={ce} ionic={ci} finished={result.get('finished')}"
    )
    if result.get("final_energy") is not None:
        per = result.get("e0_energy_per_atom")
        per_str = f", E0/atom={per:.6f}" if per is not None else ""
        lines.append(
            f"energy: F={result['final_energy']:.6f} eV, E0={result.get('e0_energy')} eV{per_str}"
        )
    if result.get("max_force") is not None:
        lines.append(f"max_force: {result['max_force']:.4f} eV/Ang")
    meta = [f"{k}={result[k]}" for k in ("nions", "ionic_steps", "fermi_energy", "total_magnetization") if result.get(k) is not None]
    if meta:
        lines.append("meta: " + "  ".join(meta))
    if result.get("error_type"):
        lines.append(f"error: {result['error_type']} ({result.get('error_source')}) — {result.get('error_message')}")
        if result.get("error_excerpt"):
            lines.append(f"  excerpt: {result['error_excerpt']}")
    return lines


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def iter_lines(path: Path):
    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        yield from handle


def read_tail(path: Path, max_bytes: int = MAX_LOG_BYTES) -> str:
    size = path.stat().st_size
    if size <= max_bytes:
        return path.read_text(encoding="utf-8", errors="ignore")
    with path.open("rb") as handle:
        handle.seek(size - max_bytes)
        return handle.read().decode("utf-8", errors="ignore")
