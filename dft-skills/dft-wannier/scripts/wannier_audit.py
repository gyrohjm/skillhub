"""Read-only Wannier inspection CLI, Python 3.10+, standard library only."""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
import math
from pathlib import Path
import sys

from wannier_io import InputError, parse_eig, parse_win, parse_wout
from wannier_bands import compare_bands, comparison_markdown


def issue(code: str, message: str, **evidence) -> dict:
    return {"code": code, "message": message, **evidence}


def check_windows(config: dict, eig: dict, *, band_space: str | None = None) -> dict:
    """Energy-only necessary conditions, not whole-input or scientific acceptance.

    num_bands is the effective W90 count. Original-space input must contain the
    full original band set; effective-space input is never excluded twice.
    """
    p = config["parameters"]
    result = {"status": "UNKNOWN", "issues": [], "per_k": [], "band_mapping": [], "window_sources": {}}
    problems = result["issues"]
    if "dis_froz_min" in p and "dis_froz_max" not in p:
        result["status"] = "FAIL"
        problems.append(issue("WINDOW_ORDER", "dis_froz_min requires dis_froz_max; the lower bound cannot be silently ignored."))
        return result
    nw, nb = p.get("num_wann"), p.get("num_bands")
    if nw is None or nb is None:
        problems.append(issue("MISSING_DIMENSIONS", "Explicit num_wann and effective num_bands are required."))
        return result
    if nw > nb:
        result["status"] = "FAIL"
        problems.append(issue("MODEL_DIMENSION", "num_wann exceeds effective num_bands."))
        return result
    special = [k for k in ("dis_froz_proj", "dis_proj_auto", "site_symmetry", "dis_spheres_num") if p.get(k)]
    special += [k for k in ("dis_proj_min", "dis_proj_max") if k in p]
    if special or "dis_spheres" in config["blocks"]:
        problems.append(issue("UNSUPPORTED_MODE", "Energy-only counting cannot validate special disentanglement/symmetry modes.", parameters=special))
        return result
    excluded = p.get("exclude_bands", [])
    if band_space not in {None, "effective", "original"}:
        raise InputError("band_space must be effective or original")
    if excluded and band_space is None:
        problems.append(issue("AMBIGUOUS_BAND_SPACE", "Specify whether eig indices are original DFT or already effective W90 indices."))
        return result
    original = band_space == "original"
    n_input_bands = nb + len(excluded) if original else nb
    # Compare ranges without constructing an array controlled by malformed huge indices.
    def contiguous(indices, count):
        ordered = sorted(indices)
        return len(ordered) == count and all(value == i for i, value in enumerate(ordered, 1))

    if original and excluded and max(excluded) > n_input_bands:
        result["status"] = "FAIL"
        problems.append(issue("BAND_MAP", "Excluded bands are outside the inferred original full band set."))
        return result
    nk_grid = math.prod(p["mp_grid"]) if p.get("mp_grid") else None
    nk_points = len(config["kpoints"]) or None
    if nk_grid and nk_points and nk_grid != nk_points:
        result["status"] = "FAIL"
        problems.append(issue("KPOINT_COUNT", "mp_grid and explicit kpoints count disagree."))
        return result
    nk = nk_grid or nk_points or p.get("num_kpts")
    if nk is None:
        problems.append(issue("MISSING_K_COUNT", "Expected source k-point count is absent; a truncated eig cannot be excluded."))
        return result
    if not contiguous(eig, nk) or any(not contiguous(row, n_input_bands) for row in eig.values()):
        result["status"] = "FAIL"
        problems.append(issue("EIG_SHAPE", "eig must have every expected band at every expected k index exactly once.", expected_kpoints=nk, expected_bands=n_input_bands, observed_kpoints=len(eig)))
        return result
    kept = [b for b in sorted(next(iter(eig.values()))) if not original or b not in excluded]
    if original:
        result["band_mapping"] = [{"original": b, "effective": i} for i, b in enumerate(kept, 1)]
    result["band_space"] = band_space or "effective"
    if nw == nb:
        result["status"] = "PASS"
        result["mode"] = "isolated_subspace_no_disentanglement"
        return result
    energies = [row[b] for row in eig.values() for b in kept]
    lo = p.get("dis_win_min", min(energies))
    hi = p.get("dis_win_max", max(energies))
    fhi = p.get("dis_froz_max")
    flo = p.get("dis_froz_min", lo) if fhi is not None else None
    result["windows_ev"] = {"outer_min": lo, "outer_max": hi, "frozen_min": flo, "frozen_max": fhi}
    result["window_sources"] = {
        "outer_min": "win" if "dis_win_min" in p else "eigenvalue_min_default",
        "outer_max": "win" if "dis_win_max" in p else "eigenvalue_max_default",
        "frozen_min": "disabled" if fhi is None else "win" if "dis_froz_min" in p else "outer_min_default",
        "frozen_max": "win" if fhi is not None else "disabled",
    }
    if lo > hi or (fhi is not None and not lo <= flo <= fhi <= hi):
        result["status"] = "FAIL"
        problems.append(issue("WINDOW_ORDER", "Inner window must be ordered and contained in outer window."))
        return result
    for k, row in sorted(eig.items()):
        values = [row[b] for b in kept]
        n_outer = sum(lo <= energy <= hi for energy in values)
        n_frozen = sum(flo <= energy <= fhi for energy in values) if fhi is not None else 0
        result["per_k"].append({"k_index": k, "n_outer": n_outer, "n_frozen": n_frozen})
        if n_outer < nw:
            problems.append(issue("OUTER_TOO_SMALL", "Outer window contains fewer states than num_wann.", k_index=k, count=n_outer))
        if n_frozen > nw:
            problems.append(issue("FROZEN_TOO_LARGE", "Frozen window contains more states than num_wann.", k_index=k, count=n_frozen))
    result["status"] = "FAIL" if problems else "PASS"
    return result


