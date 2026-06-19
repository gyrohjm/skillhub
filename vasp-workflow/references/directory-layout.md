# Directory Layout

Use two directory levels:

1. A research project root created by `init-research-project`.
2. A VASP case root for one material/configuration/calculation case.

On nmg/Phoenix, default cluster case roots are:

```text
/home/jmhe/project/<project_slug>/calculations/<system_slug>/<case_slug>
```

For new cases that will be registered and archived by `vasp-work-manager`, use
the managed project-root convention explicitly:

```text
/home/<user>/projects/<project_slug>/calculations/<system_slug>/<case_slug>
```

`project_slug`, `system_slug`, and `case_slug` must be English
`lowercase_snake_case`. Use `--case-root` for an explicit path, or pass
`--cluster nmg|phoenix|generic --project-slug <project> --system-slug <system>
--case-slug <case>` and let the helper derive the default path.

When syncing results back to a local research project, preserve raw calculation
files under:

```text
raw_data/calculations/<system_slug>/<case_slug>/
```

Copy structures to `formal_data/structures/<system_slug>/` only after explicit
user approval.

The local `raw_data/formal_data` lifecycle does not apply as a second directory
tree on the cluster. In a cluster case, keep raw calculation files in their
task directories and run post-processing in the existing case-local tree:

```text
<case-root>/analysis/plot_data/
<case-root>/analysis/figures/
<case-root>/analysis/reports/
```

Do not create `<cluster-project>/raw_data/`. Summarize case/report/figure paths
and key conclusions at `<cluster-project>/docs/project_summary.md` through
`vasp-work-manager`.

Create every material or configuration under one case root:

```text
<case-root>/
  structure/
    POSCAR.initial
    metadata.json
    candidates.dat
    source.cif
  test/
    encut/
    kpoints/
    sigma/
    potcar/
    notes/
  relax/
    POSCAR
    POSCAR-ini
    CONTCAR
    recovery_attempts/
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
    review_queue.dat
    review_queue.jsonl
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

Under `structure/`, keep `metadata.json` for provenance. When a structure was
researched from databases or literature, `candidates.dat` should record the
candidate comparison and `source.cif` (or another source file) may be kept when
licensing allows.

Treat `structure/POSCAR.initial` as the reviewed pre-relax structure. Treat
`relax/CONTCAR` as the optimized structure only after relaxation is converged
and reviewed.
For every prepared relax task, keep `relax/POSCAR-ini` as a copy of the initial
approved structure. Do not overwrite it during continuation; it is the fallback
when the relaxation scatters or needs a clean restart.

Use `test/` only for convergence or sensitivity scans. Once a production
parameter set is selected, record the chosen values and then prepare `relax/`.
Do not feed `test/` outputs into downstream production tasks unless the user
explicitly promotes a specific result.

Use `relax/` as the source of optimized structures. Production SCF and phonon
tasks should point at a specific relaxed `CONTCAR` and record its hash.
If relax reaches the maximum ionic steps without converging, preserve the
attempt's `OUTCAR` and `CONTCAR` under `relax/recovery_attempts/attempt-N/`,
then continue by copying that `CONTCAR` to `POSCAR` only inside the approved
recovery envelope.

Use `electronic/scf/` for the static calculation that produces final energy,
`WAVECAR`, and `CHGCAR` for downstream electronic analysis. Downstream
electronic directories should reuse SCF `CHGCAR` and `WAVECAR` with symbolic
links, not copied files.

Use standard stage task directories (`relax/`, `electronic/scf`,
`electronic/band`, `electronic/dos`) as ordinary VASP run folders containing
`POSCAR`, `INCAR`, `KPOINTS`, `POTCAR`, `job.sh`, `task_spec.json`,
`submission_review.dat`, and `submission_approval.json`.

Do not infer that the latest-looking directory is safe to use. Check the
dependency recorded in `task_spec.json` or ask the user when the source cannot
be established from files.
