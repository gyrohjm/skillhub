# Plot Data Retention

Figures are not enough. Always preserve the data used to draw band, DOS,
fat-band, phonon, pCOHP, ELF, CHGDIFF, spin-density, PARCHG, EOS, convergence,
and charge-density plots.

## Files To Preserve

Keep plot-ready data:

```text
*.dat
*.csv
```

Prefer `.dat` for primary numeric arrays. Keep `.json` for metadata such as
`plot_manifest.json`, `state.json`, or `task_spec.json`, not as the only copy of
numeric plotting data.

Keep final images:

```text
*.png
*.pdf
```

For `vaspmgr plot`, expected outputs include:

```text
band.dat
band.png
band.pdf
dos.dat
dos.png
dos.pdf
band_dos.png
band_dos.pdf
fatband.png
fatband.pdf
phonon_band.png
phonon_band.pdf
phonon_dos.png
phonon_dos.pdf
chgdiff_z.dat
elf_slice.dat
pcohp_selected_bonds.dat
```

The exact prefix may differ, so collect by extension and manifest the paths.

## Inputs That Explain The Plot

When present, preserve the raw files that make the plotted data interpretable:

```text
EIGENVAL
DOSCAR
PROCAR
KLABELS
REFORMATTED_BAND.dat
KPOINTS
POSCAR
OUTCAR
band.yaml
total_dos.dat
projected_dos.dat
COHPCAR.lobster
ICOHPLIST.lobster
lobsterout
```

Do not assume a PNG can be regenerated without these files.

## Collection

On clusters, process and plot directly in the calculation case root:

```text
<case_root>/analysis/plot_data/
<case_root>/analysis/figures/
<case_root>/analysis/reports/
```

Do not create a cluster `raw_data/` tree or duplicate source outputs for
plotting. Analysis files should point back to the original case files through
their provenance headers. The archive script already keeps plot-ready files by
default.

Create a separate plot-only bundle only when the user explicitly needs a
transfer artifact. After a dry-run listing, use ordinary copy commands:

```bash
find /path/to/run -type f \( -name '*.dat' -o -name '*.csv' -o -name '*.json' -o -name '*.png' -o -name '*.pdf' \)
mkdir -p /path/to/plot-data-bundle
rsync -av --include '*/' --include '*.dat' --include '*.csv' --include '*.json' \
  --include '*.png' --include '*.pdf' --exclude '*' \
  /path/to/run/ /path/to/plot-data-bundle/
```

## Notebook-Derived Figures

For figures created from notebooks, keep:

- the exported image,
- the table or array exported to `.dat` or `.csv`,
- metadata exported to `.json` when needed,
- the minimal notebook or script needed to explain transformations when it is
  small enough to be useful.

Do not keep notebook execution caches or unrelated exploratory output in the
archive.

At project level, add only a concise entry to `docs/project_summary.md` with
the case path, report path, key figure paths, validation status, and main
conclusion. Keep numeric arrays in the case `analysis/plot_data/` directory.
