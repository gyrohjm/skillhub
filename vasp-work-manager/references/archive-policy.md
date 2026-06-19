# Archive Policy

Archive finished VASP runs so the result can be inspected months later without
depending on a crowded working directory.

## Layout

New cluster projects must first create one short English project directory under
`/home/<user>/projects/`. If the local project name is Chinese, translate it to
a concise English `lowercase_snake_case` slug and confirm it with the user
before creating cluster paths. Do not use Chinese characters or long descriptive
phrases in cluster directory names.

Use this cluster layout by default:

```text
/home/<user>/projects/<project_slug>/
  calculations/
    <system_slug>/
      <case_slug>/
  archive/
    <system_slug>/
      <case_slug>/
        <timestamp>Z/
          files copied from the run directory
          result.json
          manifest.json
          SHA256SUMS
  ledger/
    vwm.sqlite
  docs/
    project_summary.md
```

For user `jmhe`, this becomes:

```text
/home/jmhe/projects/<project_slug>/
```

Archive a finished case from the cluster calculation path:

```text
/home/<user>/projects/<project_slug>/calculations/<system_slug>/<case_slug>
```

Use the archive root:

```text
/home/<user>/projects/<project_slug>/archive
```

Use the ledger path:

```text
/home/<user>/projects/<project_slug>/ledger/vwm.sqlite
```

Older paths such as `/home/jmhe/project/<project_slug>/...` may be recorded as
legacy source paths when they already exist, but new managed projects should use
the `/home/<user>/projects/<project_slug>/` convention.

## Cluster Workspace Policy

- Do not create `raw_data/` or `formal_data/` inside the cluster project root.
  Those directories belong to the local `init-research-project` data lifecycle.
- Keep raw VASP inputs/outputs in their original case directory under
  `calculations/<system_slug>/<case_slug>/`; do not duplicate them into another
  cluster data tree.
- Run post-processing and plotting in the same case root, using:

  ```text
  calculations/<system_slug>/<case_slug>/analysis/
    plot_data/
    figures/
    reports/
  ```

- `vasp-analysis` writes validated `.dat`, figures, and case reports there.
  `vasp-work-manager` records those paths in the ledger/archive manifest.
- Maintain only a concise project-level summary at `docs/project_summary.md`.
  Record system/case, task state, source path, analysis report/figure paths,
  archive path, and key conclusions; do not copy numeric data into the summary.
- When results are intentionally synchronized to the local research project,
  the local copy may enter `raw_data/calculations/<system_slug>/<case_slug>/`
  and later follow the local promotion lifecycle. This does not create a
  `raw_data/` directory on the cluster.

Use this minimum project-summary table:

```markdown
| task | state | source_case | analysis_files | archive | review | conclusion/notes |
|---|---|---|---|---|---|---|
| sic_bulk.relax_pbe | completed | calculations/sic_bulk/relax_pbe | analysis/plot_data/energy.dat; analysis/figures/relax.pdf | archive/sic_bulk/relax_pbe/... | accepted | Relaxed structure converged. |
```

Append or update one row per case. Keep detailed methods, numeric tables, and
figures in the case directory; the summary document is an index, not a second
data store.

Generate or refresh it from the ledger with:

```bash
python scripts/vwm_report.py \
  --ledger /home/<user>/projects/<project_slug>/ledger/vwm.sqlite \
  --project <project_slug> \
  --format markdown \
  --output /home/<user>/projects/<project_slug>/docs/project_summary.md
```

When copying results back into a local `init-research-project` tree, keep raw
inputs/outputs under `raw_data/calculations/<system_slug>/<case_slug>/`.
Promote figures, tables, plot `.dat` files, and approved structures into
`formal_data` only after validation and user approval.

Each archive timestamp is immutable. If a task is archived again, create a new
timestamped archive version instead of overwriting the old one.

## Ledger And Records

The manager owns task intake and durable records. Use the SQLite ledger as a
lightweight index, not as a workflow engine:

- register/import existing tasks with project, task, source path, cluster,
  task type, and state,
- record notes, review status, archive path, parse status, VASP status, and
  event history,
- record file checksums and categories after an archive version is created,
- report what is preserved and where it lives.

