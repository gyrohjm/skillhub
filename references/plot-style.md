# Plot Style

Match the user's existing Jupyter notebook style from `extend_demo`.

Default constants:

```text
SAVE_DPI = 600
FIG_SIZE = 10, 6
BAND_FIG_SIZE = 8, 10
FONT_SIZE = 24
AXIS_LABEL_SIZE = 28
TITLE_SIZE = 30
TICK_SIZE = 28
LEGEND_SIZE = 24
LINE_WIDTH = 2.5
REFERENCE_LINEWIDTH = 2.0
FERMI_COLOR = red
REFERENCE_COLOR = #9E9E9E
TOTAL_COLOR = black
GRID_ALPHA = 0.30
FILL_ALPHA = 0.22
REFERENCE_ALPHA = 0.28
SPINE_WIDTH = 1.5
```

Rules:

- Use white figure background.
- Prefer Arial; allow matplotlib fallback when Arial is unavailable.
- Use bold axis labels and bold titles.
- Use red dashed Fermi or zero-reference guides.
- Use dashed grid with alpha 0.30.
- Save both `.png` and `.pdf`.
- Write figures atomically from memory to avoid partial files on synced folders.
- Keep the `.dat` used to draw the figure beside or near the figure.
