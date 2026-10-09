---
name: dft-work-manager
description: "Initialize local/cluster DFT projects, organize legacy calculation directories, maintain fixed documents and task selection, and return reproducible final artifacts. Does not own scientific inputs or job submission."
---

# DFT Work Manager

Read the project storage_role and applicable AGENTS.md first. Read MEMORY.md on the local side and retrieve execution context from live or explicitly dated observations.
Before saving documents or handing off decisions, follow
[project records](../dft-contracts/references/project-records.md) for fixed paths,
names and evidence-linked memory. Environment details stay in private local profiles.


The canonical record is the live task leaf for registered tasks.
workflow.json is the sole live leaf ledger; logs, dashboards and archives are derived.
Keep `workflow.json` as the source of execution state. Cluster numbered-stage README scientific
explanation is human-authored; marked status blocks are derived.
An archive is an explicit export, never a default lifecycle stage.
Legacy files without a ledger remain unverified evidence until examined; filenames
and exit markers do not establish scientific acceptance.

## Initialize or work across local and cluster roots

For project setup from docs/refs, dual-root operation, cluster input edits or returning
selected results, follow [paired projects](../dft-contracts/references/paired-projects.md).
Read and classify the source materials, derive only known stages and source-linked
planning records, preview conflicts, initialize the two endpoints, then fill the existing
plan and unresolved questions. Completion means each endpoint's state is reported and
sync/check passes or names the exact pending items. Initialize an ordinary local Git
repository without staging, commits or pushes. A project initialization grants no new
calculation permission.

## Organize an existing project

For a cluttered project, old calculations without ledgers, directory renaming or
reference repair, follow [project organization](references/project-organization.md).
Inventory and reconcile documents first, preview exact moves and reference findings,
then apply only the eligible scope and verify the journal. Preserve blocked tasks in
place and explain them in the owning README/index. Initialization alone does not
rearrange old calculations or turn a legacy root into a paired project.

## Project context and document routing

Use `scripts/dft_project.py` for init/route/context, fixed document read/update,
idempotent events, screen/mark, rework-impact, publish, sync/check and local Git setup. See [project records](../dft-contracts/references/project-records.md).
Initialize once; read memory at session start and persist evidence-linked decisions
and next actions at handoff. These record operations do not authorize calculations.

## Select only the requested operation

Read applicable project instructions and the exact source leaf. For layout questions
consult [workspace layout](../dft-contracts/references/workspace-layout.md) and
[ownership](references/skill-contract.md). Do not scan the entire project to log one event.

- Record/log update: paired projects use local `dft_project.py event` and `sync`;
  never run the human logger against a cluster root. Single-root projects use
  `scripts/vwm_task_log.py append --task-dir <leaf>` with
  the event, evidence and next action. Registered routes use docs/log.md with stable
  event IDs; legacy projects retain logs/<composition>/<structure>.md and marked latest-status blocks,
  preserving surrounding human content.
- Stage README: [task template](references/task-readme-template.md), adapting it to
  the task. A routine task need not invent research hypotheses or controls.
- Data classification: [plot data](references/plot-data.md) when plots are involved.
  Classify existing files before moving or exporting them; raw engine files stay in
  their leaf. Paired projects keep scripts/data/figures with cluster tasks and stage analysis in the
  owning cluster numbered-stage README (never one report per calculation variant);
  local analysis/ holds the unique main_report.md and selected final figures/tables.
  Existing single-root routes retain their task-local analysis/ and results/ destinations. Legacy structure-level analysis remains supported.
- Export/transfer: read [archive policy](references/archive-policy.md)
  only for an explicit source/destination request. Dry-run inventory, preserve raw
  source and verify manifest/checksums. Archive creation never deletes or moves the live source.
  Logging the verified export is a human-record update step; the export manifest
  does not replace live records.
- In-project relocation: use [project organization](references/project-organization.md)
  for a byte-bound preview, fresh inactivity evidence, reference checks and resumable
  copies. A screening label alone is not permission or sufficient evidence to move a task.

## Screening and documents

Update fixed roles through read/document with an expected hash; conflicts require
rereading, not another filename. Use the three [README roles](references/task-readme-template.md); container directories use their owner’s guide.
Use event IDs for logs and stable keys for memory. Git holds document history.
Run screen before selection or retirement. Mark selected only from recorded scientific
acceptance, with a reason/evidence and unique purpose key; latest is not best.
Logical archived keeps files in place. Physical archival still uses explicit verified
export/relocation, fresh scheduler state and dependency checks. Do not interpret a
screening candidate as clearance to move files. At handoff sync and check, resolving
new issues without automatically changing scientific records or committing files.

## Boundaries

Do not edit scientific parameters, decide scientific acceptance, submit/cancel jobs,
repair runtime failures or automatically move failed calculations.
Technical failure retries in place through workflow after preserving
`attempts/attempt-NNN/`; completed unexpected results get a derived rerun branch.
Move to `failed/` only with explicit scope, confirmed terminal failure and no active recovery.
Never move queued/running tasks. Cleanup/deletion requires separate explicit scope.

Record `derived_from`, user overrides and the independent `scheduler_complete`,
`artifact_complete`, `scientifically_accepted` facts from the live workflow.
Do not infer new conclusions from filenames or overwrite the source ledger with an index.
For scheduler/resource operations use workflow plus `dft-submit`; for interpretation
use `dft-analysis` or `dft-wannier`. These skills need not be loaded for record-only work.

## Compatibility only

Optional `vwm_ledger.py`, `vwm_report.py`, `vwm_dashboard.py`, `vwm_export.py`
and `vwm_archive.py` use explicit paths and remain available. Do not invent a default
ledger/archive root, auto-migrate old task_spec/state files, or publish licensed POTCAR data.
