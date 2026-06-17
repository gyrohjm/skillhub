#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

from vaplot_dat import parse_dat
from vaplot_style import (
    BAND_FIG_SIZE,
    FERMI_COLOR,
    FIG_SIZE,
    FILL_ALPHA,
    LINE_WIDTH,
    PALETTE,
    TOTAL_COLOR,
    apply_style,
    color_cycle,
    save_figure,
    style_axes,
)


def load_table(path: Path) -> tuple[dict[str, str], np.ndarray, list[str]]:
    meta, rows, errors = parse_dat(path)
    if errors:
        raise ValueError("; ".join(errors))
    columns = meta["columns"].split()
    return meta, np.asarray(rows, dtype=float), columns


def selected_columns(columns: list[str], requested: list[str] | None) -> list[int]:
    if not requested:
        return list(range(1, len(columns)))
    lookup = {name: idx for idx, name in enumerate(columns)}
    missing = [name for name in requested if name not in lookup]
    if missing:
        raise ValueError("missing columns: " + ", ".join(missing))
    return [lookup[name] for name in requested]


def apply_window(ax, window: list[float] | None, axis: str) -> None:
    if window is None:
        return
    if axis == "x":
        ax.set_xlim(window[0], window[1])
    else:
        ax.set_ylim(window[0], window[1])


def plot_dos(args: argparse.Namespace) -> tuple[Path, Path]:
    import matplotlib.pyplot as plt

    _meta, data, columns = load_table(args.dat)
    x = data[:, 0]
    y_indices = selected_columns(columns, args.columns)

    apply_style()
    fig, ax = plt.subplots(figsize=FIG_SIZE, facecolor="white")
    colors = color_cycle(skip_total=True)

    for idx in y_indices:
        label = columns[idx]
        y = data[:, idx]
        if args.mirror_spin_down and any(token in label.lower() for token in ("down", "dw", "dn")):
            y = -np.abs(y)
        color = TOTAL_COLOR if idx == y_indices[0] and "total" in label.lower() else next(colors)
        ax.plot(x, y, color=color, linewidth=LINE_WIDTH, label=label)
        if args.fill:
            ax.fill_between(x, 0, y, color=color, alpha=FILL_ALPHA)

    ax.axvline(0.0, color=FERMI_COLOR, linestyle="--", linewidth=2.0)
    ax.set_ylim(bottom=None if args.allow_negative_y else 0)
    apply_window(ax, args.window, "x")
    style_axes(ax, args.title, xlabel=args.x_label, ylabel=args.y_label)
    ax.legend(loc=args.legend_loc, framealpha=0.65)
    fig.tight_layout()
    return save_figure(fig, args.output)


def plot_band_like(args: argparse.Namespace, *, phonon: bool = False) -> tuple[Path, Path]:
    import matplotlib.pyplot as plt

    _meta, data, columns = load_table(args.dat)
    x = data[:, 0]
    y_indices = selected_columns(columns, args.columns)

    apply_style()
    fig, ax = plt.subplots(figsize=BAND_FIG_SIZE if args.tall else FIG_SIZE, facecolor="white")
    for idx in y_indices:
        y = data[:, idx]
        if args.window and (np.nanmax(y) < args.window[0] or np.nanmin(y) > args.window[1]):
            continue
        ax.plot(x, y, color=args.color, linewidth=args.linewidth)

    ax.axhline(0.0, color=FERMI_COLOR, linestyle="--", linewidth=2.0)
    apply_window(ax, args.window, "y")
    style_axes(
        ax,
        args.title,
        xlabel=args.x_label,
        ylabel=args.y_label or ("Frequency" if phonon else "Energy (eV)"),
    )
    fig.tight_layout()
    return save_figure(fig, args.output)


def plot_profile(args: argparse.Namespace) -> tuple[Path, Path]:
    import matplotlib.pyplot as plt

    _meta, data, columns = load_table(args.dat)
    x = data[:, 0]
    y_indices = selected_columns(columns, args.columns)

    apply_style()
    fig, ax = plt.subplots(figsize=FIG_SIZE, facecolor="white")
    colors = color_cycle(skip_total=True)
    for idx in y_indices:
        color = next(colors)
        ax.plot(x, data[:, idx], color=color, linewidth=LINE_WIDTH, label=columns[idx])
    if args.zero_line:
        ax.axhline(0.0, color=FERMI_COLOR, linestyle="--", linewidth=1.8)
    style_axes(ax, args.title, xlabel=args.x_label, ylabel=args.y_label)
    if len(y_indices) > 1 or args.legend:
        ax.legend(loc=args.legend_loc, framealpha=0.65)
    fig.tight_layout()
    return save_figure(fig, args.output)


def plot_cohp(args: argparse.Namespace) -> tuple[Path, Path]:
    import matplotlib.pyplot as plt

    _meta, data, columns = load_table(args.dat)
    energy = data[:, 0]
    y_indices = selected_columns(columns, args.columns)

    apply_style()
    fig, ax = plt.subplots(figsize=FIG_SIZE, facecolor="white")
    colors = color_cycle(skip_total=True)
    for idx in y_indices:
        x = data[:, idx]
        if args.negate:
            x = -x
        ax.plot(x, energy, color=next(colors), linewidth=LINE_WIDTH, label=columns[idx])
    ax.axhline(0.0, color=FERMI_COLOR, linestyle="--", linewidth=2.0)
    ax.axvline(0.0, color="#444444", linestyle="--", linewidth=1.4)
    apply_window(ax, args.window, "y")
    style_axes(ax, args.title, xlabel=args.x_label, ylabel=args.y_label)
    ax.legend(loc=args.legend_loc, framealpha=0.65)
    fig.tight_layout()
    return save_figure(fig, args.output)


