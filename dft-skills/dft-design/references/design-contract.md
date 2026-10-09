# Calculation design contract

Registered routes keep docs/plan.md, calculation_design.json and append-only
history.jsonl in their docs/ directory. Legacy scopes keep
`plans/<composition>/<structure>/README.md`, `calculation_design.json` and history.jsonl. These are the human view, live design and immutable
review evidence; no additional plan/approval files are needed.

## Modes

Schema-v2 accepts `design_mode: task | research`; absent means `research`.
Research mode retains its existing scientific schema and strict production checks.

Task mode requires task identity, structure/source, engine envelope with exact
scientific parameters, calculation matrix/stages, `execution_plan.tasks[]`,
completion expectations and stop conditions. Research questions, hypotheses,
controls, convergence studies and uncertainty claims are not mandatory when inapplicable.
Never satisfy a validator by inventing scientific claims or evidence.

Each execution task declares safe relative static input sources or explicit
`source_task`/artifact recipes. An optional `job_script` selects an existing
workspace-relative dft-submit template copy; its actual name is retained.
The graph must have valid references and no cycles, irrespective of design mode.
An optional directory (for example 01_tests/ecut/k12) places a unique task_slug within
a numbered stage. Executable directories must not overlap. Pass the registered route
as --project to design commands when several routes share composition/structure.
The fixed plan.md carries the same design-sync marker used by legacy plan READMEs.

## Parameters and acceptance

`parameter_selection` distinguishes `pending`, `candidate`, `validated` and
`user_specified`. A user-specified exact value records its source/method and may
be approved for task execution without convergence evidence. Its precision is
unverified, not `validated`. Unknown essential parameter values still block execution.

Research production approval still requires validated cutoff, occupations and kpoints
with selected values and evidence, plus exact engine parameters.
Changing mode does not manufacture scientific acceptance.

## Drafts, review and binding

Initialize all known leaves before review with `initialize --draft`. Current inputs
are available to inspect; future dependent inputs remain recipes. Draft leaves cannot submit.
The user reviews parameters once. The approval event must actually be appended using
the design approval command with its verified snapshot/hash, reviewer, scope and event ID.

Use workflow `bind-approval` to attach that real event to the existing tree. Current
scientific files must match the reviewed event; binding never overwrites inputs.
Existing approved designs may still initialize through the original approved path.

An approval event contains the existing history schema, `scientific_design_approved`
event type, `<design_id>:rNNNN`, design revision, scope, reviewer, time, design path,
SHA256 and embedded design snapshot. Do not fabricate a temporary approval for draft creation.
The ordinary approved graph can submit without repeated user approval within its authorized scope.

## User edits

Current on-disk inputs are authoritative. Hash mismatch triggers reconciliation, not
re-approval. Ordinary changes update the live design and affected unsubmitted descendants.
Running snapshots and historical approvals stay immutable. Completed unexpected results
are retained and branch. Only a major scientific conflict returns to the user.

## Compatibility only

Schema-v1 designs and old approval bundles remain readable; do not silently rewrite them.
Embedded research convergence campaigns retain their original approval and evidence rules.
