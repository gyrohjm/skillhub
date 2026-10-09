---
name: dft-design
description: Use when the user explicitly invokes $dft-design to prepare or revise DFT parameters and task graphs, or to design a new DFT study. Routine supplied-input tasks use task mode; research and convergence design are conditional.
---

# DFT Design

For DFT project work, read the applicable AGENTS.md and project storage_role; MEMORY.md belongs to the local planning side.
Before saving documents or handing off decisions, follow
[project records](../dft-contracts/references/project-records.md) for fixed paths,
names and evidence-linked memory. Environment details stay in private local profiles.

For paired local/cluster projects, read [paired projects](../dft-contracts/references/paired-projects.md) before preparing inputs, writing analysis or transferring results.



Own exact scientific parameters, sources, task graph and the initial parameter review.
`dft-workflow` materializes inputs and runs tasks. `dft-submit` owns resource
and launcher conventions; do not reproduce cluster policy here.

## Choose the smallest applicable mode

- `design_mode: task`: existing inputs, explicit user parameters or a reusable
  design. Record structure/source, engine, exact parameters, tasks/dependencies,
  expected outputs and stop conditions. Do not invent hypotheses, controls,
  convergence studies or validation evidence to fill a form.
- `design_mode: research`: a new physical model, research question or genuinely
  unresolved parameter selection. Read [scientific design](references/scientific-design.md)
  and [numerical policy](references/numerical-parameter-policy.md) only for this work.
  Old records without `design_mode` retain research validation.

`user_specified` parameters can be approved for execution without convergence
evidence. Record the supplied value and source and state “用户指定、精度未验证”.
Do not label these parameters `validated`, automatically add convergence tasks,
or infer `scientifically_accepted` from user approval.

## Prepare, then review once

1. Discover the project, read applicable AGENTS.md and reuse existing files/decisions.
   For new projects read [workspace layout](../dft-contracts/references/workspace-layout.md).
2. Design the complete task tree and all determinable inputs in `execution_plan.tasks[]`.
   Record future dependencies as recipes, never fabricated outputs.
3. Validate the design and use workflow `initialize --draft` to initialize all
   executable leaves before review. There is one workflow.json per executable leaf.
4. Present one compact parameter/source table and unresolved issues; obtain
   one user scientific-parameter approval. The requested execution scope must be clear:
   preparing or diagnosing alone never authorizes production submission.
5. Append the real approval event and use workflow `bind-approval`; it checks the
   reviewed current inputs without overwriting them. Subsequent authorized submissions
   require no repeated user approval. Already approved designs retain the old initialize path.

## Records and authority

Registered routes keep docs/plan.md, docs/calculation_design.json and append-only
docs/history.jsonl. Update that one plan and stable sections; Git preserves old text.
Legacy plans/<composition>/<structure>/README.md and sibling JSON/history stay supported.
README files explain purpose and navigation rather than repeat the plan.
The JSON records live design and task intent; approval events preserve immutable evidence.

Current on-disk inputs are authoritative. Hash mismatch triggers reconciliation, not
re-approval. Adopt ordinary user changes and update affected plans; preserve running
snapshots. Escalate only major conflicts, pausing only the affected branch.
Completed unexpected results stay intact; workflow creates a derived rerun candidate.
Before scientific rework, record a change ID, trigger/evidence, old/new parameters,
affected tasks, reusable inputs with reasons, acceptance and a bounded stopping rule.
Use project rework-impact; unresolved compatibility blocks reuse. New work does not
automatically replace selected results. Stage numbering aids reading, dependencies
govern execution; optional execution task directory places nested scans within a stage.

## Conditional references

- Writing/validating JSON or approval events: [design contract](references/design-contract.md).
- Engine envelope or cross-engine question: [engine contract](references/engine-contract.md).
- Domain tasks only: [defects/surfaces](references/defects-surfaces-interfaces.md),
  [NEB](references/migration-neb.md), [phonons](references/phonon-thermodynamics.md),
  [EPC/Tc](references/epc-tc.md).
- Wannier model or fitting parameters only: use `dft-wannier`.
- Use `scripts/computation_design.py --help` for validate/approve/render interfaces;
  do not read its implementation for normal operation.

## Compatibility only

`bootstrap` is compatibility only for older design records. Do not silently migrate,
rename or rewrite legacy approvals. New task mode shares the existing records,
not a second workflow system.
