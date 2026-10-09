# Local Task Logs

Paired projects keep the full human timeline only in local route docs/log.md; cluster generated README views show operational facts; human stage sections own analysis. Registered routes use one docs/log.md timeline. Pass --event-id for a stable event;
repeating identical content is a no-op, conflicting content requires a correction event.
Legacy projects retain root-level `logs/<composition>/<structure>.md`. It is an agent-readable execution trail. The live task README,
`workflow.json`, and engine files remain authoritative; any ledger or archive
is optional and derived.

## Files And Timing

- Append one row after each relevant manager registration, state/review update,
  failed-task movement, recovery decision, optional export/verification, or
  cleanup plan.
- Keep one structure log rather than one file per task. Use the task/variant
  relative path in the `task` column so multiple lineages remain locatable.
- Legacy log index READMEs remain compatibility-only; new routes do not create container READMEs.
- For legacy projects only, the append helper refreshes a marked latest-status block in the task README,
  structure README, and both log index READMEs. It must preserve all text
  outside those markers and must not rewrite the append-only timeline.
- Keep the log append-only; correct a mistaken event by adding a superseding
  event instead of rewriting history.

## Required Fields

Record timestamp, actor, composition/structure/task, manager action, resulting
status, and a live evidence path. For optional operations, also record ledger,
manifest, SHA256 verification, or export path. State the next action or handoff.

Do not copy POTCAR content, secrets, large output, or unverified physical
interpretation into task logs. Record durable decisions under stable keys in MEMORY.md and stage conclusions
in the cluster numbered-stage README.md; project synthesis belongs in local analysis/main_report.md for paired projects (results/main_report.md for existing single-root projects).

## Data handoff boundary

The manager may inventory and classify existing files, but it does not produce
new `.dat` arrays, figures, or scientific conclusions. Raw engine files remain
under the task leaf. Paired source products use cluster task data/ and figures/;
stage conclusions use the cluster numbered-stage README with relative figure/evidence links. Existing single-root task-local
analysis/data, figures and analysis/README.md remain readable.
Retain a relative pointer to the producing task. Send extraction, validation, and
interpretation requests to `dft-analysis`.
