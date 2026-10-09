from __future__ import annotations

from pathlib import Path
from typing import Any


def floats(line: str) -> list[float]:
    values: list[float] = []
    for token in line.replace("D", "E").replace("d", "e").split():
        try:
            values.append(float(token))
        except ValueError:
            continue
    return values


def vasp_eigenval(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    if len(lines) < 7:
        return None
    header = floats(lines[5])
    if len(header) < 3:
        return None
    nelect, nkpoints, nbands = int(header[0]), int(header[1]), int(header[2])
    index = 6
    kpoints: list[list[float]] = []
    weights: list[float] = []
    spin_energies: list[list[list[float]]] = [[], []]
    spin_occupancies: list[list[list[float]]] = [[], []]
    spin_polarized = False
    for _ in range(nkpoints):
        while index < len(lines) and not lines[index].strip():
            index += 1
        if index >= len(lines):
            return None
        kline = floats(lines[index])
        index += 1
        if len(kline) < 4:
            return None
        kpoints.append(kline[:3])
        weights.append(kline[3])
        energies_at_k = [[], []]
        occupations_at_k = [[], []]
        for _band in range(nbands):
            if index >= len(lines):
                return None
            row = floats(lines[index])
            index += 1
            if len(row) >= 5:
                spin_polarized = True
                energies_at_k[0].append(row[1])
                energies_at_k[1].append(row[2])
                occupations_at_k[0].append(row[3])
                occupations_at_k[1].append(row[4])
            elif len(row) >= 3:
                energies_at_k[0].append(row[1])
                occupations_at_k[0].append(row[2])
            else:
                return None
        for channel in range(2 if spin_polarized else 1):
            spin_energies[channel].append(energies_at_k[channel])
            spin_occupancies[channel].append(occupations_at_k[channel])
    occupied: list[float] = []
    unoccupied: list[float] = []
    channels = 2 if spin_polarized else 1
    for channel in range(channels):
        for energies, occupations in zip(spin_energies[channel], spin_occupancies[channel]):
            for energy, occupation in zip(energies, occupations):
                (occupied if occupation > 0.5 else unoccupied).append(energy)
    vbm = max(occupied) if occupied else None
    cbm = min(unoccupied) if unoccupied else None
    gap = max(0.0, cbm - vbm) if vbm is not None and cbm is not None else None
    return {
        "source": path.name,
        "unit": "eV",
        "electron_count": nelect,
        "kpoints": kpoints,
        "weights": weights,
        "energies_by_spin_eV": spin_energies[:channels],
        "occupancies_by_spin": spin_occupancies[:channels],
        "spin_channels": channels,
        "vbm_eV": vbm,
        "cbm_eV": cbm,
        "band_gap_eV": gap,
        "gap_method": "occupation_threshold_0.5",
    }


def vasp_doscar(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    if len(lines) < 7:
        return None
    header = floats(lines[5])
    if len(header) < 4:
        return None
    nedos, fermi = int(header[2]), header[3]
    rows = [floats(line) for line in lines[6 : 6 + nedos]]
    rows = [row for row in rows if len(row) >= 3]
    if not rows:
        return None
    spin_polarized = len(rows[0]) >= 5
    value: dict[str, Any] = {
        "source": path.name,
        "energy_eV": [row[0] for row in rows],
        "fermi_eV": fermi,
        "spin_channels": 2 if spin_polarized else 1,
    }
    if spin_polarized:
        value["dos_states_per_eV"] = [[row[1] for row in rows], [row[2] for row in rows]]
    else:
        value["dos_states_per_eV"] = [[row[1] for row in rows]]
    return value


def qe_bands_gnu(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    bands: list[list[list[float]]] = []
    current: list[list[float]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        row = floats(line)
        if len(row) >= 2:
            current.append(row[:2])
        elif current:
            bands.append(current)
            current = []
    if current:
        bands.append(current)
    if not bands:
        return None
    return {"source": path.name, "unit": "eV", "bands": bands, "band_gap_eV": None}


def qe_dos(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    rows = [floats(line) for line in path.read_text(encoding="utf-8", errors="replace").splitlines()]
    rows = [row for row in rows if len(row) >= 2]
    if not rows:
        return None
    return {
        "source": path.name,
        "energy_eV": [row[0] for row in rows],
        "dos_states_per_eV": [[row[1] for row in rows]],
        "spin_channels": 1,
    }