Do not use the ledger to decide new INCAR/KPOINTS/POTCAR values, submit jobs,
or perform analysis. Those actions belong to `vasp-workflow` and
`vasp-analysis`.

## Default Kept Files

Keep core inputs and outputs when present:

```text
POSCAR
POSCAR-ini
INCAR
KPOINTS
POTCAR
job.sh
submit.slurm
run_vasp.sh
OUTCAR
OSZICAR
CONTCAR
recovery_attempts/
vasp.out
vasp.err
task_manifest.json
task_spec.json
state.json
submission_review.dat
submission_approval.json
queue.log
result.json
```

Keep processed data and figure data by default:

```text
*.dat
*.csv
*.png
*.pdf
```

Keep metadata by default:

```text
*.json
*.md
```

This includes workflow state, submit-review records, plot manifests, band, DOS,
fat-band, phonon, pCOHP, ELF, CHGDIFF, spin-density, PARCHG, EOS, and
notebook-derived data tables. Primary numeric plot data should be `.dat`; JSON
should describe metadata, not replace plot arrays.

## Default Exclusions

Do not keep these large files by default:

```text
WAVECAR
CHGCAR
vasprun.xml
XDATCAR
ELFCAR
PARCHG
```

Include them only when the user explicitly asks or when a restart/analysis
requires them. Before including large files, state the expected archive size
when possible.

When downstream task directories contain symlinks to SCF `CHGCAR` or `WAVECAR`,
record the link target in the manifest. Do not silently dereference those links
and duplicate the large files unless the user explicitly asks for a
self-contained archive that includes them.

## Manifest Requirements

Every archive version must write:

- `manifest.json`: source path, archive path, project, task, timestamp, selected
  file list, size, SHA256, category, review status, and plot data list.
- `SHA256SUMS`: one line per archived file, compatible with `sha256sum -c`.
- `result.json`: existing parsed result if available, otherwise a minimal
  generated summary from OSZICAR/OUTCAR.

## Verification

Verify an archive before using it as the basis for cleanup, transfer, or
publication:

```bash
python scripts/vwm_verify.py --archive /path/to/archive/system_slug/case_slug/timestamp
```

The verifier checks:

- `manifest.json` exists and is valid JSON.
- `SHA256SUMS` exists and can be parsed.
- every checksum target stays inside the archive directory.
- every listed file exists.
- every listed file matches its SHA256 hash.
- files listed in `manifest.json` are also covered by checksums.

Exit codes:

- `0`: archive verified.
- `1`: integrity or archive-path problems were found.
- `2`: command usage error.

Use `--json` when another tool or script needs machine-readable output.

## Manual Restore

Do not maintain a separate restore script until restore becomes a frequent
operation. Restore is intentionally ordinary file copying:

```bash
ARCHIVE=/path/to/archive/system_slug/case_slug/timestamp
DEST=/path/to/restored-run

mkdir -p "$DEST"
rsync -av --exclude manifest.json --exclude SHA256SUMS "$ARCHIVE"/ "$DEST"/
```

Before overwriting an existing run directory:

1. Verify the archive.
2. List the destination directory.
3. Copy into a new directory when possible.
4. Keep `manifest.json` and `SHA256SUMS` beside the restored data or record
   their archive path in notes.

## Safety Rules

- Run a dry run first when archiving unfamiliar or very large directories.
- Never delete the source directory as part of archive creation.
- Never use broad destructive cleanup commands after archiving. If cleanup is
  needed, list exact targets first.
- Do not put archives containing licensed POTCAR files in public repositories.
- Keep archive roots outside transient scratch unless the final archive is
  copied back to persistent storage.

## Command Pattern

```bash
python scripts/vwm_archive.py \
  --source /path/to/run \
  --project project-name \
  --task task-name \
  --archive-root /path/to/archive-root \
  --ledger /path/to/vwm.sqlite \
  --state COMPLETED \
  --review-status NEEDS_REVIEW
```

Preview first:

```bash
python scripts/vwm_archive.py ... --dry-run
```

Include large restart files only when needed:

```bash
python scripts/vwm_archive.py ... --include-large
```
