# Optional Automation And Cron

Use this reference only when the user explicitly asks for automatic handoff,
cron polling, or bounded retry behavior. Automation is a helper path, not the
core value of this skill.

Current behavior: `vasp-workflow` can prepare standard relax, SCF, band, and DOS
stage directories, and can run a small cron/watch state machine when an
automation plan is installed and approved. Without automation, an Agent or user
detects completion, prepares/reviews the next task, gets approval, and submits.

Use automation only after the workflow order, stage inputs, scientific
parameters, POTCAR choices, and resource envelopes have already been reviewed.
The Agent's job remains audit, repair, and scientific review; cron only polls
and submits approved stages.

## Safety Model

- Approve the dependency graph before automation starts.
- Approve the relevant calculation-matrix scope with `computation-design` and
  preserve its provenance in each production stage. Automation blocks a stage
  whose `task_spec.json`/`state.json` is exploratory or untracked.
- Approve scientific parameters, POTCAR choices, structure sources, and resource
  envelopes before the first automated submit.
- Built-in relax defaults may be prefilled (`EDIFF=1E-6`, `EDIFFG=-0.01`,
  `NSW=80`), but they are still part of the reviewed envelope.
- Built-in SCF defaults may be prefilled with `EDIFF=1E-7`, `IBRION=-1`, and
  `NSW=0`, but they are still part of the reviewed envelope.
- General relax automation does not use a convergence ladder by default. It
  must keep relax `EDIFF=1E-6` and `EDIFFG=-0.01` unless the review envelope
  explicitly approves a different value.
- Each stage still needs `submission_review.dat`. Cron may submit only when
  either the stage has a matching `submission_approval.json` or the stage is
  marked `preapproved_by_workflow: true` because the initial reviewed workflow
  envelope already fixed its scientific parameters and resources.
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
      "preapproved_by_workflow": false,
      "completion_files": ["CONTCAR", "OUTCAR"],
      "incar_defaults": {
        "EDIFF": "1E-6",
        "EDIFFG": "-0.01",
        "NSW": 80,
        "IBRION": 2,
        "ISIF": 3,
        "ISMEAR": 0,
        "SIGMA": "0.05",
        "PREC": "Accurate",
        "LREAL": ".FALSE."
      },
      "relax_ediff_policy": "fixed at 1E-6 by default; changes require review envelope approval",
      "relax_ediffg_policy": "fixed at -0.01 by default; changes require review envelope approval",
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
      "preapproved_by_workflow": false,
      "inputs_from": [{"stage": "relax", "file": "CONTCAR", "to": "POSCAR"}],
      "completion_files": ["OUTCAR", "CHGCAR"],
      "incar_defaults": {
        "EDIFF": "1E-7",
        "IBRION": -1,
        "NSW": 0,
        "ISIF": 2,
        "ISMEAR": 0,
        "SIGMA": "0.05",
        "PREC": "Accurate",
        "LREAL": ".FALSE.",
        "LWAVE": ".TRUE.",
        "LCHARG": ".TRUE."
      },
      "scf_ediff_policy": "fixed at 1E-7 by default; changes require review envelope approval",
      "require_convergence": true,
      "detect_failure_from_parse": true,
      "auto_recover": false,
      "max_retries": 0,
      "recovery_command": ""
    }
  ]
}
```

Set `preapproved_by_workflow: true` only after the initial project computation
plan has already listed that stage's full effective INCAR inheritance/overrides,
KPOINTS policy, POTCAR labels, structure source, cluster profile, resource
profile, and completion gate. The helper still requires the stage's
`submission_review.dat`, and the current files/resources must match the hashes
recorded in `task_spec.json` or `state.json`. Optional
`workflow_preapproved_review_hash`, `workflow_preapproved_input_hashes`, and
`workflow_preapproved_resource_hash` can pin the envelope more tightly.

For FD phonons, add a taskset stage after preparing it with
`prepare phonon-fd`:

```json
{
  "name": "phonon-fd",
  "kind": "phonon-fd-worker-queue",
  "depends_on": ["relax"],
  "path": "phonon/fd/fd-001",
  "status": "planned",
  "submit_command": "python -m vwf submit workers --taskset ./phonon/fd/fd-001 --approved",
  "review_file": "input/submission_review.dat",
  "approval_file": "input/submission_approval.json"
}
```

The tick treats this kind as complete only when every displacement job is
`done`; it fails when queue jobs enter `failed` and no work remains, or
immediately with `fail_fast: true`.

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
- `ready`: dependencies are done; eligible for submit only when auto-submit
  also finds a matching stage approval or workflow preapproval.
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
  `OUTCAR/OSZICAR/CONTCAR/vasp.out/vasp.err` are moved into
  `recovery_attempts/attempt-N/` so the next run is judged on its own results
  and the unconverged geometry remains available for debugging.

For relax continuations, `CONTCAR -> POSCAR` may be repeated until the parser
reports ionic convergence. Do not mark relax `done` or prepare SCF from
`relax/CONTCAR` until convergence is confirmed. A final one-step continuation is
supporting evidence, not the formal gate.

- `"command"` (default when `recovery_command` is set): the tick runs your
  `recovery_command` verbatim in the stage directory and returns it to `ready`
  on exit 0, else `blocked`. Keep it conservative (custodian/pymatgen
  diagnostics, copy approved restart files, regenerate a job script from
  approved settings). Do not let it alter scientific inputs outside review.

Either way, recovery respects `max_retries`; once reached the stage stays
`blocked` for the human. Recovery never bypasses the submit gate: a recovered
stage still needs either a matching stage approval or valid workflow
preapproval to be auto-submitted.

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
- `link: true` symlinks instead of copying. Use it for SCF `CHGCAR`/`WAVECAR`;
  if the symlink cannot be created, automation blocks instead of falling back to
  a copy.
- `optional: true` skips a missing source silently; otherwise a missing required
  source blocks the stage (`required staged input missing: ...`).
- Staging is idempotent (a destination already matching the source is left
  untouched) and records provenance in `staged_inputs.json` inside the stage.

These derivations are part of the approved envelope (see the Safety Model:
"SCF may use relax/CONTCAR"), so staging does **not** invalidate a stage's
review/approval — it only materializes inputs the dependency graph already
declared. It will not run until the upstream stage has converged.

## Watch Loop

Use `watch` for an interactive blocking run instead of cron:

```bash
python -m vwf automation watch \
  --case-root ./SiC \
  --interval-seconds 300 \
  --max-resubmit 5
```

`watch` calls the same `tick` loop repeatedly, exits `0` when all stages are
`done`, exits `2` on blocked/failed stages, and exits `1` on `--max-cycles`.
Use cron when you want the login node to keep polling after the shell exits.

## Human Review Queue

Whenever a stage becomes `blocked` or `failed`, automation appends a review item
to:

```text
automation/review_queue.dat
automation/review_queue.jsonl
```

Inspect it with:

```bash
python -m vwf automation review --case-root ./SiC
```

Set `notify_command` in `workflow_plan.json` to run a local notification hook.
The command receives `VWF_CASE_ROOT`, `VWF_STAGE`, `VWF_STATUS`, `VWF_REASON`,
and `VWF_STAGE_PATH` in the environment.

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
