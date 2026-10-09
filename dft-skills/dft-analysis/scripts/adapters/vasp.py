from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

from .base import max_norm, parse_poscar, result_skeleton, source_record, source_records, validate_result
from .electronic_structure import vasp_doscar, vasp_eigenval


FLOAT = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[EeDd][-+]?\d+)?"
VERSION_RE = re.compile(r"\bvasp\.([^\s]+)", re.IGNORECASE)
NIONS_RE = re.compile(r"NIONS\s*=\s*(\d+)")
NSW_RE = re.compile(r"NSW\s*=\s*(\d+)")
IBRION_RE = re.compile(r"IBRION\s*=\s*(-?\d+)")
TOTEN_RE = re.compile(r"free\s+energy\s+TOTEN\s*=\s*(%s)" % FLOAT, re.IGNORECASE)
SIGMA_RE = re.compile(r"energy\(sigma->0\)\s*=\s*(%s)" % FLOAT, re.IGNORECASE)
FERMI_RE = re.compile(r"E-fermi\s*:\s*(%s)" % FLOAT)
MAG_RE = re.compile(r"number of electron\s+%s\s+magnetization\s*(%s)?" % (FLOAT, FLOAT), re.IGNORECASE)
STRESS_RE = re.compile(r"^\s*in kB\s+(.+)$")
FORCE_HEADER_RE = re.compile(r"TOTAL-FORCE \(eV/Angst\)")


def number(value: str) -> float:
    return float(value.replace("D", "E").replace("d", "e"))


def parse_vasp(task_dir: str | Path) -> dict[str, Any]:
    root = Path(task_dir).expanduser().resolve()
    outcar = root / "OUTCAR"
    if not outcar.is_file():
        raise FileNotFoundError(f"VASP OUTCAR not found: {outcar}")

    result = result_skeleton("vasp", root, "dft-analysis.adapters.vasp")
    result["source_files"] = source_records(root, ("OUTCAR", "OSZICAR", "CONTCAR", "POSCAR", "vasprun.xml"))
    version = None
    nions = nsw = ibrion = None
    total_energy = sigma_energy = fermi = magnetization = None
    stress_kbar: list[float] | None = None
    force_blocks: list[list[list[float]]] = []
    current_forces: list[list[float]] | None = None
    skip_separator = False
    normal = electronic = ionic = False
    warnings: list[str] = []

    for raw_line in outcar.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.rstrip()
        lower = line.lower()
        if version is None and (match := VERSION_RE.search(line)):
            version = match.group(1)
        if "voluntary context switches" in lower:
            normal = True
        if "aborting loop because ediff is reached" in lower:
            electronic = True
        if "reached required accuracy" in lower and "not reached" not in lower:
            ionic = True
        if "not reached required accuracy" in lower:
            electronic = False
            ionic = False
        if any(token in line for token in ("VERY BAD NEWS", "ZBRENT", "BRMIX", "ZHEGV")):
            warnings.append(line.strip())

        if FORCE_HEADER_RE.search(line):
            current_forces = []
            skip_separator = True
            continue
        if current_forces is not None:
            if re.match(r"\s*-{5,}\s*$", line):
                if skip_separator:
                    skip_separator = False
                    continue
                if current_forces:
                    force_blocks.append(current_forces)
                current_forces = None
                continue
            values = re.findall(FLOAT, line)
            if len(values) >= 6:
                current_forces.append([number(value) for value in values[-3:]])
            continue

        if (match := TOTEN_RE.search(line)):
            total_energy = number(match.group(1))
        if (match := SIGMA_RE.search(line)):
            sigma_energy = number(match.group(1))
        if (match := FERMI_RE.search(line)):
            fermi = number(match.group(1))
        if (match := NIONS_RE.search(line)):
            nions = int(match.group(1))
        if (match := NSW_RE.search(line)):
            nsw = int(match.group(1))
        if (match := IBRION_RE.search(line)):
            ibrion = int(match.group(1))
        if (match := MAG_RE.search(line)) and match.group(1):
            magnetization = number(match.group(1))
        if (match := STRESS_RE.match(line)):
            values = [number(value) for value in re.findall(FLOAT, match.group(1))]
            if len(values) >= 6:
                stress_kbar = values[:6]

    is_static = nsw == 0 or ibrion == -1
    electronic_value: bool | None = electronic if (electronic or normal) else None
    ionic_value: bool | None = None if is_static else (True if ionic else None)
    result.update(
        engine_version=version,
        termination={"normal": normal, "status": "completed" if normal else "incomplete"},
        convergence={"electronic": electronic_value, "ionic": ionic_value},
        energy={
            "total_eV": total_energy,
            "sigma_to_zero_eV": sigma_energy,
            "per_atom_eV": total_energy / nions if total_energy is not None and nions else None,
            "fermi_eV": fermi,
            "normalization": "cell",
        } if total_energy is not None else None,
        forces={
            "unit": "eV/Angstrom",
            "vectors": force_blocks[-1] if force_blocks else [],
            "max_norm_eV_per_A": max_norm(force_blocks[-1]) if force_blocks else None,
        } if force_blocks else None,
        stress={
            "unit": "GPa",
            "voigt_order": ["xx", "yy", "zz", "xy", "yz", "zx"],
            "tensor_voigt_GPa": [value * 0.1 for value in stress_kbar],
            "source_unit": "kbar",
        } if stress_kbar else None,
        magnetization={"total_muB": magnetization} if magnetization is not None else None,
        final_structure=parse_poscar(root / "CONTCAR") or parse_poscar(root / "POSCAR"),
        warnings=sorted(set(warnings)),
        confidence="high" if normal and total_energy is not None else ("medium" if total_energy is not None else "low"),
    )
    bands = vasp_eigenval(root / "EIGENVAL")
    dos = vasp_doscar(root / "DOSCAR")
    if bands or dos:
        result["electronic_structure"] = {
            "fermi_eV": fermi,
            "band_gap_eV": bands.get("band_gap_eV") if bands else None,
            "vbm_eV": bands.get("vbm_eV") if bands else None,
            "cbm_eV": bands.get("cbm_eV") if bands else None,
            "bands": bands,
            "dos": dos,
        }
        for name in ("EIGENVAL", "DOSCAR"):
            path = root / name
            if path.is_file():
                result["source_files"].append(source_record(path, root))
    if result["convergence"]["electronic"] is None:
        result["warnings"].append("electronic convergence could not be established from OUTCAR")
    validate_result(result)
    return result
