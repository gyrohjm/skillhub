# VASP Skill Contract

Use these ownership boundaries. In short, `vasp-workflow` owns the
running/orchestration layer, `vasp-work-manager` owns the records/archive layer,
and `vasp-analysis` owns completed-output scientific analysis.

| Skill | Owns | Must not do | Handoff |
|---|---|---|---|
| `vasp-workflow` | Running/orchestration: case trees, task directories, `POSCAR`/`INCAR`/`KPOINTS`/`POTCAR`/`job.sh`, `task_spec.json`, `state.json`, `submission_review.dat`, submit/queue logs, dependency handoff, bounded recovery, cron/watch plans. | Long-term archive ledger, cleanup decisions, plot extraction, figures, interpretation reports. | Completed/failed task records go to `vasp-work-manager`; completed-output analysis goes to `vasp-analysis`. |
| `vasp-work-manager` | Records/archive: import/register existing tasks into the lightweight ledger, write notes/review status/events, create immutable archive versions, manifests, `SHA256SUMS`, file records, project summaries, reports, and verification results. | Generate or change VASP scientific inputs, submit/recover jobs, call cluster resources, parse data into new scientific `.dat` arrays, interpret physical meaning. | Missing or invalid task setup goes to `vasp-workflow`; missing plot data or interpretation goes to `vasp-analysis`. |
| `vasp-analysis` | Data processing and analysis: extract validated plot-ready `.dat`, create figures, write reports, interpret completed outputs, and propose next calculations. | Submit jobs, mutate calculation inputs, register ledger records, decide archive retention or cleanup. | New calculations go to `vasp-workflow`; durable preservation of outputs/reports goes to `vasp-work-manager`. |

Do not let one skill silently cross into another skill's ownership. It is fine
to write a handoff note, next-task block, or archive request, but the receiving
skill owns the actual action.

For managed cluster records, `vasp-work-manager` requires one short English
project directory before system/case directories:

```text
/home/<user>/projects/<project_slug>/
  calculations/<system_slug>/<case_slug>/
  archive/<system_slug>/<case_slug>/<timestamp>Z/
  ledger/vwm.sqlite
  docs/project_summary.md
```

If the local project name is Chinese, translate it to concise English
`lowercase_snake_case` before creating the cluster project root.

Do not create cluster-side `raw_data/` or `formal_data/`. Keep post-processing
inside each source case under `analysis/plot_data`, `analysis/figures`, and
`analysis/reports`. The project-level document only summarizes task state,
paths, and conclusions; it does not duplicate raw or processed arrays.

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
