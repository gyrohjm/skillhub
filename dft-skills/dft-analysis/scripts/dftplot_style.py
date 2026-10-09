#!/usr/bin/env python3
from __future__ import annotations

import io
import os
import tempfile
from pathlib import Path
from typing import Iterable


SAVE_DPI = 600
FIG_SIZE = (10.0, 6.0)
BAND_FIG_SIZE = (8.0, 10.0)
FONT_SIZE = 28
AXIS_LABEL_SIZE = 28
TITLE_SIZE = 28
TICK_SIZE = 28
LEGEND_SIZE = 28
LINE_WIDTH = 2.5
REFERENCE_LINEWIDTH = 2.0
FERMI_COLOR = "#B2182B"
REFERENCE_COLOR = "#9E9E9E"
TOTAL_COLOR = "black"
GRID_ALPHA = 0.30
FILL_ALPHA = 0.22
REFERENCE_ALPHA = 0.28
SPINE_WIDTH = 1.5

PALETTE = [
    TOTAL_COLOR,
    "#1F4E79",
    "#D97706",
    "#2A9D8F",
    "#6A3D9A",
    "#C62828",
    "#4D4D4D",
    "#7A5195",
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
        "font.sans-serif": ["Arial", "DejaVu Sans"],
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
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
    ax.tick_params(direction="in", width=SPINE_WIDTH, length=7)
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
    _atomic_write(png, png_buf.getvalue())
    _atomic_write(pdf, pdf_buf.getvalue())
    return png, pdf


def _atomic_write(path: Path, payload: bytes) -> None:
    """Write a figure beside its destination, then replace it atomically."""

    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()
