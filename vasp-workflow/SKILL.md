---
name: vasp-workflow
description: "Running/orchestration layer for VASP calculation tasks: workflow design, structure/POSCAR research, input preparation, submit review, safe Slurm submission, queue/dependency handoff, parsing, bounded recovery, and automation. Use when planning or preparing test/relax/SCF/band/DOS/phonon tasks, confirming POSCAR/INCAR/KPOINTS/POTCAR/job.sh provenance, selecting nmg/Phoenix/G3 resources, generating submit reviews, submitting jobs, handling runtime failures, or using vwf helpers. Do not use for long-term task registration/archive ledger work or plot/data analysis; hand those to vasp-work-manager and vasp-analysis."
---

# VASP Workflow

## Overview

Use this skill as the running/orchestration layer for VASP task creation,
submission, monitoring, dependency handoff, and bounded recovery. The main job
is to make the Agent follow the user's calculation process correctly:

```text
read rules -> confirm input sources -> prepare/check files -> show submit review -> get user approval -> submit
```

Use `vasp-work-manager` after tasks need registration, archive records, ledger
updates, or integrity checks. Use `vasp-analysis` after outputs exist and need
`.dat` extraction, plotting, or interpretation.

## Skill Boundary

- Owns: case/task directory creation, structure research, input generation,
  submit reviews, Slurm submission, dependency orchestration, bounded recovery,
  and workflow-state files such as `task_spec.json`, `state.json`, queue logs,
  and `submission_review.dat`.
- Does not own: durable task registry/ledger, archive manifests/checksums,
  cleanup decisions, plot-ready data extraction, figures, or scientific
  interpretation reports.
- Handoff: send completed or failed task records to `vasp-work-manager`; send
  DOS/band/phonon/ELF/CHGDIFF/pCOHP extraction and interpretation to
  `vasp-analysis`.

## Required First Steps

1. For any submit, cancel, overwrite, cleanup, transfer, or compute action, read
   `references/safe-operations.md`.
2. Before planning a calculation chain, read `references/workflow-order.md`.
3. Before creating a new case tree, read `references/directory-layout.md`.
4. Before generating a POSCAR from only a formula, material name, phase family,
   or uncertain structure description, read `references/structure-research.md`.
5. Before preparing or checking inputs, read `references/input-review.md`.
6. Before selecting a built-in INCAR preset or drafting an INCAR template, read
   `references/incar-templates.md`.
7. Before choosing POTCAR files, read `references/potcar-policy.md`; default
   functional is PBE, but the concrete POTCAR labels/paths/hashes must be
   reviewed before submit.
8. Before any `sbatch`, read `references/submit-review.md`; every submission
   needs explicit user approval of POSCAR, full INCAR, KPOINTS, POTCAR, Slurm
   resources, and task count.
9. For finite-displacement phonons, read `references/fd-worker-queue.md`.
10. For nmg/Phoenix/G3 resources, read `references/cluster-profiles.md`; if
   `references/cluster-profiles.local.md` exists, read it next.
11. Before Phoenix CPU, Phoenix-GPU, g1/g2 A100, or g3 H100 submissions, read
    `references/phoenix-submit.md`.
12. When a Slurm, VASP, Wannier90, or phonopy error appears, read
    `references/common-errors.md` before proposing fixes.
13. Read `references/automation-cron.md` and `references/error-recovery.md` only
   when the user explicitly wants automatic handoff, cron polling, or bounded
   retry behavior.

## Operating Rules

- Default POTCAR functional is PBE. Never silently choose the element-specific
  POTCAR label or path when the local catalog is missing or ambiguous.
- Never infer a production POSCAR from chemical formula alone. When the phase or
  structure is uncertain, research candidate structures and ask the user to
  choose the intended phase/model before writing `structure/POSCAR.initial`.
- Do not submit until the user has reviewed complete calculation parameters:
  full effective INCAR, KPOINTS mesh/path, POTCAR functional/labels/titles/hash,
  POSCAR source/structure details, Slurm resources, VASP command, and task
  count.
- Before a production calculation chain, define the downstream parameter
  envelope for relax, SCF, band, DOS, phonon, and related follow-up tasks:
  inherited INCAR parameters, explicit overrides, KPOINTS policy, POTCAR
  labels, structure source, cluster profile, resource envelope, and completion
  gate. Downstream stages may proceed inside this reviewed envelope after relax
  convergence; anything outside it needs a new review.
- Do not change scientific inputs such as POSCAR, POTCAR, ENCUT, KPOINTS,
  ISMEAR, SIGMA, MAGMOM, EDIFF, or EDIFFG for convenience or speed unless the
  user explicitly approves that scientific change.
- Treat `test/` as parameter exploration only. Production calculations normally
  flow `test -> relax -> electronic/scf -> downstream electronic/phonon ->
  analysis/archive`.
- For relax continuation, keep `POSCAR-ini` as the initial approved geometry,
  copy `CONTCAR` to `POSCAR` only inside the approved recovery envelope, and
  preserve each unconverged attempt's `OUTCAR` and `CONTCAR` under
  `recovery_attempts/attempt-N/`.
- Do not advance from relax to SCF until `vwf parse` or equivalent review
  confirms ionic convergence. A final relax that takes one ionic step is useful
  evidence, not the formal gate.
