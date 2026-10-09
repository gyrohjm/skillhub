"""Conservative Wannier90 text readers. No engine invocation or file writes."""
from __future__ import annotations

import math
import re


class InputError(ValueError):
    """An input is malformed or ambiguous; never substitute a guessed value."""


NUMBER = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[EeDd][+-]?\d+)?"


def number(value: str) -> float:
    try:
        result = float(value.replace("D", "E").replace("d", "e"))
    except ValueError as exc:
        raise InputError(f"not a number: {value!r}") from exc
    if not math.isfinite(result):
        raise InputError(f"non-finite number: {value!r}")
    return result


def integer(value: str, *, minimum: int | None = 1) -> int:
    if not re.fullmatch(r"[+-]?\d+", value.strip()):
        raise InputError(f"not an integer: {value!r}")
    result = int(value)
    if minimum is not None and result < minimum:
        raise InputError(f"integer must be >= {minimum}: {value!r}")
    return result


def uncomment(line: str) -> str:
    quote = None
    i = 0
    while i < len(line):
        char = line[i]
        if quote:
            if char == quote:
                if i + 1 < len(line) and line[i + 1] == quote:
                    i += 2
                    continue
                quote = None
        elif char in "\"'":
            quote = char
        elif char in "!#":
            return line[:i].strip()
        i += 1
    if quote:
        raise InputError("unterminated quoted string")
    return line.strip()


def band_list(value: str) -> list[int]:
    value = re.sub(r"\s*([:-])\s*", r"\1", value.strip())
    tokens = re.split(r"[\s,;]+", value)
    bands = set()
    for token in tokens:
        match = re.fullmatch(r"(\d+)(?:[:-](\d+))?", token)
        if not match:
            raise InputError(f"invalid excluded band/range: {token!r}")
        first = integer(match[1])
        last = integer(match[2]) if match[2] else first
        first, last = min(first, last), max(first, last)
        if last > 1_000_000:
            raise InputError("unsupported huge band range")
        for band in range(first, last + 1):
            if band in bands:
                raise InputError(f"duplicate excluded band: {band}")
            bands.add(band)
    return sorted(bands)


def _scalar(key: str, value: str):
    positive = {"num_wann", "num_bands", "num_kpts"}
    nonnegative = {"num_iter", "dis_num_iter", "dis_conv_window", "dis_spheres_num"}
    logical = {"spinors", "dis_froz_proj", "dis_proj_auto", "site_symmetry", "use_bloch_phases", "gamma_only", "auto_projections"}
    real = {"dis_win_min", "dis_win_max", "dis_froz_min", "dis_froz_max", "dis_proj_min", "dis_proj_max", "conv_tol", "dis_conv_tol", "dis_mix_ratio"}
    if key in positive | nonnegative:
        return integer(value, minimum=0 if key in nonnegative else 1)
    if key == "conv_window":
        return integer(value, minimum=None)
    if key in real:
        return number(value)
    if key in logical:
        if value.lower() in {"true", ".true.", "t"}:
            return True
        if value.lower() in {"false", ".false.", "f"}:
            return False
        raise InputError(f"invalid logical {key}: {value!r}")
    if key == "mp_grid":
        parts = re.split(r"[\s,]+", value)
        if len(parts) != 3:
            raise InputError("mp_grid needs three positive integers")
        return [integer(x) for x in parts]
    if key == "exclude_bands":
        return band_list(value)
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1].replace(value[0] * 2, value[0])
    if re.fullmatch(NUMBER, value):
        return number(value)
    return value


def parse_win(text: str) -> dict:
    """Read scalar assignments and preserve blocks; do not expand projections."""
    parameters, blocks, sources = {}, {}, {}
    active = None
    for lineno, raw in enumerate(text.splitlines(), 1):
        try:
            line = uncomment(raw)
            if not line:
                continue
            boundary = re.fullmatch(r"(begin|end)\s*:?\s+(\w+)", line, re.I)
            if boundary:
                action, name = boundary[1].lower(), boundary[2].lower()
                if action == "begin":
                    if active or name in blocks:
                        raise InputError("nested or repeated input block")
                    active = name
                    blocks[name] = []
                else:
                    if active != name:
                        raise InputError("unmatched block terminator")
                    active = None
                continue
            if active:
                blocks[active].append(line)
                continue
            match = re.fullmatch(r"([A-Za-z_]\w*)\s*(?:=|:|\s)\s*(.+)", line)
            if not match:
                raise InputError(f"unsupported input statement: {line!r}")
            key = match[1].lower()
            value = _scalar(key, match[2].strip())
            if key in parameters and parameters[key] != value:
                raise InputError(f"conflicting duplicate parameter: {key}")
            parameters[key] = value
            sources.setdefault(key, []).append(lineno)
        except InputError as exc:
            raise InputError(f"win line {lineno}: {exc}") from exc
    if active:
        raise InputError(f"unterminated block: {active}")
    kpoints = []
    for line in blocks.get("kpoints", []):
        parts = line.split()
        if len(parts) != 3:
            raise InputError("kpoints requires three crystallographic coordinates per row")
        kpoints.append([number(x) for x in parts])
    return {"parameters": parameters, "blocks": blocks, "sources": sources, "kpoints": kpoints}


def parse_eig(text: str) -> dict[int, dict[int, float]]:
    """Return k-index -> band-index -> eV; reject duplicate/non-finite entries."""
    rows = {}
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = uncomment(raw)
        if not line:
            continue
        parts = line.split()
        if len(parts) != 3:
            raise InputError(f"eig line {lineno}: expected band, k-index, eigenvalue")
        band, kpoint, energy = integer(parts[0]), integer(parts[1]), number(parts[2])
        if band in rows.setdefault(kpoint, {}):
            raise InputError(f"eig line {lineno}: duplicate band {band} at k={kpoint}")
        rows[kpoint][band] = energy
    if not rows:
        raise InputError("empty eig file")
    return rows


