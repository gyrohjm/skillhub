# Plot Style

这是项目科研图的固定模板。不要让最终图依赖 matplotlib 自动样式或自动坐标
范围；如果某个体系需要不同的版式，应在结构级 `scripts/` 或项目级
`code/templates/` 中复制后显式修改，并在报告中说明。

## Fixed house style

```text
SAVE_DPI = 600
FIG_SIZE = (10, 6)
BAND_FIG_SIZE = (8, 10)
FONT_FAMILY = Arial (fallback: DejaVu Sans)
FONT_SIZE = 28pt
AXIS_LABEL_SIZE = 28pt
TITLE_SIZE = 28pt
TICK_SIZE = 28pt
LEGEND_SIZE = 28pt
LINE_WIDTH = 2.5pt
REFERENCE_LINEWIDTH = 2.0pt
FERMI_COLOR = #B2182B
REFERENCE_COLOR = #9E9E9E
TOTAL_COLOR = #000000
PALETTE = #1F4E79, #D97706, #2A9D8F, #6A3D9A, #C62828, #4D4D4D
GRID_ALPHA = 0.30
FILL_ALPHA = 0.22
REFERENCE_ALPHA = 0.28
SPINE_WIDTH = 1.5pt
```

Rules:

- white figure background; inward ticks; consistent spine and line widths;
- Arial is the requested font. A fallback is allowed only when the runtime
  does not provide Arial; record that fallback in the report if it matters;
- 28pt is the baseline for the stated canvas sizes. Apply the proportional
  typography rules below when changing layout; omit redundant titles;
- Fermi/zero-reference guides use the fixed red dashed color;
- use the fixed palette in order; do not silently choose a new colormap for a
  curve family;
- save both `.png` and `.pdf` at 600 dpi-equivalent output quality;
- write outputs atomically and keep the validated `.dat` source linked from the
  figure/report.

## Typography, legends and canvas proportions

- Design the plotting panels and the intended display/export size together.
  Keep 28pt at the default canvas sizes. When scaling a single panel uniformly,
  scale its fonts, markers and line widths with it; adding panels or an external
  legend is not a reason to scale down all text.
- Keep tick and legend text at 85–100% of the axis-label size. As a house-style
  starting range, axis-label size in points should be about 5–7% of the shorter
  panel dimension in points. Check the rendered result; these ratios are layout
  targets, not grounds for clipping labels or distorting scientific geometry.
- At intended final print size, target 10–12pt text and keep essential text at
  least 9pt unless the user specifies otherwise. Solve crowding by simplifying
  labels, reducing tick density, moving legends or splitting panels before
  shrinking text. Check a preview at actual intended size, not only zoomed in.
- Legend entries should identify the varying quantity concisely (e.g. Mg, B,
  s, p, spin up). Put units on axes/colorbars and common conditions in the caption;
  keep filenames, repeated prefixes and sentences out of legends.
- Place a short legend in genuinely empty space. If it obscures data, occupies
  roughly a quarter of the panel, or has more than about 5–6 entries, consider a
  shared external legend, a compact multi-column legend, or separate panels.
  Deduplicate entries and retain the same ordering and colors across figures.
- Reserve explicit layout space for external legends and colorbars. Preserve
  the data-panel aspect ratio and align comparable panels; enlarge the canvas
  deliberately or wrap the legend rather than compressing the plot into a strip.
  Inspect the full exported canvas for clipping and excessive whitespace.

## Axes, reference choices and visual hierarchy

- Keep both major and minor tick marks strictly inside the axis bounds: no ticks
  at the four corners. Select tick density for legibility; not every sampled
  point needs a tick label. Give ordinary endpoints/markers a little breathing room.
- Band-path endpoint labels must remain at their physical positions. When they
  coincide with plot boundaries, suppress their tick strokes while retaining the
  labels; do not shift the path coordinates to satisfy the corner rule.
- Data dominate; physical reference lines are secondary; path separators and
  grids are lighter. Use grids only where they aid reading, usually on one axis.
- Convergence plots use the highest-precision valid completed calculation under
  otherwise consistent settings as the reference (e.g. densest k mesh or highest
  cutoff), not the lowest energy. State the reference and normalization explicitly.
  Preserve signed differences by default; label absolute errors if requested.
  A finite reference does not itself prove convergence.
- Keep element/orbital/spin colors and comparison scales consistent across panels.
  Use colorblind-distinguishable categories, sequential maps for scalar magnitudes,
  and zero-centered diverging maps for signed quantities; avoid rainbow maps.
- Keep energy zeros, units, projection normalization and colorbar ranges aligned
  in comparison figures. Record any smoothing, broadening or interpolation;
  aesthetic changes must not conceal crossings, peaks or imaginary frequencies.

## Export and visual acceptance

Open the rendered output before delivery. Inspect label/tick/legend/colorbar
overlap, corner ticks, clipped markers, margins, panel proportions and legibility
at intended size. Re-render until these pass; successful execution alone is not
visual acceptance. Record font fallback and layout/reference choices briefly.
For dispersion curves, also inspect the sample-only companion required by the
plot catalog. Existing templates may need adaptation to meet these requirements;
their availability does not establish compliance.

## Axis-range planning gate

Every final figure must receive both explicit ranges:

```text
--xlim XMIN XMAX --ylim YMIN YMAX
```

The limits must be increasing, physically justified, and recorded in the
analysis report (for example, energy window around the Fermi level, full
phonon-frequency range, or a declared profile interval). The plotting script
rejects omitted or invalid limits; automatic scaling is for exploratory viewing
only and must not be promoted to a final figure.

Example:

```bash
python dftplot_plot.py dos \
  --dat analysis/plot_data/dos_total.dat \
  --output analysis/figures/dos_total \
  --xlim -3 12 --ylim 0 25
```
