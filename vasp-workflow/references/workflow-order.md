# Workflow Order

Use this calculation order unless the user explicitly approves another
scientific dependency:

```text
structure -> test -> relax -> electronic/scf -> downstream electronic/phonon -> analysis -> manager archive/records
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
- Continue an unconverged relax by copying the latest `CONTCAR` to `POSCAR`
  only when the run finished without requiring scientific-parameter changes and
  the approved review envelope allows continuation. Before each continuation,
  preserve that attempt's `OUTCAR` and `CONTCAR` under
  `relax/recovery_attempts/attempt-N/`.
- A relaxed structure is ready for SCF only after `vwf parse` or equivalent
  review reports ionic convergence. A final relax that needs only one ionic step
  is a useful practical sign, but it is not a substitute for the convergence
  verdict.
- `electronic/scf/`: static calculation after relax. It provides total energy
  and reusable `CHGCAR`/`WAVECAR` for band, DOS, pCOHP, ELF, charge density,
  spin density, PARCHG, LOCPOT, Bader, optics, and Wannier tasks.
- Downstream electronic tasks should inherit the reviewed SCF-compatible INCAR
  envelope and only override parameters that were listed before production
  began. Reuse SCF `CHGCAR` and `WAVECAR` with `ln -s`; do not duplicate them
  with file copies.
- The standard helper automatically symlinks existing `electronic/scf/CHGCAR`
  and `electronic/scf/WAVECAR` into `prepare band` and `prepare dos` outputs
  unless an explicit `--stage-from` destination overrides that file.
- `phonon/`: use the optimized relaxed structure unless the user explicitly
  requests a non-relaxed or constrained reference.
- `analysis/`: extract `.dat` data, figures, and reports with `vasp-analysis`
  directly under the source case. On clusters, do not create a parallel
  `raw_data/` tree for these products.
- Register/archive with `vasp-work-manager` after results, plot data, figures,
  reports, and review files are ready; summarize their paths and conclusions in
  the cluster project `docs/project_summary.md`.

Before preparing a child task, state the upstream source explicitly: original
`POSCAR`, relaxed `CONTCAR`, SCF `CHGCAR`/`WAVECAR`, or phonopy displacement.
Record the path and hash in `task_spec.json` or the submit review.
