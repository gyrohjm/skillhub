# Plot Catalog

Prioritize DOS and PDOS first, then expand by source family.

## Electronic

- DOS/PDOS: `DOSCAR`, `vasprun.xml`, VASPKIT outputs, or cached `.dat`.
- Band: `EIGENVAL`, `OUTCAR`, `KPOINTS`, `REFORMATTED_BAND.dat`, `KLABELS`.
- Fatband/projected band: `PROCAR`, `PBAND_*.dat`, PyProcar/VASPKIT outputs.
- pCOHP/COBI/COOP: LOBSTER `COHPCAR`, `ICOHPLIST`, `lobsterout`.
- ELF: `ELFCAR` slices or line profiles.
- Charge density difference: `CHGCAR`/`CHG` difference and z distribution.
- Spin density: spin-polarized `CHGCAR` or magnetization grids.
- PARCHG: selected band/charge slices and profiles.
- LOCPOT/work function: extract vacuum potential profiles and write
  `work_function.dat`.
- Bader: write atom-indexed `bader_charge.dat`.
- Defect/surface/interface energies: write formation, surface, adsorption, or
  interface energy `.dat` tables from validated reference totals.
- Optical, Wannier, and electronic unfolding are supported as later templates.

## Phonon

- Phonon band/DOS: phonopy `band.yaml`, `total_dos.dat`, `projected_dos.dat`.
- FD post-processing should preserve displacement mapping and force sources.
- Phonon unfolding should consume external spectral-weight `.dat` from tools
  such as upho/KPROJ/VASPKIT rather than reimplementing the unfolding algorithm
  in the first version.

## Style

Match the existing notebook language from `extend_demo`: white background,
large readable labels, visible Fermi/zero-frequency guides, PNG and PDF output,
and `.dat` saved beside every figure.

Use `scripts/dftplot_plot.py` templates. Every final invocation must provide
both `--xlim XMIN XMAX` and `--ylim YMIN YMAX`; choose ranges from the data and
record the reason in the report:

```text
dos          energy on x, DOS on y, red EF line at x=0
band         k-distance on x, energy on y, red EF line at y=0
phonon-band  q-distance on x, frequency on y, red zero-frequency line
phonon-dos   frequency on x, phonon DOS on y
profile      x/profile plots for CHGDIFF z, spin z, ELF line, etc.
cohp         pCOHP/COHP on x, energy on y, red EF and x=0 guide
heatmap      x/y/value slice plots for ELF, PARCHG, spin density, CHGDIFF
```

Use the templates as starting points; adapt and inspect their output against
`references/plot-style.md`, including proportional fonts, external legends and
boundary ticks. Do not assume a template implements every rule.

## Dispersion curves: paired deliverables

Electronic bands, projected bands and phonon dispersions require two exports
from the same data and with identical energy/frequency reference, axes, path,
colors and projection normalization:

- `<name>_lines.png/.pdf`: the connected presentation view.
- `<name>_samples.png/.pdf`: original supplied sampling points only, with
  no connecting lines, spline smoothing, resampling or added interpolation.

Use modest, readable markers for the sample-only view; preserve projection
weights for projected bands. Separate discontinuous path segments in both
views. Default connections follow adjacent samples within each segment, not
an invented band-tracking scheme. Inspect suspicious crossings against the
sample-only view; it reveals plotting artifacts but does not prove connectivity.
If supplied energies already come from Wannier or force-constant interpolation,
state that provenance: “sample-only” removes plotting interpolation, not the
upstream physical interpolation. Never label them direct DFT points.

## Figure-specific composition

| Figure | Composition and evidence requirements |
| --- | --- |
| Band | Neutral base bands; subtle high-symmetry separators; clear energy zero. Use physical path distances, preserve path breaks, and combine repeated boundary labels where appropriate. |
| DOS / PDOS | Dark total DOS; fixed element/orbital colors; light optional fill. Separate crowded components into panels. State states/eV normalization per cell, atom or spin. |
| Spin DOS | Use a consistent channel convention; if mirrored, explain that negative values indicate a spin channel. Match scales between channels. |
| Band–DOS / phonon–DOS | Share the vertical energy/frequency axis and bounds, align panel heights, and reserve a narrower DOS panel without squeezing its labels or legend. |
| Projected band | Light underlying bands; explicit marker-size legend or colorbar for weights; consistent scales across panels. Use separate panels when projections obscure one another. |
| Phonon dispersion | Retain negative frequencies and document the imaginary-mode convention. Keep the zero guide visible and linewidths thin enough to resolve acoustic branches. Supply both dispersion variants above. |
| Brillouin zone | Preserve Cartesian reciprocal-space geometry and equal spatial scale; prefer orthographic projection. Use light edges, emphasized paths, separated labels and defined reciprocal axes. |
| Fermi surface | Record energy, coordinate system and view. Match camera, scale and color meaning across comparisons; keep BZ edges light and avoid transparency that confuses front/back pockets. Use multiple views or separate sheets where needed. State meshing/interpolation provenance. |

Three-dimensional BZ and Fermi-surface views use explicit spatial bounds and
camera settings instead of a two-dimensional energy-window convention. Preserve
geometry when laying out legends, axes and colorbars.
