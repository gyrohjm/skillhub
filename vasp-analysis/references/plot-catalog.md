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
- LOCPOT/work function, Bader, optical, Wannier, and electronic unfolding are
  supported as later templates.

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

Use `scripts/vaplot_plot.py` templates:

```text
dos          energy on x, DOS on y, red EF line at x=0
band         k-distance on x, energy on y, red EF line at y=0
phonon-band  q-distance on x, frequency on y, red zero-frequency line
phonon-dos   frequency on x, phonon DOS on y
profile      x/profile plots for CHGDIFF z, spin z, ELF line, etc.
cohp         pCOHP/COHP on x, energy on y, red EF and x=0 guide
heatmap      x/y/value slice plots for ELF, PARCHG, spin density, CHGDIFF
```

These templates enforce the house style; custom matplotlib code should call the
same style helpers or match `references/plot-style.md`.
