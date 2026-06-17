---
name: vasp-analysis
description: Extract, validate, plot, and interpret VASP post-processing data. Use when converting VASP, phonopy, LOBSTER, PyProcar, VASPKIT, CHGCAR/ELFCAR/PARCHG, DOSCAR, EIGENVAL, PROCAR, band.yaml, total_dos.dat, COHPCAR, ICOHPLIST, or notebook outputs into plot-ready .dat files, figures, analysis reports, and next-step recommendations without submitting new calculations.
---

# VASP Analysis

## Overview

Use this skill after calculation outputs exist. The core product is reusable
plot-ready `.dat` data, then figures, then interpretation reports. JSON is only
for metadata such as `plot_manifest.json`.

Use `vasp-workflow` to prepare or submit calculations. Use `vasp-work-manager`
to archive completed tasks, plot data, figures, and reports.

## Required First Steps

1. For any numeric plot data, read `references/data-contract.md`; write `.dat`
   first, then PNG/PDF figures.
2. Before drawing figures, read `references/plot-style.md`; use the bundled
   plotting templates unless the user explicitly asks for a different style.
3. For DOS, band, phonon, pCOHP, ELF, CHGDIFF, spin density, PARCHG, or similar
   plots, read `references/plot-catalog.md`.
4. For report writing or next-step recommendations, read
   `references/report-format.md`.
5. Do not submit VASP jobs from this skill. If analysis suggests a new
   calculation, write a next-task description for `vasp-workflow`.

## Operating Rules

- Preserve source provenance in `.dat` comment headers.
- Prefer one table per physical curve family, such as `dos_total.dat`,
  `phonon_band.dat`, `chgdiff_z.dat`, or `pcohp_selected_bonds.dat`.
- Keep units and column names explicit.
- Keep plot-ready arrays parseable with plain whitespace splitting.
- Do not store primary numeric plot data only in `.json`, notebook output, or a
  PNG. JSON may describe metadata, not replace `.dat`.
- When optional tools are missing, report the missing dependency and the source
  files needed to rerun extraction.

## Data Validator

Use the bundled validator before archiving or reporting:

```bash
SKILL=/Users/gyro/Library/CloudStorage/SynologyDrive-note-sync/project/coding/skillhub/vasp-analysis
python "$SKILL/scripts/vaplot_dat.py" validate analysis/plot_data/dos_total.dat
```

Expected `.dat` header:

```text
# vaplot_dat_version = 1
# source = /path/to/source
# units = energy:eV dos:states/eV
# columns = energy_eV total_dos C_pdos Si_pdos
```

## Plot Templates

Use the bundled template plotter for consistent notebook-style figures:

```bash
python "$SKILL/scripts/vaplot_plot.py" dos \
  --dat analysis/plot_data/dos_total.dat \
  --output analysis/figures/dos_total \
  --title "DOS" \
  --window -3 12

python "$SKILL/scripts/vaplot_plot.py" band \
  --dat analysis/plot_data/band.dat \
  --output analysis/figures/band \
  --title "Band Structure" \
  --window -3 3

python "$SKILL/scripts/vaplot_plot.py" profile \
  --dat analysis/plot_data/chgdiff_z.dat \
  --output analysis/figures/chgdiff_z \
  --x-label "z (Angstrom)" \
  --y-label "Charge density difference"
```

## Reference Map

- `references/data-contract.md`: `.dat` header, numeric row, units, and
  validator expectations.
- `references/plot-style.md`: fixed notebook-style plotting parameters.
- `references/plot-catalog.md`: supported and planned plot families.
- `references/report-format.md`: report outputs and next-step recommendation
  boundary.
