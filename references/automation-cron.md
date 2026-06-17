# Automation And Cron

Current behavior: `vasp-workflow` does not automatically submit SCF, band, DOS,
phonon, or analysis tasks after relax unless an automation plan is installed and
approved. Without automation, an Agent or user must detect completion, prepare
the next task, generate review, get approval, and submit.

Preferred production behavior: use a workflow-level automation plan so a small
cron-driven tick script can monitor Slurm and hand off stages without Agent
intervention. The Agent's job becomes audit, repair, and scientific review.

## Safety Model

- Approve the dependency graph before automation starts.
- Approve scientific parameters, POTCAR choices, structure sources, and resource
  envelopes before the first automated submit.
- Each stage still needs `submission_review.dat` and
  `submission_approval.json`; cron may only submit when the approval matches the
  current stage files.
- Derived inputs must stay inside the approved envelope. Example: SCF may use
  `relax/CONTCAR`; phonon FD may use the same approved relaxed structure. Declare
  such derivations with a stage's `inputs_from` (see "Input Staging Between
  Stages") so they are materialized automatically and on the record. If a hash,
  path, POTCAR choice, KPOINTS, INCAR, node count, or command changes outside
  these declared derivations, automation must block.
- Recovery actions must stay inside the approved envelope and respect
  `max_retries`. See `error-recovery.md`.
- `test/` outputs are not production dependencies unless explicitly promoted by
  the user.

## Plan Shape

Use:

```bash
python -m vwf automation init --case-root ./SiC
```

This creates `automation/workflow_plan.json`. Edit it so stages describe the
actual case, for example:

```json
{
  "auto_submit": true,
  "stages": [
    {
      "name": "relax",
      "depends_on": [],
      "path": "relax",
      "status": "ready",
      "submit_command": "sbatch job.sh",
      "review_file": "submission_review.dat",
      "approval_file": "submission_approval.json",
      "completion_files": ["CONTCAR", "OUTCAR"],
      "require_convergence": true,
      "detect_failure_from_parse": true,
      "auto_recover": false,
      "max_retries": 0,
      "recovery_command": ""
    },
    {
      "name": "scf",
      "depends_on": ["relax"],
      "path": "electronic/scf",
      "status": "planned",
      "submit_command": "sbatch job.sh",
      "review_file": "submission_review.dat",
      "approval_file": "submission_approval.json",
      "inputs_from": [{"stage": "relax", "file": "CONTCAR", "to": "POSCAR"}],
      "completion_files": ["OUTCAR", "CHGCAR"],
      "require_convergence": true,
      "detect_failure_from_parse": true,
      "auto_recover": false,
      "max_retries": 0,
      "recovery_command": ""
    }
  ]
}
```

## Completion Is Judged By Convergence, Not Exit Code

A run that terminates normally but never reaches accuracy is **not** done. The
tick uses `vwf parse` (the same parser as the `parse` command) to read the
scientific outcome:

- `completion_files` is only an existence gate so a half-written run is not
  parsed. It does not, by itself, mean the stage is complete.
- `require_convergence: true` makes a stage reach `done` only when
  `vwf parse` reports `converged: true` (ionic convergence for a relax;
  electronic convergence for an `NSW=0`/`IBRION=-1` static run).
- `detect_failure_from_parse: true` marks a stage `failed` when the parser finds
  a real crash (`error_type`, e.g. `ZBRENT_FAILED`) or a run that finished
  cleanly yet did **not** converge. A still-running job has neither, so it is
  not falsely failed.

Omit both flags to fall back to the legacy file/text-only behavior. Inspect any
stage directly with `python -m vwf parse --task-dir <stage path>`.

Status meanings:

- `planned`: waiting for dependencies.
- `ready`: dependencies are done and approval exists; eligible for submit.
- `submitted` or `running`: Slurm job id is known.
- `done`: completion files exist and (if `require_convergence`) the run
  converged.
- `failed`: a failure marker, an explicit failed state, or a parsed
  crash/non-converged terminal result.
