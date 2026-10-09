#!/usr/bin/env python
"""Render a LaTeX math expression to a transparent PNG for PowerPoint display.

The primary formula source of truth remains the LaTeX string in the JavaScript
generator, and MathJax remains the preferred renderer for archival SVG output.
This script produces the companion PNG asset used for stable PowerPoint
insertion and export in local Office environments.
"""
from __future__ import annotations

import argparse
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Render LaTeX math to PNG.")
    parser.add_argument("--latex", required=True, help="LaTeX math expression without surrounding dollar signs")
    parser.add_argument("--out", required=True, help="Output PNG path")
    parser.add_argument("--fontsize", type=float, default=34.0)
    parser.add_argument("--dpi", type=int, default=320)
    parser.add_argument("--pad", type=float, default=0.03)
    args = parser.parse_args()

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    expr = args.latex.strip()
    if not (expr.startswith("$") and expr.endswith("$")):
        expr = f"${expr}$"

    fig = plt.figure(figsize=(0.01, 0.01), dpi=args.dpi)
    fig.patch.set_alpha(0.0)
    fig.text(0, 0, expr, fontsize=args.fontsize, color="black", math_fontfamily="stix")
    fig.savefig(out, dpi=args.dpi, transparent=True, bbox_inches="tight", pad_inches=args.pad)
    plt.close(fig)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
