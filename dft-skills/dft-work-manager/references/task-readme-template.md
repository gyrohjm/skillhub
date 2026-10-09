# README roles

Use one README at the project root, each registered research route and each numbered
task stage. Parameter variants and pure container directories use their owner's guide.
Existing human documents stay intact; this rule limits new automatic creation.
A project-local template may refine these roles without duplicating logs or reports.

## Shared format

Human-maintained sections:

- **Purpose:** concrete purpose of this scope; no invented scientific question for a routine task.
- **Files and use:** a compact path / purpose / input-output table and relevant entry commands.
- **Interpretation:** cluster numbered-stage analysis, with evidence, validity, limitations and next action.

Generated `dft-view` section:

- **Current snapshot:** last verified observation, freshness and unresolved state.
- **Directory guide:** actual child directories and their purposes.
- **Tasks:** execution and use/acceptance are separate columns; link exact variants and revisions.
- **Recent changes:** latest three relevant events, replaced in place, not an appended history.

Preserve text outside generated blocks. Never copy all engine parameters, resources,
queue output or a full history into a README. workflow.json owns execution facts;
local route docs/log.md owns the complete human event timeline. Repeated events use
stable IDs. Scheduler COMPLETED does not imply scientifically accepted or selected.

## Project root

Local: project purpose, local/cluster ownership, route navigation, MEMORY, unique
main report and total data index. Cluster: operational scope, routes, execution overview
and a logical pointer to local records; no copied planning or analysis narrative.

## Research route

Explain the scope and stage/dependency order, current focus, blockers and next step.
Local routes link docs/plan.md and docs/log.md instead of repeating their content.
Cluster routes link operational task stages. Container docs/shared trees are described
here; no README is needed in every child directory.

## Task stage

Cluster: identify calculation type, task nature and evidence level when known. Explain
native inputs/outputs, scripts/, data/, figures/, the exact run/reproduction command,
upstream dependencies, execution status and gate/selection facts. Parameter variants
and scientific reruns share the stage overview; their workflow records retain identity.
Show `derived_from` for rerun lineage and keep `scheduler_complete`, `artifact_complete`
and `scientifically_accepted` separate. An unknown gate stays unknown.

Cluster stage README is the authoritative stage report: state conclusions, evidence,
validity, limitations and next action. Embed figures using relative Markdown image
paths; link plot data, scripts, input/output leaves and task identities. A stage is a
numbered directory such as 01_tests, not a k-mesh variant, displacement or MD replica.
Keep interim and unconverged findings here with their status clearly stated.

Local: keep the one formal main report. After convergence or the recorded stage
acceptance criteria pass, incorporate the validated conclusions and selected figures
with source stage/task paths, UUID/revision and data/script hashes. Keep cluster source
evidence intact. Local stage README copies, if needed for navigation, point to the
cluster report and are not independently maintained scientific reports.

Completion check: one authoritative stage README contains working relative figure
and evidence links; no new per-variant reports or duplicate stage prose; local final
claims are backed by recorded acceptance and traceable source artifacts. A manager
sync refreshes status only; scientific interpretation and publication require their
own evidence checks.

For paired projects, analysis/main_report.md includes final-artifact navigation; do not
create another analysis/README.md. Single-root project reports keep their existing paths.

## Maintenance triggers

Update after creation, submission, observing completion/failure, analysis, rework,
selection or publication; at handoff run sync/check. Tools refresh generated blocks,
and the Agent updates interpretation only when supported by new evidence. No new
facts means no duplicate event or timestamp-only rewrite. Disconnection preserves the
last known observation and marks it stale. No daemon or periodic poll is implied.
