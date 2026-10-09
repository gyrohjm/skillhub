from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .base import max_norm, result_skeleton, source_record, validate_result
from .electronic_structure import qe_bands_gnu, qe_dos


RY_TO_EV = 13.605693122994
RY_BOHR_TO_EV_A = 25.711033531
FLOAT = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[EeDd][-+]?\d+)?"
VERSION_RE = re.compile(r"Program PWSCF v\.([^\s]+)", re.IGNORECASE)
NAT_RE = re.compile(r"number of atoms/cell\s*=\s*(\d+)", re.IGNORECASE)
ENERGY_RE = re.compile(r"!\s+total energy\s*=\s*(%s)\s+Ry" % FLOAT, re.IGNORECASE)
FERMI_RE = re.compile(r"the Fermi energy is\s+(%s)\s+ev" % FLOAT, re.IGNORECASE)
FORCE_RE = re.compile(r"atom\s+\d+\s+type\s+\d+\s+force\s*=\s*(%s)\s+(%s)\s+(%s)" % (FLOAT, FLOAT, FLOAT), re.IGNORECASE)
MAG_RE = re.compile(r"total magnetization\s*=\s*(%s)\s+Bohr mag/cell" % FLOAT, re.IGNORECASE)


def number(value: str) -> float:
    return float(value.replace("D", "E").replace("d", "e"))


def output_candidates(root: Path) -> list[Path]:
    preferred = [root / name for name in ("pw.out", "scf.out", "relax.out", "nscf.out", "bands.out")]
    found = [path for path in preferred if path.is_file()]
    if found:
        return found
    return sorted(path for path in root.glob("*.out") if path.is_file())


def parse_quantum_espresso(task_dir: str | Path) -> dict[str, Any]:
    root = Path(task_dir).expanduser().resolve()
    outputs = output_candidates(root)
    if not outputs:
        raise FileNotFoundError(f"Quantum ESPRESSO output not found under {root}")
    output = outputs[-1]
    lines = output.read_text(encoding="utf-8", errors="replace").splitlines()
    text = "\n".join(lines)
    result = result_skeleton("quantum-espresso", root, "dft-analysis.adapters.quantum_espresso")
    result["source_files"] = [source_record(path, root) for path in outputs]
    for suffix in ("*.in", "*.xml", "*.upf", "*.UPF"):
        for path in sorted(root.glob(suffix)):
            result["source_files"].append(source_record(path, root))

    version_match = VERSION_RE.search(text)
    nat_match = NAT_RE.search(text)
    nions = int(nat_match.group(1)) if nat_match else None
    energies = [number(value) for value in ENERGY_RE.findall(text)]
    fermi_values = [number(value) for value in FERMI_RE.findall(text)]
    force_vectors = [[number(value) * RY_BOHR_TO_EV_A for value in match] for match in FORCE_RE.findall(text)]
    if nions and len(force_vectors) >= nions:
        force_vectors = force_vectors[-nions:]
    magnetizations = [number(value) for value in MAG_RE.findall(text)]
    normal = "JOB DONE" in text
    electronic: bool | None = None
    if "convergence has been achieved" in text:
        electronic = True
    if "convergence NOT achieved" in text or "convergence not achieved" in text:
        electronic = False

    stress_tensor: list[list[float]] | None = None
    for index, line in enumerate(lines):
        if "total   stress" not in line.lower() or index + 3 >= len(lines):
            continue
        rows: list[list[float]] = []
        for candidate in lines[index + 1 : index + 4]:
            values = [number(value) for value in re.findall(FLOAT, candidate)]
            if len(values) >= 6:
                rows.append([value * 0.1 for value in values[-3:]])
        if len(rows) == 3:
            stress_tensor = rows

    fatal_patterns = ("Error in routine", "%%%%%%%%%%%%%%", "stopping ...", "Maximum CPU time exceeded")
    warnings = [pattern for pattern in fatal_patterns if pattern in text]
    total_eV = energies[-1] * RY_TO_EV if energies else None
    result.update(
        engine_version=version_match.group(1) if version_match else None,
        termination={"normal": normal and not warnings, "status": "completed" if normal and not warnings else "incomplete"},
        convergence={"electronic": electronic, "ionic": None},
        energy={
            "total_eV": total_eV,
            "per_atom_eV": total_eV / nions if total_eV is not None and nions else None,
            "fermi_eV": fermi_values[-1] if fermi_values else None,
            "source_unit": "Ry",
            "normalization": "cell",
        } if energies else None,
        forces={
            "unit": "eV/Angstrom",
            "vectors": force_vectors,
            "max_norm_eV_per_A": max_norm(force_vectors),
            "source_unit": "Ry/bohr",
        } if force_vectors else None,
        stress={"unit": "GPa", "tensor_GPa": stress_tensor, "source_unit": "kbar"} if stress_tensor else None,
        magnetization={"total_muB": magnetizations[-1]} if magnetizations else None,
        warnings=warnings,
        confidence="high" if normal and energies and electronic is True else ("medium" if energies else "low"),
    )
    band_paths = sorted(root.glob("*.bands.dat.gnu")) + sorted(root.glob("bands.dat.gnu"))
    dos_paths = sorted(root.glob("*.dos")) + sorted(root.glob("dos.dat"))
    bands = qe_bands_gnu(band_paths[0]) if band_paths else None
    dos = qe_dos(dos_paths[0]) if dos_paths else None
    if bands or dos:
        result["electronic_structure"] = {
            "fermi_eV": fermi_values[-1] if fermi_values else None,
            "band_gap_eV": None,
            "bands": bands,
            "dos": dos,
        }
        result["warnings"].append(
            "QE band gap is not inferred from plot-only files without occupations"
        )
        for path in [*(band_paths[:1]), *(dos_paths[:1])]:
            result["source_files"].append(source_record(path, root))
    if electronic is None:
        result["warnings"].append("electronic convergence could not be established from QE output")
    validate_result(result)
    return result
