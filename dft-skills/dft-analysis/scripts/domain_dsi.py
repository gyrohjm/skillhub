#!/usr/bin/env python3
"""Write domain-pack analysis products for defects, surfaces, and interfaces."""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


ENERGY_ANALYSES = {
    "formation_energy": ("formation_energy_eV", "energy:eV"),
    "surface_energy": ("surface_energy_eV_per_A2", "energy:eV_per_A2"),
    "adsorption_energy": ("adsorption_energy_eV", "energy:eV"),
    "interface_adhesion": ("interface_adhesion_eV_per_A2", "energy:eV_per_A2"),
    "work_function": ("work_function_eV", "energy:eV"),
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def safe_name(value: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9_]+", "_", value.strip()).strip("_")
    return clean or "result"


def analysis_root(case_root: Path) -> Path:
    canonical = case_root / "analysis"
    legacy_roots = (case_root / "9analysis", case_root / "6analysis")
    for candidate in (canonical, *legacy_roots):
        if candidate.is_dir() and any(
            item.is_file() or item.is_symlink() for item in candidate.rglob("*")
        ):
            return candidate
    if canonical.exists():
        return canonical
    for candidate in legacy_roots:
        if candidate.exists():
            return candidate
    return canonical


def write_dat(path: Path, *, source: str, units: str, columns: list[str], rows: list[list[float]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# dftplot_dat_version = 1",
        "# engine = derived_or_recorded_in_source",
        f"# source = {source}",
        f"# units = {units}",
        "# columns = " + " ".join(columns),
    ]
    for row in rows:
        if len(row) != len(columns):
            raise ValueError("row length does not match columns")
        lines.append(" ".join(f"{value:.12g}" for value in row))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_report(
    path: Path,
    *,
    analysis_type: str,
    dat_path: Path,
    verdict: str,
    value_summary: str,
    evidence: list[str],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    evidence_lines = "\n".join(f"- `{item}`" for item in evidence) if evidence else "- 未提供额外证据路径"
    text = f"""# {analysis_type} 分析报告

- analysis_type: `{analysis_type}`
- hypothesis_verdict: `{verdict}`
- plot_data: `{dat_path}`
- generated_at: `{utc_now()}`

## 结果

{value_summary}

## 证据路径

{evidence_lines}

## 后续处理

如果判定为 `inconclusive` 或需要补算收敛/对照，写
`analysis/reports/design_change_request.json` 并交回 `dft-design`。
不要从分析阶段直接进入 production workflow。
"""
    path.write_text(text, encoding="utf-8")


def cmd_energy(args: argparse.Namespace) -> int:
    case_root = args.case_root.expanduser().resolve()
    column, units = ENERGY_ANALYSES[args.analysis_type]
    name = safe_name(args.output_name or args.analysis_type)
    root = analysis_root(case_root)
    dat_path = root / "plot_data" / f"{name}.dat"
    report_path = root / "reports" / f"{name}.md"
    source = args.source or str(case_root)
    write_dat(dat_path, source=source, units=units, columns=["index", column], rows=[[1.0, args.value]])
    write_report(
        report_path,
        analysis_type=args.analysis_type,
        dat_path=dat_path,
        verdict=args.verdict,
        value_summary=f"`{column}` = {args.value:g}",
        evidence=args.evidence,
    )
    print(f"[ok] wrote {dat_path}")
    print(f"[ok] wrote {report_path}")
    return 0


def parse_pair(value: str, *, name: str) -> tuple[float, float]:
    if "=" not in value:
        raise ValueError(f"{name} must use X=Y")
    left, right = value.split("=", 1)
    try:
        return float(left), float(right)
    except ValueError as exc:
        raise ValueError(f"{name} must contain numeric X and Y values") from exc


def cmd_bader(args: argparse.Namespace) -> int:
    case_root = args.case_root.expanduser().resolve()
    rows = [list(parse_pair(item, name="--charge")) for item in args.charge]
    if not rows:
        raise ValueError("at least one --charge atom_index=charge_e entry is required")
    root = analysis_root(case_root)
    dat_path = root / "plot_data" / "bader_charge.dat"
    report_path = root / "reports" / "bader_charge.md"
    write_dat(
        dat_path,
        source=args.source or str(case_root),
        units="charge:e",
        columns=["atom_index", "charge_e"],
        rows=rows,
    )
    write_report(
        report_path,
        analysis_type="bader_charge",
        dat_path=dat_path,
        verdict=args.verdict,
        value_summary=f"写出 {len(rows)} 个 atom 的 Bader charge。",
        evidence=args.evidence,
    )
    print(f"[ok] wrote {dat_path}")
    print(f"[ok] wrote {report_path}")
    return 0


def cmd_chgdiff(args: argparse.Namespace) -> int:
    case_root = args.case_root.expanduser().resolve()
    rows = [list(parse_pair(item, name="--point")) for item in args.point]
    if not rows:
        raise ValueError("at least one --point z_ang=value entry is required")
    root = analysis_root(case_root)
    dat_path = root / "plot_data" / "charge_density_difference.dat"
    report_path = root / "reports" / "charge_density_difference.md"
    write_dat(
        dat_path,
        source=args.source or str(case_root),
        units="z:Angstrom charge_density:e_per_A3",
        columns=["z_ang", "charge_density_difference"],
        rows=rows,
    )
    write_report(
        report_path,
        analysis_type="charge_density_difference",
        dat_path=dat_path,
        verdict=args.verdict,
        value_summary=f"写出 {len(rows)} 个 z-profile 点。",
        evidence=args.evidence,
    )
    print(f"[ok] wrote {dat_path}")
    print(f"[ok] wrote {report_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="domain_dsi.py")
    sub = parser.add_subparsers(dest="command", required=True)

    energy = sub.add_parser("energy", help="Write one scalar DSI energy/work-function result.")
    energy.add_argument("--case-root", type=Path, required=True)
    energy.add_argument("--analysis-type", choices=sorted(ENERGY_ANALYSES), required=True)
    energy.add_argument("--value", type=float, required=True)
    energy.add_argument("--verdict", choices=("supported", "falsified", "inconclusive"), required=True)
    energy.add_argument("--source")
    energy.add_argument("--evidence", action="append", default=[])
    energy.add_argument("--output-name")
    energy.set_defaults(func=cmd_energy)

    bader = sub.add_parser("bader", help="Write Bader charge table.")
    bader.add_argument("--case-root", type=Path, required=True)
    bader.add_argument("--charge", action="append", default=[], help="atom_index=charge_e")
    bader.add_argument("--verdict", choices=("supported", "falsified", "inconclusive"), required=True)
    bader.add_argument("--source")
    bader.add_argument("--evidence", action="append", default=[])
    bader.set_defaults(func=cmd_bader)

    chgdiff = sub.add_parser("chgdiff", help="Write charge-density-difference z profile.")
    chgdiff.add_argument("--case-root", type=Path, required=True)
    chgdiff.add_argument("--point", action="append", default=[], help="z_ang=value")
    chgdiff.add_argument("--verdict", choices=("supported", "falsified", "inconclusive"), required=True)
    chgdiff.add_argument("--source")
    chgdiff.add_argument("--evidence", action="append", default=[])
    chgdiff.set_defaults(func=cmd_chgdiff)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except (OSError, ValueError) as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
