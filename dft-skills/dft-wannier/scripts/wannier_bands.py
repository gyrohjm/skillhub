"""Metrics on explicitly aligned band datasets; never infer physical acceptance."""
from __future__ import annotations

import math

from wannier_io import InputError


def finite(value) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InputError("band data and thresholds must be numeric, not strings or booleans")
    if not math.isfinite(value):
        raise InputError("band data and thresholds must be finite")
    return float(value)


def validate_dataset(data: dict) -> None:
    if not isinstance(data, dict) or type(data.get("schema_version")) is not int or data["schema_version"] != 1:
        raise InputError("expected band dataset schema_version 1")
    required = {"units": "eV", "kpoint_basis": "fractional", "matching": "explicit_band_ids"}
    for key, value in required.items():
        if data.get(key) != value:
            raise InputError(f"{key} must be {value!r}")
    for key in ("energy_reference", "system_id"):
        if not isinstance(data.get(key), str) or not data[key].strip():
            raise InputError(f"explicit {key} is required")
    if data.get("sampling") not in {"independent", "high_symmetry_path", "training_grid"}:
        raise InputError("sampling must declare independent, high_symmetry_path or training_grid")
    ids = data.get("band_ids")
    if not isinstance(ids, list) or not ids or not all(isinstance(b, str) and b.strip() for b in ids) or len(set(ids)) != len(ids):
        raise InputError("band_ids must be a nonempty list of unique explicit correspondence labels")
    points, energies = data.get("kpoints"), data.get("energies")
    if not isinstance(points, list) or not points or not isinstance(energies, list) or len(points) != len(energies):
        raise InputError("kpoints and energies must have the same nonzero row count")
    for point, row in zip(points, energies):
        if not isinstance(point, list) or len(point) != 3 or not isinstance(row, list) or len(row) != len(ids):
            raise InputError("each k row needs three coordinates and one energy per band_id")
        for value in point + row:
            finite(value)


def metrics(errors: list[float]) -> dict:
    if not errors:
        return {"count": 0, "mae_mev": None, "rmse_mev": None, "max_error_mev": None}
    magnitude = [abs(value) for value in errors]
    count = len(errors)
    return {
        "count": count, "mae_mev": math.fsum(value / count for value in magnitude),
        "rmse_mev": math.hypot(*errors) / math.sqrt(count), "max_error_mev": max(magnitude),
    }


def compare_bands(reference: dict, candidate: dict, *, target_window, mae_threshold_mev=None, max_threshold_mev=None) -> dict:
    validate_dataset(reference)
    validate_dataset(candidate)
    if len(target_window) != 2:
        raise InputError("target_window needs a lower and upper energy")
    low, high = (finite(value) for value in target_window)
    if low > high:
        raise InputError("target window is reversed")
    for value in (mae_threshold_mev, max_threshold_mev):
        if value is not None and finite(value) < 0:
            raise InputError("error thresholds must be nonnegative")
    for key in ("system_id", "energy_reference"):
        if reference[key] != candidate[key]:
            raise InputError(f"different {key}: refusing to align energies or physical systems implicitly")
    if set(reference["band_ids"]) != set(candidate["band_ids"]):
        raise InputError("explicit band correspondence differs; dropping bands is not allowed")
    if len(reference["kpoints"]) != len(candidate["kpoints"]):
        raise InputError("k-point row counts differ")
    for ref, pred in zip(reference["kpoints"], candidate["kpoints"]):
        if any(abs(a - b) > 1e-8 for a, b in zip(ref, pred)):
            raise InputError("k-point coordinates/order differ; align using physical provenance before comparison")
    column = {band: i for i, band in enumerate(candidate["band_ids"])}
    rows, errors, target_errors = [], [], []
    for k, (ref, pred) in enumerate(zip(reference["energies"], candidate["energies"]), 1):
        for b, band in enumerate(reference["band_ids"]):
            reference_ev, candidate_ev = ref[b], pred[column[band]]
            error = finite((candidate_ev - reference_ev) * 1000)
            in_target = low <= reference_ev <= high
            rows.append({"k_index": k, "band_id": band, "reference_ev": reference_ev, "candidate_ev": candidate_ev, "error_mev": error, "in_target": in_target})
            errors.append(error)
            if in_target:
                target_errors.append(error)
    target = metrics(target_errors)
    check = "UNKNOWN"
    if target_errors and mae_threshold_mev is not None and max_threshold_mev is not None:
        check = "PASS_ON_SUPPLIED_DATA" if target["mae_mev"] <= mae_threshold_mev and target["max_error_mev"] <= max_threshold_mev else "FAIL"
    independent = reference["sampling"] == candidate["sampling"] == "independent"
    return {
        "schema_version": 1, "kind": "wannier_band_comparison", "sources": {},
        "system_id": reference["system_id"], "energy_reference": reference["energy_reference"],
        "target_window_ev": [low, high], "target_mask": "reference_energies_only",
        "matching": "explicit_band_ids", "kpoint_tolerance": 1e-8,
        "sampling": {"reference": reference["sampling"], "candidate": candidate["sampling"]},
        "independent_validation": independent, "provenance_validation": "USER_DECLARED_NOT_AUTOMATICALLY_VERIFIED",
        "thresholds_mev": {"mae": mae_threshold_mev, "max_error": max_threshold_mev},
        "global_metrics": metrics(errors), "target_metrics": target,
        "threshold_check": check, "decision": "REFINE_MODEL" if check == "FAIL" else "NEEDS_AGENT",
        "scientifically_accepted": None, "errors": rows,
        "limitations": ["Metrics apply only to supplied points and explicit band correspondence.", "Sampling independence, structure/spin identity and energy reference are declarations requiring source verification.", "Energy errors do not validate wavefunctions, topology, Fermi-surface topology or EPC matrix elements."],
    }


def comparison_markdown(report: dict) -> str:
    lines = ["# Wannier band comparison", "", f"Decision: **{report['decision']}**", "",
             f"Threshold check: `{report['threshold_check']}`", "",
             "| Region | Samples | MAE (meV) | RMSE (meV) | Max error (meV) |",
             "|---|---:|---:|---:|---:|"]
    for name in ("global_metrics", "target_metrics"):
        m = report[name]
        lines.append(f"| {name} | {m['count']} | {m['mae_mev']} | {m['rmse_mev']} | {m['max_error_mev']} |")
    lines += ["", f"Energy reference: `{report['energy_reference']}`. Target mask uses reference energies; no energy shift is fitted.", "", "## Evidence", ""]
    for name, source in report["sources"].items():
        lines.append(f"- {name}: `{source['path']}`; SHA256 `{source['sha256']}`")
    lines += ["", "## Limits", ""] + [f"- {value}" for value in report["limitations"]]
    lines += ["", "Scientific acceptance is not established by this report.", ""]
    return "\n".join(lines)
