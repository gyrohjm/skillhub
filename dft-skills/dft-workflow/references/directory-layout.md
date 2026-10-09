# Directory layout

Read the shared [workspace layout](../../dft-contracts/references/workspace-layout.md)
when initializing or extending a project. dft-project.json registers research routes;
a legacy calculations/ plus project marker remains supported. Read project/route
instructions and use registered relative paths, not inferred cluster or user paths.

Numbered stages such as 01_tests, 02_relax and 03_scf sit directly under a route.
Nest convergence variants within their stage. Only real variants, attempts or scientific
revisions add depth; common inputs belong in optional shared/ at their actual reuse scope.

The execution plan uses stable task_slug IDs. An optional directory such as
01_tests/ecut/k12 places a task within a nested stage. Input sources are portable
workspace-relative paths. initialize --route <relative-route> prepares new leaves
without replacing existing route files; an existing leaf requires reconciliation or
an explicit scientific rerun. bind-approval uses the same --route.

There is one workflow.json per executable leaf, and workflow.json is the sole live
leaf ledger: input authority/hash, recipes, exact upstream references, immutable
attempt snapshots, scheduler receipt, completion and lineage. Execution state must not
be copied into another machine ledger. Keep scheduler_complete, artifact_complete
and scientifically_accepted independent; current selection is an explicit decision.

Stage analysis/data, figures, scripts and analysis/README.md stay with the source task.
The project results/ contains only its unique main_report.md and selected final
figures/tables, with derived provenance and a navigation README. Use the project document
tool for stable roles and sections; use Git for previous document versions.

Technical failure retries in place after preserving evidence in attempts/attempt-NNN/.
A scientific rerun uses revisions/rerun_NNN/ beneath the original task, a new UUID and
lineage.derived_from. Do not overwrite completed outputs or inherit selection. Pin
upstream references to exact revisions when task_slug becomes ambiguous.

The project keeps one .dft/resource-profile.json cache. Private environment details,
rendered submission scripts, licensed potentials and large raw/restart data stay out
of public Git. dft-submit owns launcher settings. Preparation never probes unrelated
clusters or creates an environment file per task.

## Compatibility only

Existing calculations/<composition>/<structure>/<task>[/<variant>] trees retain old
paths and structure-level analysis. The legacy prepare, vwf and qewf helpers remain
compatibility surfaces. Existing archives/failed trees are readable and never moved
as a side effect of initialization or a documentation update.
