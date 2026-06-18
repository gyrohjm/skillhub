# Research Data Lifecycle

## Canonical Flow

```text
raw_data -> code processing -> validation -> user approval -> formal_data
```

## `raw_data`

- Preserve original experimental outputs, downloaded sources, and calculation outputs.
- Never edit source files in place.
- Store temporary or partially processed products under `raw_data/interim/`.
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
- Append one row to `formal_data/MANIFEST.csv` containing artifact path, category, source file/data, processing code, parameters, validation, approver, approval date, manuscript usage, and SHA256.
- If the artifact changes, create a new filename or version and a new manifest row.
