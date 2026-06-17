# Report Format

Write analysis reports as Markdown:

```text
analysis/reports/<topic>.md
```

Include:

- source archive or workflow path,
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