def plot_heatmap(args: argparse.Namespace) -> tuple[Path, Path]:
    import matplotlib.pyplot as plt
    import matplotlib.tri as tri

    _meta, data, columns = load_table(args.dat)
    if data.shape[1] < 3:
        raise ValueError("heatmap requires at least x, y, value columns")
    x, y, z = data[:, 0], data[:, 1], data[:, 2]

    apply_style()
    fig, ax = plt.subplots(figsize=FIG_SIZE, facecolor="white")
    triang = tri.Triangulation(x, y)
    contour = ax.tricontourf(triang, z, levels=args.levels, cmap=args.cmap)
    fig.colorbar(contour, ax=ax, label=args.colorbar_label)
    style_axes(ax, args.title, xlabel=args.x_label, ylabel=args.y_label, show_grid=False)
    ax.set_aspect(args.aspect)
    fig.tight_layout()
    return save_figure(fig, args.output)


def common_xy_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--dat", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--title", default="")
    parser.add_argument("--columns", nargs="*", default=None, help="Y/value columns to plot by name.")
    parser.add_argument("--legend-loc", default="upper right")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Plot vaplot .dat files with the user's notebook style.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    dos = sub.add_parser("dos")
    common_xy_args(dos)
    dos.add_argument("--window", nargs=2, type=float, default=None)
    dos.add_argument("--x-label", default="Energy (eV)")
    dos.add_argument("--y-label", default="DOS (states/eV)")
    dos.add_argument("--fill", action="store_true", default=True)
    dos.add_argument("--no-fill", action="store_false", dest="fill")
    dos.add_argument("--mirror-spin-down", action="store_true", default=True)
    dos.add_argument("--no-mirror-spin-down", action="store_false", dest="mirror_spin_down")
    dos.add_argument("--allow-negative-y", action="store_true")
    dos.set_defaults(func=plot_dos)

    band = sub.add_parser("band")
    common_xy_args(band)
    band.add_argument("--window", nargs=2, type=float, default=None)
    band.add_argument("--x-label", default="k-point")
    band.add_argument("--y-label", default="Energy (eV)")
    band.add_argument("--color", default="#1f77b4")
    band.add_argument("--linewidth", type=float, default=1.25)
    band.add_argument("--tall", action="store_true", default=True)
    band.set_defaults(func=lambda args: plot_band_like(args, phonon=False))

    phb = sub.add_parser("phonon-band")
    common_xy_args(phb)
    phb.add_argument("--window", nargs=2, type=float, default=None)
    phb.add_argument("--x-label", default="Wave vector")
    phb.add_argument("--y-label", default="Frequency")
    phb.add_argument("--color", default="black")
    phb.add_argument("--linewidth", type=float, default=1.25)
    phb.add_argument("--tall", action="store_true", default=False)
    phb.set_defaults(func=lambda args: plot_band_like(args, phonon=True))

    phd = sub.add_parser("phonon-dos")
    common_xy_args(phd)
    phd.add_argument("--window", nargs=2, type=float, default=None)
    phd.add_argument("--x-label", default="Frequency")
    phd.add_argument("--y-label", default="Phonon DOS")
    phd.add_argument("--fill", action="store_true", default=True)
    phd.add_argument("--no-fill", action="store_false", dest="fill")
    phd.add_argument("--mirror-spin-down", action="store_false", default=False)
    phd.add_argument("--allow-negative-y", action="store_true")
    phd.set_defaults(func=plot_dos)

    profile = sub.add_parser("profile")
    common_xy_args(profile)
    profile.add_argument("--x-label", default="")
    profile.add_argument("--y-label", default="")
    profile.add_argument("--zero-line", action="store_true", default=True)
    profile.add_argument("--no-zero-line", action="store_false", dest="zero_line")
    profile.add_argument("--legend", action="store_true")
    profile.set_defaults(func=plot_profile)

    cohp = sub.add_parser("cohp")
    common_xy_args(cohp)
    cohp.add_argument("--window", nargs=2, type=float, default=None)
    cohp.add_argument("--x-label", default="-pCOHP")
    cohp.add_argument("--y-label", default="Energy (eV)")
    cohp.add_argument("--negate", action="store_true", default=True)
    cohp.add_argument("--no-negate", action="store_false", dest="negate")
    cohp.set_defaults(func=plot_cohp)

    heatmap = sub.add_parser("heatmap")
    common_xy_args(heatmap)
    heatmap.add_argument("--x-label", default="x")
    heatmap.add_argument("--y-label", default="y")
    heatmap.add_argument("--colorbar-label", default="value")
    heatmap.add_argument("--levels", type=int, default=80)
    heatmap.add_argument("--cmap", default="viridis")
    heatmap.add_argument("--aspect", default="equal")
    heatmap.set_defaults(func=plot_heatmap)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        png, pdf = args.func(args)
    except Exception as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 1
    print(f"[wrote] {png}")
    print(f"[wrote] {pdf}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
