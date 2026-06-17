#!/usr/bin/env python3
from __future__ import annotations

import io
from pathlib import Path
from typing import Iterable


SAVE_DPI = 600
FIG_SIZE = (10.0, 6.0)
BAND_FIG_SIZE = (8.0, 10.0)
FONT_SIZE = 24
AXIS_LABEL_SIZE = 28
TITLE_SIZE = 30
TICK_SIZE = 28
LEGEND_SIZE = 24
LINE_WIDTH = 2.5
REFERENCE_LINEWIDTH = 2.0
FERMI_COLOR = "red"
REFERENCE_COLOR = "#9E9E9E"
TOTAL_COLOR = "black"
GRID_ALPHA = 0.30
FILL_ALPHA = 0.22
REFERENCE_ALPHA = 0.28
SPINE_WIDTH = 1.5

PALETTE = [
    TOTAL_COLOR,
    "#1f77b4",
    "#ff7f0e",
    "#2ca02c",
    "#d62728",
    "#9467bd",
    "#8c564b",
    "#e377c2",
    "#7f7f7f",
    "#17becf",
]


def apply_style() -> None:
    import matplotlib.pyplot as plt

    plt.rcParams.update({
        "font.size": FONT_SIZE,
        "axes.labelsize": AXIS_LABEL_SIZE,
        "axes.titlesize": TITLE_SIZE,
        "xtick.labelsize": TICK_SIZE,
        "ytick.labelsize": TICK_SIZE,
        "legend.fontsize": LEGEND_SIZE,
        "figure.figsize": FIG_SIZE,
        "font.family": ["Arial", "DejaVu Sans"],
        "axes.unicode_minus": False,
    })


def style_axes(ax, title: str | None = None, *, xlabel: str = "", ylabel: str = "", show_grid: bool = True) -> None:
    if xlabel:
        ax.set_xlabel(xlabel, fontweight="bold")
    if ylabel:
        ax.set_ylabel(ylabel, fontweight="bold")
    if title:
        ax.set_title(title, fontweight="bold", pad=20)
    if show_grid:
        ax.grid(True, alpha=GRID_ALPHA, linestyle="--")
    for spine in ax.spines.values():
        spine.set_linewidth(SPINE_WIDTH)


def color_cycle(skip_total: bool = False) -> Iterable[str]:
    start = 1 if skip_total else 0
    while True:
        for color in PALETTE[start:]:
            yield color


def save_figure(fig, output_prefix: str | Path) -> tuple[Path, Path]:
    output = Path(output_prefix)
    output.parent.mkdir(parents=True, exist_ok=True)
    png = output.with_suffix(".png")
    pdf = output.with_suffix(".pdf")

    png_buf = io.BytesIO()
    pdf_buf = io.BytesIO()
    fig.savefig(png_buf, format="png", dpi=SAVE_DPI, bbox_inches="tight", facecolor="white")
    fig.savefig(pdf_buf, format="pdf", bbox_inches="tight", facecolor="white")
    png.write_bytes(png_buf.getvalue())
    pdf.write_bytes(pdf_buf.getvalue())
    return png, pdf
