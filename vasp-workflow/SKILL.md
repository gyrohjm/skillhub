---
name: vasp-workflow
description: Guide agents through VASP workflow design, structure/POSCAR research, input preparation, submit review, and safe Slurm submission. Use when planning or preparing test/relax/SCF/band/DOS/phonon VASP calculations, researching unknown crystal structures from databases or literature before POSCAR generation, confirming POSCAR/INCAR/KPOINTS/POTCAR/job.sh provenance, selecting nmg/Phoenix/G3 resources, generating mandatory submit reviews, or using optional helper scripts such as vwf prepare, parse, review, phonon-fd workers, or cron automation.
---

# VASP Workflow

## Overview

Use this skill as a workflow guide, not as a full workflow manager. The main job
is to make the Agent follow the user's VASP process correctly:

```text
read rules -> confirm input sources -> prepare/check files -> show submit review -> get user approval -> submit
```

Use `vasp-work-manager` after runs need archiving or integrity checks. Use
`vasp-analysis` after outputs exist and need `.dat` extraction, plotting, or
reporting.

## Required First Steps

1. For any submit, cancel, overwrite, cleanup, transfer, or compute action, read
   `references/safe-operations.md`.
2. Before planning a calculation chain, read `references/workflow-order.md`.
3. Before creating a new case tree, read `references/directory-layout.md`.
4. Before generating a POSCAR from only a formula, material name, phase family,
   or uncertain structure description, read `references/structure-research.md`.
5. Before preparing or checking inputs, read `references/input-review.md`.
6. Before choosing POTCAR files, read `references/potcar-policy.md`; default
   functional is PBE, but the concrete POTCAR labels/paths/hashes must be
   reviewed before submit.
7. Before any `sbatch`, read `references/submit-review.md`; every submission
   needs explicit user approval of POSCAR, full INCAR, KPOINTS, POTCAR, Slurm
   resources, and task count.
8. For finite-displacement phonons, read `references/fd-worker-queue.md`.
9. For nmg/Phoenix/G3 resources, read `references/cluster-profiles.md`; if
   `references/cluster-profiles.local.md` exists, read it next.
10. Before Phoenix CPU, Phoenix-GPU, g1/g2 A100, or g3 H100 submissions, read
    `references/phoenix-submit.md`.
11. Read `references/automation-cron.md` and `references/error-recovery.md` only
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
- Do not change scientific inputs such as POSCAR, POTCAR, ENCUT, KPOINTS,
  ISMEAR, SIGMA, MAGMOM, EDIFF, or EDIFFG for convenience or speed unless the
  user explicitly approves that scientific change.
- Treat `test/` as parameter exploration only. Production calculations normally
  flow `test -> relax -> electronic/scf -> downstream electronic/phonon ->
  analysis/archive`.
- Treat scripts as helpers for mechanical, repeated, or error-prone actions.
  Prefer reference instructions for scientific judgment and workflow decisions.
- Optional automation cannot bypass submit review. Any input hash or resource
  envelope change invalidates old approval.

## Helper Scripts

Set `PYTHONPATH` when using helper scripts:

```bash
SKILL=/Users/gyro/Library/CloudStorage/SynologyDrive-note-sync/project/coding/skillhub/vasp-workflow
export PYTHONPATH="$SKILL/scripts${PYTHONPATH:+:$PYTHONPATH}"
```

Common helpers:

```bash
python -m vwf init-case --case-root ./SiC
python -m vwf prepare relax --case-root ./SiC --potcar /path/to/POTCAR --encut 520 --kmesh "8 8 8"
python -m vwf prepare scf --case-root ./SiC --source-poscar ./SiC/relax/CONTCAR --potcar /path/to/POTCAR --encut 520 --kmesh "12 12 12"
python -m vwf prepare band --case-root ./SiC --source-poscar ./SiC/relax/CONTCAR --potcar /path/to/POTCAR --encut 520 --line-points 20
python -m vwf prepare dos --case-root ./SiC --source-poscar ./SiC/relax/CONTCAR --potcar /path/to/POTCAR --encut 520 --kmesh "16 16 16" --nedos 2001
python -m vwf review submit --taskset ./SiC/relax
python -m vwf parse --task-dir ./SiC/relax --write
```

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
- `references/potcar-policy.md`: PBE default, private catalog behavior, and
  POTCAR review requirements.
- `references/submit-review.md`: mandatory approval contract before any submit.
- `references/fd-worker-queue.md`: dynamic finite-displacement worker model.
- `references/cluster-profiles.md`: cluster profile cautions and live checks.
- `references/phoenix-submit.md`: Phoenix CPU, g1/g2 A100, and g3 H100 Slurm
  profiles and review requirements.
- `references/automation-cron.md`: optional cron/watch helper behavior.
- `references/error-recovery.md`: optional bounded recovery guidance.
- `references/safe-operations.md`: destructive action and scientific-input red
  lines.