def parse_wout(text: str, *, num_wann=None, dis_num_iter=None, num_iter=None) -> dict:
    """Read common W90 3.x markers, keeping absent evidence as None."""
    lines = text.splitlines()
    starts = [i for i, line in enumerate(lines) if re.fullmatch(r"\s*\|?\s*WANNIER90\s*\|?\s*", line, re.I)]
    start = starts[-1] if starts else 0
    result = {
        "version": None, "run_start_line": start + 1,
        "normal_termination": None, "disentanglement_converged": None,
        "localization_converged": None, "reached_dis_num_iter": None,
        "reached_num_iter": None, "omega_i_history": [], "spread_history": [],
        "dis_iterations": [], "localization_iterations": [], "final_centres": [],
        "final_state_complete": None, "spread_unit": None,
        "errors": [], "warnings": [], "evidence_lines": {},
    }
    active_final, summary_seen = False, False
    centre = re.compile(r"WF\s+centre\s+and\s+spread\s+(\d+)\s*\(\s*(" + NUMBER + r")\s*,\s*(" + NUMBER + r")\s*,\s*(" + NUMBER + r")\s*\)\s*(" + NUMBER + r")", re.I)
    summary = re.compile(r"Sum\s+of\s+centres\s+and\s+spreads\s*\(\s*(" + NUMBER + r")\s*,\s*(" + NUMBER + r")\s*,\s*(" + NUMBER + r")\s*\)\s*(" + NUMBER + r")\s*$", re.I)
    for lineno in range(start + 1, len(lines) + 1):
        line = lines[lineno - 1]
        low = line.lower()
        version = re.search(r"\bRelease\s*:\s*(\d+\.\d+(?:\.\d+)?)", line, re.I)
        if version:
            result["version"] = version[1]
        evidence = {"line": lineno, "text": line.strip()}
        if re.search(r"(?:^|[\s*|])(?:error\s*[:!]|fatal\b|MPI_ABORT\b|segmentation fault|forrtl:\s*severe)", line, re.I):
            result["errors"].append(evidence)
        if re.fullmatch(r"\s*Exiting\.{7}\s*", line, re.I):
            diagnostic = next((following.strip() for following in lines[lineno:] if following.strip()), "")
            result["errors"].append({**evidence, "text": line.strip() + (" " + diagnostic if diagnostic else "")})
        if "warning" in low:
            result["warnings"].append(evidence)
        if re.search(r"\ball done\b", line, re.I):
            result["normal_termination"] = True
            result["evidence_lines"]["normal_termination"] = lineno
        for label, stem in (("disentanglement_converged", "disentanglement"), ("localization_converged", "wannierisation")):
            if re.search(stem + r"\s+(?:convergence criteria satisfied|convergence achieved|converged)\b", low):
                result[label] = True
                result["evidence_lines"][label] = lineno
            if re.search(stem + r"\s+(?:not converged|failed to converge|convergence not achieved|convergence criteria not satisfied)\b", low):
                result[label] = False
                result["evidence_lines"][label] = lineno
        unit = re.search(r"(?:Spread|Spreads)\s*\((Ang|Bohr)\^2\)", line, re.I)
        if unit:
            result["spread_unit"] = "Bohr^2" if unit[1].lower() == "bohr" else "Ang^2"
        if "<--" in line:
            data, marker = line.split("<--", 1)
            parts = data.split()
            if parts and re.fullmatch(r"\d+", parts[0]) and marker.strip() in {"DIS", "CONV"}:
                try:
                    values = [number(p) for p in parts]
                    if marker.strip() == "DIS" and len(values) == 5:
                        result["omega_i_history"].append(values[2])
                        result["dis_iterations"].append(int(values[0]))
                    elif marker.strip() == "CONV" and len(values) in {4, 5}:
                        result["spread_history"].append(values[-2])
                        result["localization_iterations"].append(int(values[0]))
                    else:
                        result["warnings"].append({**evidence, "code": "UNPARSED_ITERATION"})
                except InputError:
                    result["warnings"].append({**evidence, "code": "UNPARSED_ITERATION"})
        if line.strip().lower() == "final state":
            active_final, summary_seen = True, False
            result["final_centres"] = []
            result["evidence_lines"]["final_state"] = lineno
        elif re.match(r"\s*(?:Initial State\b|Cycle\s*:)", line, re.I):
            active_final = False
        if active_final:
            match = centre.search(line)
            if match:
                result["final_centres"].append({"id": int(match[1]), "centre": [number(match[i]) for i in (2, 3, 4)], "spread": number(match[5]), "line": lineno})
            if "sum of centres and spreads" in low:
                total = summary.search(line)
                if total:
                    try:
                        [number(total[i]) for i in (1, 2, 3, 4)]
                        summary_seen = True
                    except InputError:
                        result["warnings"].append({**evidence, "code": "INVALID_FINAL_SUMMARY"})
                active_final = False
    if "final_state" in result["evidence_lines"]:
        ids = [item["id"] for item in result["final_centres"]]
        expected = num_wann if num_wann is not None else len(ids)
        result["final_state_complete"] = bool(summary_seen and ids and len(ids) == expected and ids == list(range(1, expected + 1)))
    if result["errors"]:
        result["normal_termination"] = False
    for key, limit, history in (("reached_dis_num_iter", dis_num_iter, "dis_iterations"), ("reached_num_iter", num_iter, "localization_iterations")):
        if limit is not None and result[history]:
            result[key] = max(result[history]) >= limit
    return result
