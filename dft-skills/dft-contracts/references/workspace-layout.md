# DFT workspace layout

For new local/cluster projects initialized from docs/refs, follow
[paired projects](paired-projects.md). Their local analysis/ and cluster task-owned
scripts/data/figures take precedence over the single-root example below.

One workflow.json per executable leaf is the live execution record.
`.dft/resource-profile.json` is the project cache; private environment information
stays outside Git. The project layout never grants permission to submit jobs.

## Discover and register

Discover the nearest `dft-project.json`, whose routes bind portable relative paths
to composition and structure identities. An alias is a label, not an inferred
chemical identity. Preserve existing names until relocation is explicitly requested.
Read AGENTS.md, MEMORY.md, the route README and current plan before writing.
Use `dft-work-manager/scripts/dft_project.py init` and `route` as documented in
[project records](project-records.md). Register only routes being worked on.

```text
project/
├── README.md                   # project map and reading order
├── AGENTS.md                   # work rules and tool entrypoints
├── MEMORY.md                   # durable decisions, questions and next actions
├── dft-project.json            # route identities; no machine paths or credentials
├── results/
│   ├── README.md               # final artifact navigation and source links
│   ├── main_report.md          # sole current project synthesis
│   ├── figures/                # selected final figures, created when published
│   ├── tables/                 # selected final summary tables
│   └── manifest.json           # derived publication provenance and checksums
└── <system_alias>/<route>/
    ├── README.md               # purpose, stage order, dependencies and selected results
    ├── shared/                 # optional: actual common inputs only
    │   ├── pseudo/
    │   └── structures/
    ├── docs/
    │   ├── plan.md             # one current route plan; update stable sections
    │   ├── calculation_design.json
    │   ├── history.jsonl       # immutable approval and plan-change events
    │   └── log.md              # one derived timeline, idempotent event IDs
    ├── 01_tests/
    │   ├── README.md
    │   ├── ecut/<variant>/
    │   └── kmesh/<variant>/
    ├── 02_relax/
    ├── 03_scf/
    └── scripts/                # optional helpers shared by several stages
```

Stage names describe work; numbers aid reading, explicit dependencies govern execution.
Both `03_scf` and existing `p3_scf` are valid. Add depth only for real subtasks,
parameter variants or scientific revisions. Create needed directories, not empty stage
trees or mandatory studies/stages/variants/revisions wrappers. Engine is metadata.

## Task-local work and final results

A simple task contains README.md, workflow.json and engine-native inputs/outputs.
Use the owning stage README for incremental conclusions. Existing single-root
`analysis/README.md` documents remain readable and are not deleted automatically.
When needed, create `analysis/data/`, `analysis/figures/` and task-specific `analysis/scripts/`.
Cross-stage analysis may live in route analysis/, with precise task references.
Promote reusable tools to `<workspace_root>/code/`; route-local helpers stay in
`<route>/scripts/`. Existing structure-local scripts remain usable.

The only current main report is `results/main_report.md`, with stable scientific
sections. README explains purpose, contents, reading order, dependencies and links;
it does not repeat the project synthesis. Publish only selected final figures/tables.
Intermediate data, diagnostics and scripts remain in their source task. Published
copies are regenerated from recorded sources, never edited independently.

README owners are project root, research route and numbered task stage. Explain
container directories and parameter variants in the owning README; do not generate
placeholder READMEs at every level. See the [role templates](../../dft-work-manager/references/task-readme-template.md).

## Common inputs

Use shared/ at the nearest scope that actually shares files. It is optional;
neither 00_pseudo nor any software is mandatory. Keep source structures,
pseudopotentials and genuinely reusable references with versions and hashes.
Preserve shared versions already used by a run; pin each consumer's version.
Relaxed structures first belong to their producing task; promote an explicitly
selected reference with provenance. Wavefunctions/restart/DFPT/EPW products stay
owned by producing tasks and are reused through checked dependencies.
Shared does not mean licensed potentials may enter Git.

## Rework and retirement

Use [project records](project-records.md) for screen, mark, rework-impact and publish.
Execution completion, artifact completeness, scientific acceptance and current
selection are distinct. A new rerun does not automatically replace an accepted result.

Technical failure retries in place after preserving evidence in attempts/.
In registered routes, scientific reruns nest under the original task's
`revisions/rerun_NNN/`; later revisions are peers there. Original outputs stay intact.
Each scientific rerun gets a new UUID and lineage.derived_from; retries keep identity.
Pin ambiguous upstream references to exact revisions, not the latest folder name.

Screen before retirement: missing evidence is needs_review, not guessed failure or
success. Record reason and evidence for recoverable, terminated, superseded or archived.
Logical retirement keeps files in place. Physical movement is separate: check live jobs,
all dependencies including absolute paths/scripts, checksums and migration mapping.
Unresolved references block relocation. Queued/running tasks and evidence stay intact.

## Environment and Git

`docs/project-resources.md` is the private project baseline, referenced by AGENTS.md
and ignored in Git. No resource JSON or environment file per task. dft-submit owns
cluster/launcher settings. Private profiles stay outside every Git worktree.
Git stores plans, summaries, scripts, portable inputs and small analysis data. Runtime
workflow.json may contain local resource details and is ignored by default; retain it
with the calculation. Git commit is neither authorization nor scientific acceptance.
The optional staged-content hook never commits, pushes or rewrites history automatically.

## Compatibility only

Projects with calculations/ plus a project marker retain their original
`calculations/<composition>/<structure>/<task>[/<variant>]` paths and structure-level
analysis destinations. Records remain `plans/<composition>/<structure>/` and
`logs/<composition>/<structure>.md`; code/templates/ and `<structure_root>/scripts/`
remain supported. Existing failed/ trees and immutable approvals are not relocated.
Use init --layout legacy for that format. Registering routes does not automatically
migrate a legacy project or reinterpret old scientific evidence.
