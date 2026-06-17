---
name: vasp-work-manager
description: Archive and verify VASP calculation data without turning the workflow into a heavy task manager. Use when preserving VASP result directories, workflow tasksets, state.json, task_spec.json, submission_review.dat, queue logs, core input/output files, .dat plot data, band/DOS/fat-band/phonon/pCOHP/ELF/CHGDIFF figures, manifests, SHA256 checksums, and lightweight optional index records for nmg/Phoenix/G3 work; also use when auditing archive integrity or planning safe data cleanup without changing scientific inputs such as KPOINTS, ENCUT, or INCAR parameters unless explicitly requested.
---

# VASP Work Manager

## Overview

Use this skill to keep VASP work findable after the calculation is done. Keep
the product small: archive directories with manifests and checksums are the
source of truth; the SQLite ledger is only an optional index.

## Required First Steps

1. If the task may submit, cancel, delete, overwrite, clean, transfer large
   data, or run compute, first read `references/archive-policy.md` and the
   relevant cluster file.
2. For archiving or moving finished calculations, read
   `references/archive-policy.md`.
3. For band, DOS, fat-band, phonon, pCOHP, ELF, CHGDIFF, spin-density,
   PARCHG, or notebook-style figures, read
   `references/plot-data.md`; preserve the data files used to draw the figure,
   not just the image.
4. For nmg jobs, read `references/clusters-nmg.md`. For Phoenix CPU/GPU jobs,
   read `references/clusters-phoenix.md`. For G3/H100, also read
   `references/g3-cautions.md`.

## Operating Rules

- Treat data retention and archive integrity as the core workflow.
- Keep source calculation directories ordinary and inspectable.
- Preserve workflow handoff files such as `task_spec.json`, `state.json`,
  `submission_review.dat`, `submission_approval.json`, and `queue.log` when
  they exist.
- Script only repeated, low-risk operations. Do not add a new script until the
  same operation has become routine enough to justify maintenance.
- Do not change scientific parameters such as KPOINTS, ENCUT, ISMEAR, SIGMA,
  EDIFF, EDIFFG, MAGMOM, or structure files just to improve speed. Performance
  tuning may change Slurm resources and MPI/OpenMP layout only, unless the user
  explicitly asks to change calculation parameters.
- Do not archive licensed POTCAR content into a public Git repository. POTCAR
  may be included in a private archive when the user owns the license and the
  archive location is appropriate.
- Do not default to keeping WAVECAR, CHGCAR, vasprun.xml, or XDATCAR in long
  term archives. Include them only when the user asks or restart/analysis needs
  them.

## Main Scripts

Script paths are relative to this skill directory.

- `scripts/vwm_archive.py`: copy core files and processed data into a durable
  archive, write `manifest.json` and `SHA256SUMS`, and update the ledger.
- `scripts/vwm_verify.py`: verify archive files against `SHA256SUMS` and the
  manifest.

Optional support scripts:

- `scripts/vwm_report.py`: export the lightweight SQLite index when one exists.
- `scripts/vwm_ledger.py`: maintain the optional index; avoid expanding it into
  a full task database.

Prefer explicit paths:

```bash
SKILL=/Users/gyro/Library/CloudStorage/SynologyDrive-note-sync/project/coding/skillhub/vasp-work-manager
LEDGER=/home/jmhe/project/vaspmgr_test/vwm.sqlite
ARCHIVE=/home/jmhe/project/vaspmgr_test/archive
```

## Common Workflows

Register an existing calculation:

```bash
python "$SKILL/scripts/vwm_archive.py" \
  --source /path/to/run \
  --project sic-test \
  --task relax-001 \
  --archive-root "$ARCHIVE" \
  --ledger "$LEDGER" \
  --state COMPLETED \
  --review-status NEEDS_REVIEW
```

Verify an archive before cleanup or transfer:

```bash
python "$SKILL/scripts/vwm_verify.py" \
  --archive "$ARCHIVE/sic-test/relax-001/20260617T120000Z"
```

Export the optional index when useful:

```bash
python "$SKILL/scripts/vwm_report.py" --ledger "$LEDGER" \
  --project sic-test --format csv --output sic-test.csv
```

Use manual restore rather than a restore script:

```bash
mkdir -p /path/to/restored-run
rsync -av --exclude manifest.json --exclude SHA256SUMS \
  "$ARCHIVE/sic-test/relax-001/20260617T120000Z/" /path/to/restored-run/
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