def inspect(*, win: Path, eig: Path | None = None, wout: Path | None = None, band_space=None) -> dict:
    report = {
        "schema_version": 1, "kind": "wannier_inspection",
        "created_at": datetime.now(timezone.utc).isoformat(), "sources": {},
        "issues": [], "decision": "NEEDS_AGENT", "electronic_fit": "UNKNOWN",
        "scientifically_accepted": None, "window_check": {"status": "UNKNOWN", "issues": [], "per_k": []},
        "energy_convention": "win windows and eig energies must share their original eV reference; no shift is fitted",
    }
    contents = {}
    malformed = False
    for name, path in (("win", win), ("eig", eig), ("wout", wout)):
        if path is None:
            report["issues"].append(issue("NOT_PROVIDED", f"{name} was not provided.", source=name))
            continue
        path = Path(path).resolve()
        try:
            data = path.read_bytes()
            contents[name] = data.decode("utf-8-sig")
            report["sources"][name] = {"path": str(path), "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
        except (OSError, UnicodeError) as exc:
            report["issues"].append(issue("MISSING_FILE" if isinstance(exc, FileNotFoundError) else "UNREADABLE_FILE", str(exc), source=name, path=str(path)))
    config = None
    if "win" in contents:
        try:
            config = parse_win(contents["win"])
            report["input"] = config
        except InputError as exc:
            malformed = True
            report["issues"].append(issue("INVALID_WIN", str(exc)))
    if config is not None and "eig" in contents:
        try:
            report["window_check"] = check_windows(config, parse_eig(contents["eig"]), band_space=band_space)
        except InputError as exc:
            malformed = True
            report["issues"].append(issue("INVALID_EIG", str(exc)))
    if "wout" in contents:
        p = config["parameters"] if config else {}
        report["log"] = parse_wout(contents["wout"], num_wann=p.get("num_wann"), dis_num_iter=p.get("dis_num_iter"), num_iter=p.get("num_iter"))
    failed_log = report.get("log", {}).get("normal_termination") is False
    if malformed or report["window_check"]["status"] == "FAIL" or failed_log:
        report["decision"] = "BLOCKED"
    report["next_action"] = {
        "action": "review_constraint_or_execution_failure" if report["decision"] == "BLOCKED" else "collect_independent_band_validation_and_review_missing_evidence",
        "execution_authorized": False,
        "note": "A passing energy-window count is necessary only; it does not validate projections, matrices, provenance, or electronic interpolation.",
    }
    return report


def markdown(report: dict) -> str:
    if report["kind"] == "wannier_band_comparison":
        return comparison_markdown(report)
    rows = ["# Wannier inspection", "", f"Decision: **{report['decision']}**", "",
            f"Energy-window check: `{report['window_check']['status']}`",
            f"Electronic fit: `{report['electronic_fit']}`; scientific acceptance: not established.", "", "## Evidence", ""]
    for name, source in report["sources"].items():
        rows.append(f"- {name}: `{source['path']}`; SHA256 `{source['sha256']}`")
    rows += ["", "## Findings", ""]
    for item in report["issues"] + report["window_check"]["issues"]:
        rows.append(f"- `{item['code']}`: {item['message']}" + (f" (k={item['k_index']})" if "k_index" in item else ""))
    log = report.get("log")
    if log:
        rows += ["", "## Numerical evidence", ""]
        for key in ("version", "normal_termination", "disentanglement_converged", "localization_converged", "reached_dis_num_iter", "reached_num_iter", "final_state_complete", "spread_unit"):
            rows.append(f"- {key}: `{log[key] if log[key] is not None else 'UNKNOWN'}`")
        for item in log["errors"] + log["warnings"]:
            rows.append(f"- Log line {item['line']}: {item['text']}")
    rows += ["", "## Next action", "", report["next_action"]["action"], "", report["next_action"]["note"], "", "This report is read-only evidence, not submission authorization.", ""]
    return "\n".join(rows)


def save_report(directory: Path, report: dict) -> None:
    """Reserve a fresh directory and never replace another report/input."""
    payloads = {"report.json": json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", "report.md": markdown(report)}
    if report["kind"] == "wannier_band_comparison":
        buffer = io.StringIO(newline="")
        writer = csv.DictWriter(buffer, fieldnames=["k_index", "band_id", "reference_ev", "candidate_ev", "error_mev", "in_target"])
        writer.writeheader()
        writer.writerows(report["errors"])
        payloads["errors.csv"] = buffer.getvalue()
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    created = []
    try:
        for name, payload in payloads.items():
            target = directory / name
            with target.open("x", encoding="utf-8", newline="\n") as stream:
                created.append(target)
                stream.write(payload)
    except BaseException:
        for target in created:
            target.unlink(missing_ok=True)
        try:
            directory.rmdir()
        except OSError:
            pass
        raise


def main(argv=None) -> int:
    # Machine-readable stdout and diagnostics use the same encoding on Windows.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    command = commands.add_parser("inspect", help="Read .win, optional .eig and .wout; never edit calculation files")
    command.add_argument("--win", type=Path, required=True)
    command.add_argument("--eig", type=Path)
    command.add_argument("--wout", type=Path)
    command.add_argument("--band-space", choices=("effective", "original"))
    command.add_argument("--output-dir", type=Path, help="New directory only; omitted means stdout only")
    comparison = commands.add_parser("compare", help="Compare explicitly aligned band JSON datasets; no automatic energy shifts")
    comparison.add_argument("--reference", type=Path, required=True)
    comparison.add_argument("--candidate", type=Path, required=True)
    comparison.add_argument("--target-window", nargs=2, type=float, required=True, metavar=("LOW_EV", "HIGH_EV"))
    comparison.add_argument("--mae-threshold-mev", type=float)
    comparison.add_argument("--max-threshold-mev", type=float)
    comparison.add_argument("--output-dir", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "inspect":
            report = inspect(win=args.win, eig=args.eig, wout=args.wout, band_space=args.band_space)
        else:
            datasets, sources = {}, {}
            for name, path in (("reference", args.reference), ("candidate", args.candidate)):
                data = path.read_bytes()
                datasets[name] = json.loads(data.decode("utf-8-sig"))
                sources[name] = {"path": str(path.resolve()), "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
            report = compare_bands(datasets["reference"], datasets["candidate"], target_window=args.target_window, mae_threshold_mev=args.mae_threshold_mev, max_threshold_mev=args.max_threshold_mev)
            report["sources"] = sources
            report["created_at"] = datetime.now(timezone.utc).isoformat()
        if args.output_dir:
            save_report(args.output_dir, report)
        print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    except (OSError, ValueError) as exc:
        print(f"wannier-audit: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
