# Directory Layout

Create every material or configuration under one case root:

```text
<case-root>/
  structure/
    POSCAR.initial
    metadata.json
  test/
    encut/
    kpoints/
    sigma/
    potcar/
    notes/
  relax/
  energy/
  electronic/
    scf/
    band/
    dos/
    fatband/
    pcohp/
    elf/
    chgdiff/
    spin-density/
    parchg/
    locpot/
    bader/
    optics/
    wannier/
  phonon/
    fd/
    dfpt/
    gamma/
    unfolded/
    thermal/
  analysis/
    plot_data/
    figures/
    reports/
  automation/
    workflow_plan.json
    automation.log
  workflow.json
```

Use `task_spec.json` in each task directory to record:

- task kind and calculation intent,
- workflow stage and upstream dependency,
- source structure and input hashes,
- dependency path, such as relax or SCF,
- cluster profile and Slurm resource envelope,
- submit script path and job id when known,
- notes about user-approved scientific parameters.

Use `test/` only for convergence or sensitivity scans. Once a production
parameter set is selected, record the chosen values and then prepare `relax/`.
Do not feed `test/` outputs into downstream production tasks unless the user
explicitly promotes a specific result.

Use `relax/` as the source of optimized structures. Production SCF and phonon
tasks should point at a specific relaxed `CONTCAR` and record its hash.

Use `electronic/scf/` for the static calculation that produces final energy,
`WAVECAR`, and `CHGCAR` for downstream electronic analysis.

Do not infer that the latest-looking directory is safe to use. Check the
dependency recorded in `task_spec.json` or ask the user when the source cannot
be established from files.
