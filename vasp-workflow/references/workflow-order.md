# Workflow Order

Use this calculation order unless the user explicitly approves another
scientific dependency:

```text
structure -> test -> relax -> electronic/scf -> downstream electronic/phonon -> analysis -> archive
```

- `structure/`: original, researched, or generated structure. If the user only
  gives a formula/material name or is unsure of the phase, follow
  `structure-research.md` before writing `POSCAR.initial`. Confirm lattice
  constants, coordinate mode, fixed atoms/selective dynamics, element counts,
  and atom ordering.
- `test/`: parameter exploration only, such as ENCUT, KPOINTS, SIGMA, smearing,
  and POTCAR comparisons. Do not use test outputs as production inputs unless
  the user explicitly promotes one result.
- `relax/`: production optimized geometry. Downstream SCF and phonon tasks
  normally use the approved relaxed `CONTCAR`.
- `electronic/scf/`: static calculation after relax. It provides total energy
  and reusable `CHGCAR`/`WAVECAR` for band, DOS, pCOHP, ELF, charge density,
  spin density, PARCHG, LOCPOT, Bader, optics, and Wannier tasks.
- `phonon/`: use the optimized relaxed structure unless the user explicitly
  requests a non-relaxed or constrained reference.
- `analysis/`: extract `.dat` data and figures with `vasp-analysis`.
- archive with `vasp-work-manager` after results, plot data, figures, and review
  files are ready.

Before preparing a child task, state the upstream source explicitly: original
`POSCAR`, relaxed `CONTCAR`, SCF `CHGCAR`/`WAVECAR`, or phonopy displacement.
Record the path and hash in `task_spec.json` or the submit review.
