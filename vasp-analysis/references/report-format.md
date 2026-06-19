# Report Format

Write analysis reports as Markdown:

```text
<case_root>/analysis/reports/<topic>.md
```

Include:

- source archive or workflow path,
- source case path on the cluster,
- local raw-data path only when results were intentionally synced to a local
  research project, normally `raw_data/calculations/<system_slug>/<case_slug>/`,
- data files used,
- figures used,
- main physical observations,
- uncertainty or failure notes,
- recommended next calculations.

When recommending new calculations, write a small next-task block for
`vasp-workflow` rather than submitting directly:

```text
next_task:
  kind: electronic/dos
  source: <path-or-archive>
  reason: Need denser DOS around EF.
  parameters_to_confirm: KPOINTS, INCAR, POSCAR, POTCAR
```

Do not treat a plot as evidence unless the `.dat` source for that plot is
preserved or can be regenerated from archived source files.
Validated `.dat` files and figures may be promoted into `formal_data` only
through the project data lifecycle; raw VASP outputs remain under
`raw_data/calculations/<system_slug>/<case_slug>/` or the verified archive.

Do not register tasks, write archive manifests, or update the VASP work-manager
ledger from analysis. Instead, list the generated `.dat`, figure, and report
paths in the report and hand them to `vasp-work-manager` for registration and
archive verification.

## Cluster Reporting

- Do not create `raw_data/` or `formal_data/` on the cluster.
- Keep numeric data and figures in the source case's `analysis/` tree.
- Keep the detailed interpretation in the case report.
- Provide one concise project-summary entry with system/case, source path,
  report path, figure paths, validation status, and key conclusions. The
  manager records this in `<project_root>/docs/project_summary.md` without
  copying data files into the project docs directory.
