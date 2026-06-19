---
name: vasp-work-manager
description: "Records/archive layer for existing VASP calculation work: register, record, archive, report, and verify tasks without creating, submitting, recovering, or changing calculations. Use when importing tasks into a lightweight ledger, preserving workflow tasksets, state.json, task_spec.json, submission_review.dat, queue logs, core input/output files, .dat plot data, figures, manifests, SHA256 checksums, archive versions, and task history for nmg/Phoenix/G3 work; also use when auditing archive integrity, reporting the task database, updating project summaries, or planning safe data cleanup. Do not use for VASP input generation, Slurm submission, runtime recovery, resource changes, or scientific data analysis; hand those to vasp-workflow and vasp-analysis."
---

# VASP Work Manager

## Overview

Use this skill as the records/archive layer after a VASP task already exists.
Keep the product small: archive directories with manifests and checksums are the
source of truth; the SQLite ledger is the lightweight task registry and event
record. Use `vasp-workflow`, not this skill, for the running/orchestration layer
that prepares inputs, submits jobs, monitors queues, or performs recovery.

## Skill Boundary

- Owns: task registration/import, ledger updates, task notes/review status,
  archive manifests, SHA256 checksums, archive verification, task reports,
  plot-data retention, and cleanup planning from recorded evidence.
- Does not own: creating POSCAR/INCAR/KPOINTS/POTCAR/job scripts, submitting or
  recovering Slurm jobs, calling cluster resources, choosing scientific
  parameters, extracting numeric plot arrays, drawing figures, or interpreting
  physical results.
- Handoff: send input creation, orchestration, submission, and recovery to
  `vasp-workflow`; send `.dat` extraction, plotting, and interpretation to
  `vasp-analysis`.

## Required First Steps

1. For any task that mixes setup, analysis, archive, or registry work, read
   `references/skill-contract.md` first and keep the handoff boundaries.
2. If the user asks to submit, cancel, recover, or run compute, stop and hand
   off to `vasp-workflow`; this skill only records and preserves existing work.
3. If the task may delete, overwrite, clean, transfer large data, or change an
   archive, first read `references/archive-policy.md` and the relevant cluster
   file.
4. For archiving or moving finished calculations, read
   `references/archive-policy.md`.
5. For band, DOS, fat-band, phonon, pCOHP, ELF, CHGDIFF, spin-density,
   PARCHG, or notebook-style figures, read
   `references/plot-data.md`; preserve the data files used to draw the figure,
   not just the image.
6. For nmg jobs, read `references/clusters-nmg.md`. For Phoenix CPU/GPU jobs,
   read `references/clusters-phoenix.md`. For G3/H100, also read
   `references/g3-cautions.md`.

## Operating Rules

- Treat data retention and archive integrity as the core workflow.
- Keep source calculation directories ordinary and inspectable.
- Preserve workflow handoff files such as `task_spec.json`, `state.json`,
  `submission_review.dat`, `submission_approval.json`, and `queue.log` when
  they exist.
- On clusters, do not create project-level `raw_data/` or `formal_data/`.
  Preserve calculation outputs in their source case, keep processed data under
  that case's `analysis/` directory, and summarize paths/status/conclusions in
  `<project_root>/docs/project_summary.md`.
- Script only repeated, low-risk operations. Do not add a new script until the
  same operation has become routine enough to justify maintenance.
- Do not change scientific parameters such as KPOINTS, ENCUT, ISMEAR, SIGMA,
  EDIFF, EDIFFG, MAGMOM, structure files, Slurm resources, or MPI/OpenMP
  layout. Record the tuning request or observation in the ledger, then hand
  actual calculation changes to `vasp-workflow`.
- Do not archive licensed POTCAR content into a public Git repository. POTCAR
  may be included in a private archive when the user owns the license and the
  archive location is appropriate.
- Do not default to keeping WAVECAR, CHGCAR, vasprun.xml, or XDATCAR in long
  term archives. Include them only when the user asks or restart/analysis needs
  them.

## Main Scripts

Script paths are relative to this skill directory.

- `scripts/vwm_ledger.py`: register/import tasks, record notes/review status,
  update task states, list/show tasks, and inspect event history.
- `scripts/vwm_archive.py`: copy core files and processed data into a durable
  archive, write `manifest.json` and `SHA256SUMS`, and update the ledger.
- `scripts/vwm_verify.py`: verify archive files against `SHA256SUMS` and the
  manifest.

Optional support scripts:

- `scripts/vwm_report.py`: export the lightweight SQLite index when one exists.

Prefer explicit paths:

```bash
SKILL=/Users/gyro/Library/CloudStorage/SynologyDrive-note-sync/project/coding/skillhub/vasp-work-manager
PROJECT_ROOT=/home/jmhe/projects/sic_test
LEDGER=$PROJECT_ROOT/ledger/vwm.sqlite
ARCHIVE=$PROJECT_ROOT/archive
```

## Common Workflows

Register or update an existing task without archiving:

```bash
python "$SKILL/scripts/vwm_ledger.py" --ledger "$LEDGER" register \
  --project sic_test \
  --task sic_bulk.relax_pbe \
  --source /path/to/run \
  --cluster nmg \
  --task-type relax \
  --state IMPORTED
```

Register an existing calculation:

```bash
python "$SKILL/scripts/vwm_archive.py" \
  --source /path/to/run \
  --project sic_test \
  --task sic_bulk.relax_pbe \
  --system-slug sic_bulk \
  --case-slug relax_pbe \
  --archive-root "$ARCHIVE" \
  --ledger "$LEDGER" \
  --state COMPLETED \
  --review-status NEEDS_REVIEW
```

Verify an archive before cleanup or transfer:

```bash
python "$SKILL/scripts/vwm_verify.py" \
  --archive "$ARCHIVE/sic_bulk/relax_pbe/20260617T120000Z"
```

Generate the cluster project summary document from the ledger:

```bash
python "$SKILL/scripts/vwm_report.py" --ledger "$LEDGER" \
  --project sic_test --format markdown \
  --output "$PROJECT_ROOT/docs/project_summary.md"
```

Use manual restore rather than a restore script:

```bash
mkdir -p /path/to/restored-run
rsync -av --exclude manifest.json --exclude SHA256SUMS \
  "$ARCHIVE/sic_bulk/relax_pbe/20260617T120000Z/" /path/to/restored-run/
```

## Reference Map

- `references/archive-policy.md`: archive layout, kept/excluded files,
  manifests, checksums, manual restore, and dry-run discipline.
- `references/plot-data.md`: plot data retention for band, DOS, fat-band,
  phonon, pCOHP, ELF, CHGDIFF, spin-density, PARCHG, and notebook-derived
  figures.
- `references/skill-contract.md`: handoff boundaries between `vasp-workflow`,
  `vasp-work-manager`, and `vasp-analysis`.
- `references/clusters-nmg.md`: nmg cluster paths, SSH alias, Nano/Nanod
  assumptions, and safe test workspace.
- `references/clusters-phoenix.md`: Phoenix CPU/GPU checks, module/resource
  caution, and Slurm safety.
- `references/g3-cautions.md`: special H100/G3 validation rules.