- Reuse SCF `CHGCAR` and `WAVECAR` in downstream electronic tasks with
  symbolic links (`ln -s`) rather than copies.
- When a task needs ledger registration, archive manifests, checksum
  verification, or cleanup planning, stop workflow actions and hand the record
  to `vasp-work-manager`.
- Treat scripts as helpers for mechanical, repeated, or error-prone actions.
  Prefer reference instructions for scientific judgment and workflow decisions.
- Optional automation cannot bypass submit review. It may submit only when the
  stage has either a matching `submission_approval.json` or explicit
  `preapproved_by_workflow: true` from the initial reviewed workflow envelope.
  Any input hash or resource envelope change invalidates old approval.

## Helper Scripts

Set `PYTHONPATH` when using helper scripts:

```bash
SKILL=/Users/gyro/Library/CloudStorage/SynologyDrive-note-sync/project/coding/skillhub/vasp-workflow
export PYTHONPATH="$SKILL/scripts${PYTHONPATH:+:$PYTHONPATH}"
```

Common helpers:

```bash
python -m vwf init-case --case-root ./SiC
python -m vwf init-case --cluster phoenix --project-slug sic_project --system-slug sic_bulk --case-slug relax_pbe
python -m vwf prepare relax --case-root ./SiC --potcar /path/to/POTCAR --encut 520 --kmesh "8 8 8"
python -m vwf prepare relax --case-root ./SiC --potcar /path/to/POTCAR --incar-preset magnetic-vdw-relax --kmesh "8 8 8"
python -m vwf prepare relax --cluster nmg --project-slug sic_project --system-slug sic_bulk --case-slug relax_pbe --encut 520 --kmesh "8 8 8" --profile nmg
python -m vwf prepare scf --case-root ./SiC --source-poscar ./SiC/relax/CONTCAR --potcar /path/to/POTCAR --encut 520 --kmesh "12 12 12"
python -m vwf prepare band --case-root ./SiC --source-poscar ./SiC/relax/CONTCAR --potcar /path/to/POTCAR --encut 520 --line-points 20
python -m vwf prepare dos --case-root ./SiC --source-poscar ./SiC/relax/CONTCAR --potcar /path/to/POTCAR --encut 520 --kmesh "16 16 16" --nedos 2001
python -m vwf review submit --taskset ./SiC/relax
python -m vwf parse --task-dir ./SiC/relax --write
```

When `--case-root` is omitted, pass `--project-slug`, `--system-slug`, and
`--case-slug`; the default cluster path is
`/home/jmhe/project/<project_slug>/calculations/<system_slug>/<case_slug>`.
For new work that will be managed by `vasp-work-manager`, prefer an explicit
`--case-root /home/<user>/projects/<project_slug>/calculations/<system_slug>/<case_slug>`
so the case lands under the managed cluster project root.
For standard prepare commands, explicit `--potcar` wins. Without it, profile
defaults search `/home/jmhe/app/pot` on nmg and
`/home/jmhe/app/pot_database` on Phoenix profiles; ambiguous or missing
matches require user confirmation.

Standard stage `job.sh` files are rendered from
`assets/templates/jobvasp.sh`. Edit that template when the shared submit script
structure needs a new line or changed module pattern; resource values still
come from the reviewed profile/CLI envelope.

For `prepare band` and `prepare dos`, if `electronic/scf/CHGCAR` or
`electronic/scf/WAVECAR` already exists and the user has not provided an
explicit `--stage-from` destination for that file, the helper symlinks it into
the downstream task and records the link in `task_spec.json` and
`submission_review.dat`.

Optional helpers:

```bash
python -m vwf prepare phonon-fd --case-root ./SiC --taskset fd-001 --dim "2 2 2" --workers 5
python -m vwf submit workers --taskset ./SiC/phonon/fd/fd-001 --approved
python -m vwf automation tick --case-root ./SiC --dry-run
python -m vwf automation review --case-root ./SiC
```

## Reference Map

- `references/workflow-order.md`: stage order and upstream file choices.
- `references/directory-layout.md`: case tree and task directory conventions.
- `references/structure-research.md`: database/literature structure lookup,
  candidate comparison, user confirmation, and POSCAR provenance rules.
- `references/input-review.md`: POSCAR/INCAR/KPOINTS/POTCAR/job.sh review rules.
- `references/incar-templates.md`: grouped INCAR template categories and built-in presets.
- `references/potcar-policy.md`: PBE default, private catalog behavior, and
  POTCAR review requirements.
- `references/submit-review.md`: mandatory approval contract before any submit.
- `references/fd-worker-queue.md`: dynamic finite-displacement worker model.
- `references/cluster-profiles.md`: cluster profile cautions and live checks.
- `references/phoenix-submit.md`: Phoenix CPU, g1/g2 A100, and g3 H100 Slurm
  profiles and review requirements.
- `references/automation-cron.md`: optional cron/watch helper behavior.
- `references/error-recovery.md`: optional bounded recovery guidance.
- `references/common-errors.md`: common Slurm, VASP, Wannier90, and phonopy
  failure signatures with allowed first actions and review-required changes.
- `references/safe-operations.md`: destructive action and scientific-input red
  lines.
- `assets/templates/jobvasp.sh`: editable standard Slurm submit script template
  for `relax`, `scf`, `band`, and `dos` helper output.
