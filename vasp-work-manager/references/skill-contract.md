# Skill Contract

Use these handoff boundaries:

- `vasp-workflow` creates calculation directories, tasksets, `task_spec.json`,
  `state.json`, `submission_review.dat`, submit scripts, and queue logs.
- `vasp-work-manager` archives and verifies those files with checksums. It does
  not decide scientific parameters, submit jobs, or interpret results.
- `vasp-analysis` extracts plot-ready `.dat`, creates figures, writes reports,
  and may suggest next tasks. It does not submit jobs.

Archive workflow tasksets with:

```text
state.json
task_spec.json
submission_review.dat
submission_approval.json
queue.log
queue/* markers
workers/*/submit.slurm
jobs/*/POSCAR INCAR KPOINTS POTCAR OUTCAR OSZICAR vasp.out vasp.err
```

Archive analysis outputs with:

```text
analysis/plot_data/*.dat
analysis/plot_data/*.csv
analysis/figures/*.png
analysis/figures/*.pdf
analysis/plot_manifest.json
analysis/reports/*.md
```

Treat `.dat` as the primary numeric plotting format. Keep JSON for state and
manifest metadata.
