# Archive Policy

Archive finished VASP runs so the result can be inspected months later without
depending on a crowded working directory.

## Layout

Use this layout by default:

```text
archive-root/
  <project>/
    <task>/
      <timestamp>Z/
        files copied from the run directory
        result.json
        manifest.json
        SHA256SUMS
```

Each archive timestamp is immutable. If a task is archived again, create a new
timestamped archive version instead of overwriting the old one.

## Default Kept Files

Keep core inputs and outputs when present:

```text
POSCAR
INCAR
KPOINTS
POTCAR
job.sh
submit.slurm
run_vasp.sh
OUTCAR
OSZICAR
CONTCAR
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
python scripts/vwm_verify.py --archive /path/to/archive/project/task/timestamp
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
ARCHIVE=/path/to/archive/project/task/timestamp
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
