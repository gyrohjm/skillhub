---
name: vasp-workflow
description: Design, prepare, review, and submit VASP calculation workflows on Slurm clusters. Use when creating VASP task directory trees, generating or checking POSCAR/INCAR/KPOINTS/POTCAR/job scripts, preparing relax/energy/electronic/phonon calculations, running finite-displacement phonon worker queues, confirming scientific input provenance before sbatch, selecting nmg/Phoenix/G3 resources, or managing workflow-side task states before archival and analysis.
---

# VASP Workflow

## Overview

Use this skill before calculation results exist. It creates standard VASP
workflow directories, prepares inputs, enforces submit review, installs optional
cron monitoring, and runs dynamic worker queues for batched calculations such
as finite-displacement phonons.

Use `vasp-work-manager` after calculations need archiving or integrity checks.
Use `vasp-analysis` when extracting `.dat` plot data, drawing figures, or
writing interpretation reports.

## Required First Steps

1. For any submit, cancel, overwrite, transfer, or compute action, read
   `references/safe-operations.md`.
2. Before creating a new project tree, read `references/directory-layout.md`.
3. Before preparing relax, energy, electronic, or phonon jobs, read
   `references/calculation-taxonomy.md`.
4. Before submitting anything, read `references/submit-review.md`; every
   `sbatch` must be preceded by explicit review of POSCAR, complete effective
   INCAR, KPOINTS mesh or high-symmetry path, user-approved POTCAR choice, node
   count, task count, worker count, and VASP command.
5. For finite-displacement phonons, read `references/fd-worker-queue.md`.
6. Before configuring automatic stage handoff or cron polling, read
   `references/automation-cron.md`.
7. Before enabling automatic retries or correction, read
   `references/error-recovery.md`.
8. For nmg/Phoenix/G3 profile choices, read `references/cluster-profiles.md`.
   If `references/cluster-profiles.local.md` exists, read it next; it is a
   private, non-committed local cluster snapshot. Recheck live cluster state
   before relying on old resource assumptions.

## Operating Rules

- Follow the workflow order unless the user explicitly approves a different
  scientific dependency: `structure -> test -> relax -> electronic/scf ->
  downstream electronic/phonon/analysis`.
- Treat `test/` as parameter exploration for ENCUT, KPOINTS, SIGMA, smearing,
  POTCAR variants, and related convergence checks. Do not use test outputs as
  production upstream inputs unless the user explicitly promotes one result.
- Treat `relax/` as the production structural foundation. Downstream SCF,
  electronic, and phonon jobs should normally use the approved relaxed
  `CONTCAR`, with path and hash recorded in the submit review. In an automation
  plan, declare this with the stage's `inputs_from` so the converged `CONTCAR`
  is staged into the next stage automatically (see
  `references/automation-cron.md`).
- Treat `electronic/scf/` as the production static calculation that generates
  total energy plus reusable `WAVECAR` and `CHGCAR` for band, DOS, charge,
  pCOHP, ELF, spin-density, PARCHG, and related post-processing workflows.
- Phonon jobs must use an optimized structure from `relax/` unless the user
  explicitly requests a non-relaxed or constrained reference structure.
- Automatic workflow handoff is allowed only inside a user-approved workflow
  envelope. Cron/tick scripts may monitor and submit the next stage, but each
  stage must still have a generated review and matching approval before
  `sbatch`.
- Judge a finished job by its parsed scientific outcome, not by exit code or the
  mere presence of output files. Use `vwf parse` (or `require_convergence` in an
  automation plan): a run can terminate cleanly without converging, and such a
  stage must not be treated as done.
- Automatic error recovery must be explicit, bounded by `max_retries`, and
  recorded in logs. Prefer established tools such as `custodian`, `pymatgen`,
  ASE, and phonopy validators for detection/repair helpers, but never allow a
  recovery command to silently change scientific parameters outside approval.
- Do not change scientific parameters such as KPOINTS, ENCUT, EDIFF, EDIFFG,
  ISMEAR, SIGMA, MAGMOM, structure files, or POTCAR choices for speed unless
  the user explicitly asks for that scientific change.
- Do not choose POTCAR variants on the user's behalf. Ask which functional and
  potential labels to use, then record the element order, title lines, source,
  and hashes in the submit review.
- For band calculations, record the full high-symmetry path and the generator
  used to create it. If VASPKIT, pymatgen, SeeK-path, phonopy, or another
  generator is missing, ask the user to install or activate an appropriate
  environment before proceeding.
- Do not submit a job when the current POSCAR/INCAR/KPOINTS/POTCAR hash differs
  from the latest submit review.
- Do not submit a job when node count, task count, wall time, worker count, or
  VASP command differs from the latest submit review.
- For finite-displacement phonons, submit worker jobs, not one Slurm job per
  displacement. Workers dynamically claim entries from `queue/undo`.
- Keep plot and analysis numeric data in `.dat` files. JSON is for metadata such
  as `state.json`, `task_spec.json`, and manifests.
- Keep workflow directories ordinary and inspectable; avoid hiding the real run
  state inside only a database.

## Script Entry Points

Set `PYTHONPATH` to this skill's `scripts/` directory:

```bash
SKILL=/Users/gyro/Library/CloudStorage/SynologyDrive-note-sync/project/coding/skillhub/vasp-workflow
export PYTHONPATH="$SKILL/scripts${PYTHONPATH:+:$PYTHONPATH}"
```

Create a case tree:

```bash
python -m vwf init-case --case-root ./SiC
```

Prepare finite-displacement phonon worker queue:

```bash
python -m vwf prepare phonon-fd \
  --case-root ./SiC \
  --taskset fd-001 \
  --dim "2 2 2" \
  --workers 5 \
  --profile nmg
```

Generate the mandatory submit review:

```bash
python -m vwf review submit \
  --taskset ./SiC/phonon/fd/fd-001
```

Submit worker jobs only after user approval:

```bash
python -m vwf submit workers \
  --taskset ./SiC/phonon/fd/fd-001 \
  --approved
```

Check queue state:

```bash
python -m vwf queue status \
  --taskset ./SiC/phonon/fd/fd-001
```

Parse a finished task for convergence, energy, forces, and errors:

```bash
python -m vwf parse --task-dir ./SiC/relax          # human summary
python -m vwf parse --task-dir ./SiC/relax --json   # machine-readable result
python -m vwf parse --task-dir ./SiC/relax --write  # also write parse_result.json
```

Create a workflow automation plan and print a cron line:

```bash
python -m vwf automation init --case-root ./SiC
python -m vwf automation cron-line --case-root ./SiC --interval-minutes 10
python -m vwf automation tick --case-root ./SiC --dry-run
```

## Reference Map

- `references/directory-layout.md`: standard case tree and task handoff files.
- `references/calculation-taxonomy.md`: relax, energy, electronic, and phonon
  task categories.
- `references/submit-review.md`: mandatory provenance/resource review before
  any `sbatch`.
- `references/fd-worker-queue.md`: dynamic FD phonon worker queue behavior.
- `references/automation-cron.md`: cron monitoring, workflow-level approval,
  and automatic stage handoff rules.
- `references/error-recovery.md`: bounded retry/correction model and suggested
  third-party helpers such as custodian and pymatgen.
- `references/cluster-profiles.md`: nmg/Phoenix/G3 profile caution, local
  override behavior, and live check expectations.
- `references/cluster-profiles.template.md`: copy to
  `references/cluster-profiles.local.md` for user-specific cluster facts; the
  local file is ignored by git.
- `references/safe-operations.md`: submit, overwrite, cancel, cleanup, and
  scientific-parameter red lines.
