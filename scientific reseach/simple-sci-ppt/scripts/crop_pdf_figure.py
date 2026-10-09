#!/usr/bin/env python
"""Render and crop a figure region from a PDF page."""
from __future__ import annotations

import argparse
from pathlib import Path


def parse_box(text: str) -> tuple[int, int, int, int]:
    parts = [int(float(x.strip())) for x in text.split(",")]
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("Box must be x0,y0,x1,y1 in rendered-pixel coordinates.")
    x0, y0, x1, y1 = parts
    if x1 <= x0 or y1 <= y0:
        raise argparse.ArgumentTypeError("Box must satisfy x1 > x0 and y1 > y0.")
    return x0, y0, x1, y1


def main() -> int:
    parser = argparse.ArgumentParser(description="Crop a paper figure from a rendered PDF page.")
    parser.add_argument("pdf", help="Input PDF path.")
    parser.add_argument("--page", type=int, required=True, help="1-based page number.")
    parser.add_argument("--box", type=parse_box, required=True, help="Crop box: x0,y0,x1,y1 in rendered pixels.")
    parser.add_argument("--out", required=True, help="Output PNG path.")
    parser.add_argument("--dpi", type=int, default=180, help="Rendering resolution.")
    args = parser.parse_args()

    import pdfplumber

    pdf_path = Path(args.pdf).expanduser().resolve()
    out = Path(args.out).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)

    with pdfplumber.open(pdf_path) as pdf:
        if args.page < 1 or args.page > len(pdf.pages):
            raise SystemExit(f"Page out of range: {args.page}; PDF has {len(pdf.pages)} pages.")
        rendered = pdf.pages[args.page - 1].to_image(resolution=args.dpi).original
        rendered.crop(args.box).save(out)

    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
