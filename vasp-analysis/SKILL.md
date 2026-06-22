---
name: vasp-analysis
description: Process and analyze completed VASP outputs by extracting validated plot-ready .dat files, generating figures, evaluating approved observables, writing interpretation reports, and proposing versioned computation-design changes without submitting jobs. Use when converting VASP, phonopy, LOBSTER, PyProcar, VASPKIT, CHGCAR/ELFCAR/PARCHG, DOSCAR, EIGENVAL, PROCAR, band.yaml, total_dos.dat, COHPCAR, ICOHPLIST, or notebook outputs into reusable data products. Do not create tasks or archive ledgers; hand design revisions, execution, and records to computation-design, vasp-workflow, and vasp-work-manager.
---

# VASP Analysis

## Overview

Use this skill after calculation outputs exist. The core product is reusable
plot-ready `.dat` data, then figures, then interpretation reports. JSON is only
for metadata such as `plot_manifest.json`.

Use `computation-design` to revise the scientific calculation matrix. Use
`vasp-workflow` to prepare or submit approved calculations. Use
`vasp-work-manager` to register/archive completed tasks, plot data, figures,
and reports.

## Skill Boundary

- Owns: extraction from completed outputs, `.dat` data contracts, validation,
  plotting, report writing, interpretation, uncertainty notes, and next-task
  recommendations.
- Does not own: creating or submitting VASP tasks, changing calculation inputs,
  workflow automation, durable archive manifests/checksums, ledger records, or
  cleanup decisions.
- Handoff: send proposed new calculations to `computation-design` as a
  versioned design change request; send completed outputs, `.dat` files,
  figures, and reports to `vasp-work-manager` for registration, archiving, and
  verification.

## Required First Steps

1. For any numeric plot data, read `references/data-contract.md`; write `.dat`
   first, then PNG/PDF figures.
2. Before drawing figures, read `references/plot-style.md`; use the bundled
   plotting templates unless the user explicitly asks for a different style.
3. For DOS, band, phonon, pCOHP, ELF, CHGDIFF, spin density, PARCHG, or similar
   plots, read `references/plot-catalog.md`.
4. For report writing or next-step recommendations, read
   `references/report-format.md`.
5. When an approved design snapshot exists, compare results with its observable
   decision rules and report `supported`, `falsified`, or `inconclusive`.
6. Do not submit VASP jobs from this skill. If analysis suggests a new
   calculation, write `analysis/reports/design_change_request.json` for
   `computation-design`; do not send an unreviewed task directly to workflow.

## Operating Rules

- On clusters, work in the source calculation case. Write outputs under
  `<case_root>/analysis/plot_data`, `<case_root>/analysis/figures`, and
  `<case_root>/analysis/reports`; do not create or populate cluster-side
  `raw_data/` or `formal_data/` directories.
- Preserve source provenance in `.dat` comment headers.
- Prefer one table per physical curve family, such as `dos_total.dat`,
  `phonon_band.dat`, `chgdiff_z.dat`, or `pcohp_selected_bonds.dat`.
- Keep units and column names explicit.
- Keep plot-ready arrays parseable with plain whitespace splitting.
- Do not store primary numeric plot data only in `.json`, notebook output, or a
  PNG. JSON may describe metadata, not replace `.dat`.
- Do not register tasks, write archive manifests, verify archive checksums, or
  decide cleanup. Produce the data/report paths and hand them to
  `vasp-work-manager`.
- Keep project-level reporting concise: write the detailed case report under
  the case `analysis/reports/` directory, then provide paths, validation state,
  and key conclusions for `vasp-work-manager` to add to
  `<project_root>/docs/project_summary.md`.
- When optional tools are missing, report the missing dependency and the source
  files needed to rerun extraction.
- Treat recommended calculations as proposed scientific changes. They require a
  new `computation-design` revision and approval before `vasp-workflow` may
  prepare them as production tasks.

## Data Validator

Use the bundled validator before reporting or handing data to
`vasp-work-manager`:

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

Create a provenance-linked design change request when evidence requires a new
calculation:

```bash
python "$SKILL/scripts/design_change_request.py" \
  --case-root <case_root> \
  --verdict inconclusive \
  --trigger "decision threshold not resolved" \
  --proposed-change "add a denser convergence point" \
  --scientific-reason "current uncertainty overlaps the effect" \
  --evidence <case_root>/analysis/plot_data/result.dat
```

## Reference Map

- `references/data-contract.md`: `.dat` header, numeric row, units, and
  validator expectations.
- `references/plot-style.md`: fixed notebook-style plotting parameters.
- `references/plot-catalog.md`: supported and planned plot families.
- `references/report-format.md`: report outputs and next-step recommendation
  boundary.
