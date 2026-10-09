# Explicit Archive and Transfer Policy

First screen and record logical retirement with reason/evidence in workflow.json.
Failed is not automatically disposable: preserve recovery inputs, diagnostics and
downstream dependencies. A logical archived task stays in place. Physical archival
is a separately scoped export or relocation, never an automatic consequence of failure.

Use this policy only after the user explicitly requests archive/export,
transfer, restore, or cleanup.

## Required authorization and path checks

Before writing:

1. identify the exact live source leaf or requested set;
2. obtain the destination from the user or project README;
3. resolve source and destination to absolute paths for the operation, while
   storing reusable provenance as relative paths where possible;
4. verify the source belongs to a registered route or the legacy calculations/ tree;
   recheck scheduler state and incoming references, including scripts and absolute paths;
5. state whether licensed pseudopotentials or large restart files are included;
6. run a dry run as a classification/data-inventory pass and report expected
   files, categories, omitted large files, and size;
7. never delete or move the live source as part of archive creation.

Do not default to `<workspace_root>/archive`, a composition-level `archive/`, a
structure-level `archive/`, `/home/<user>/...`, or another project's previous
destination.

## Export contents

Keep the minimal files needed to understand and reproduce the requested scope:

- leaf `README.md` and `workflow.json`;
- approved design reference when available;
- engine inputs, job script, concise scheduler logs, and decisive outputs;
- source structure and exact upstream dependency references;
- requested processed `.dat`, figures, and reports;
- diagnostics for a failed/rejected run when that is the export purpose.

Large wavefunction, charge-density, trajectory, scratch, and restart files are
opt-in. Explain size and downstream need before including them. Do not publish
licensed POTCAR/PAW or restricted pseudopotential content.

## Integrity records

Every explicit export version must contain:

- `manifest.json`: source, destination, timestamp, scope, file list, size,
  category, and SHA256 for exported files;
- `SHA256SUMS`: one checksum line per exported file.

These files belong to the export, not to every live task. The live
`workflow.json` keeps only hashes needed for scientific input/dependency
identity; submission verifies those existing hashes instead of creating a
duplicate hash inventory.

After `vwm_archive.py` completes, the manager still appends a concise archive
and verification event with `vwm_task_log.py`. The export manifest/ledger is
machine evidence; task and log README status blocks are the human handoff.

## Verification

Verify before transfer, restore, or any separately approved cleanup:

```bash
python <dft-work-manager-skill>/scripts/vwm_verify.py \
  --archive <explicit-export-version>
```

The verifier must confirm that both integrity records parse, every checksum
target stays inside the export directory, every listed file exists, and every
hash matches.

## Restore

Restore into a new destination when possible. Before overwriting any live
directory:

1. verify the export;
2. list the exact destination and conflicts;
3. compare the live README/`workflow.json` with the exported versions;
4. request explicit overwrite approval;
5. preserve the export integrity records or record their location.

## Cleanup boundary

Archive verification is evidence, not deletion permission. Cleanup is a
separate destructive action with exact targets and explicit authorization.
Never issue broad recursive cleanup against a workspace, composition, structure,
or unresolved variable/glob.
