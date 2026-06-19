# Research Data Lifecycle

## Canonical Flow

```text
raw_data -> code processing -> validation -> user approval -> formal_data
```

## `raw_data`

This section defines the local research-project lifecycle. Do not mirror the
`raw_data/` or `formal_data/` tree on a VASP cluster project.

- Preserve original experimental outputs, downloaded sources, and calculation outputs.
- Never edit source files in place.
- Store temporary or partially processed products under `raw_data/interim/`.
- Store calculation data under `raw_data/calculations/<system_slug>/<case_slug>/`.
- Keep VASP inputs, outputs, pre-relax structures such as `POSCAR.initial`, and
  post-relax structures such as `CONTCAR` in raw data or the archived case
  first. Do not treat a relaxed structure as formal data until the user
  explicitly approves it for reuse or publication.
- Within cluster VASP case directories, downstream tasks should reuse SCF
  `CHGCAR` and `WAVECAR` with symbolic links. When syncing back to local raw
  data or archiving, record link targets and avoid duplicating those large files
  unless the user asks for a self-contained copy.
- On clusters, keep source outputs in the case task directories and write
  `.dat`, figures, and reports under the same case's `analysis/` directory.
  Maintain only a project-level `docs/project_summary.md` index; create local
  `raw_data` entries only when results are intentionally synced back.
- Record origin, acquisition date, instrument/code version, and relevant run identifiers.

## `code`

- Keep all transformations reproducible in scripts or notebooks.
- Use English `lowercase_snake_case` filenames.
- Record parameters, software environment, and input paths.
- Tests should validate parsing, units, array alignment, and expected invariants.

## Validation Gate

Before promotion confirm:

- Source provenance is known.
- Processing code and parameters are recorded.
- Units, labels, dimensions, and physical meaning are checked.
- Results reproduce from preserved source data.
- The artifact is suitable for a manuscript figure, table, structure, plot dataset, or supplement.
- The user explicitly approves promotion.

## `formal_data`

- Copy rather than move the approved artifact; preserve the source.
- Never overwrite an existing artifact.
- Use only `plot_data`, `figures`, `tables`, `structures`, or `supplementary` categories.
- Store approved structures under `formal_data/structures/<system_slug>/`.
- Append one row to `formal_data/MANIFEST.csv` containing artifact path, category, source file/data, processing code, parameters, validation, approver, approval date, manuscript usage, and SHA256.
- If the artifact changes, create a new filename or version and a new manifest row.