- `blocked`: the job left Slurm but completion criteria are not satisfied, or
  approval/review is missing.

## Recovery

When `auto_recover=true` (plan and stage) and `retry_count < max_retries`, the
tick attempts one recovery per failed/blocked stage. There are two strategies,
selected by the stage's `recovery_strategy`:

- `"classify"` (default when no `recovery_command` is set): the built-in engine
  reads the parsed error (`vwf parse`) and picks **one envelope-safe action**.
  It never edits scientific parameters; anything that would require a scientific
  or resource change is turned into `block` with a recommendation for the human.

  | Parsed condition | Action |
  |---|---|
  | `ZBRENT_FAILED` (CONTCAR present) | `restart_from_contcar` (continue relaxation) |
  | `TIME_LIMIT` (CONTCAR present / absent) | `restart_from_contcar` / `resubmit` |
  | `CHGCAR_READ_FAILED` (declared CHGCAR source) | `restage_inputs` (re-pull CHGCAR) |
  | ionic relaxation not converged (CONTCAR present) | `restart_from_contcar` |
  | `OUT_OF_MEMORY`, `COMMAND_NOT_FOUND`, `ZHEGV_FAILED`, `LAPACK_ERROR`, electronic non-convergence | `block` (needs review) |

  Restrict the permitted actions per stage with
  `"recovery_actions": ["restart_from_contcar", "resubmit"]`; a chosen action
  outside the list is downgraded to `block`. Before each retry the prior
  `OUTCAR/OSZICAR/vasp.out/vasp.err` are moved into
  `recovery_attempts/attempt-N/` so the next run is judged on its own results.

- `"command"` (default when `recovery_command` is set): the tick runs your
  `recovery_command` verbatim in the stage directory and returns it to `ready`
  on exit 0, else `blocked`. Keep it conservative (custodian/pymatgen
  diagnostics, copy approved restart files, regenerate a job script from
  approved settings). Do not let it alter scientific inputs outside review.

Either way, recovery respects `max_retries`; once reached the stage stays
`blocked` for the human. Recovery never bypasses the per-stage approval gate —
a recovered stage still needs its approval to be auto-submitted.

## Input Staging Between Stages

A stage may declare `inputs_from` to pull a converged upstream output into its
own inputs. The tick performs the copy when the dependency reaches `done`
(which, with `require_convergence`, means the upstream actually converged), just
before the stage becomes `ready`:

```json
"inputs_from": [
  {"stage": "relax", "file": "CONTCAR", "to": "POSCAR"},
  {"stage": "scf",   "file": "CHGCAR",  "link": true},
  {"stage": "scf",   "file": "WAVECAR", "link": true, "optional": true}
]
```

- `to` defaults to `file`; use it to rename (CONTCAR -> POSCAR).
- `link: true` symlinks instead of copying — prefer it for large files such as
  CHGCAR/WAVECAR so they are not duplicated.
- `optional: true` skips a missing source silently; otherwise a missing required
  source blocks the stage (`required staged input missing: ...`).
- Staging is idempotent (a destination already matching the source is left
  untouched) and records provenance in `staged_inputs.json` inside the stage.

These derivations are part of the approved envelope (see the Safety Model:
"SCF may use relax/CONTCAR"), so staging does **not** invalidate a stage's
review/approval — it only materializes inputs the dependency graph already
declared. It will not run until the upstream stage has converged.

## Cron

After reviewing the generated command, install it manually with `crontab -e`:

```bash
python -m vwf automation cron-line --case-root ./SiC --interval-minutes 10
```

The cron entry should run on a login node where `squeue`, `sbatch`, modules, and
the case path are available. Keep the tick interval conservative, usually 5-15
minutes. Do not run VASP itself from cron; cron only polls and submits Slurm
jobs.

Test safely first:

```bash
python -m vwf automation tick --case-root ./SiC --dry-run
```

Then run one live tick manually before relying on cron:

```bash
python -m vwf automation tick --case-root ./SiC
```
