---
name: dft-workflow
description: "Prepare and run existing DFT tasks: initialize input trees before parameter review, reconcile user edits, resolve dependencies, record scheduler receipts, monitor and recover. Use dft-submit for cluster and launcher conventions. VASP and prebuilt QE are operational; other backends remain contract-only."
---

# DFT Workflow

For DFT project work, read the applicable AGENTS.md and project storage_role; MEMORY.md belongs to the local planning side.
Before saving documents or handing off decisions, follow
[project records](../dft-contracts/references/project-records.md) for fixed paths,
names and evidence-linked memory. Environment details stay in private local profiles.

For paired local/cluster projects, read [paired projects](../dft-contracts/references/paired-projects.md) before preparing inputs, writing analysis or transferring results.



Own input materialization, dependency decisions, execution receipts and recovery.
workflow.json is the sole live leaf ledger. Scientific design belongs to
`dft-design`; cluster, resource, template and launcher conventions belong to
the available `dft-submit` skill. Resolve that skill from the active skill
catalog when preparing a submission script or performing scheduler operations.
Do not assume it is a Python API, duplicate its policy, or launch a second submitter.

## Short path

1. Resolve the project and requested task, read its applicable AGENTS.md and
   existing inputs/plan. For a new layout only, read
   [workspace layout](../dft-contracts/references/workspace-layout.md).
   Reuse current parameters and known templates; do not scan unrelated cases or clusters.
2. Design complete tree and all determinable inputs; initialize all executable leaves
   with `initialize --draft`. Upstream-dependent files remain explicit recipes.
   Drafts are `planned`, unapproved and cannot submit.
3. Obtain one user scientific-parameter approval of current parameters, append the
   real design event, then use `bind-approval` on that tree without regenerating inputs.
   Existing approved designs can still use `initialize --event-id ...`.
4. For an authorized ready task, call `submit` once. It internally reconciles current
   on-disk inputs, runs the deterministic dependency gate, reuses the project resource
   cache and snapshots the actual `job.script` before submitting. Do not repeat these
   checks manually. Submit without repeated user approval.
5. Program first, professional Agent second, user only for a major conflict.
   Consult the Agent only for an inconclusive verdict, not for routine gate success.
   Waiting for upstream output is not a request for another user review.

Current on-disk inputs are authoritative. Hash mismatch triggers reconciliation, not
re-approval. Preserve user overrides; ordinary changes update the plan and affected
unsubmitted descendants. Running snapshots are immutable; new edits apply to later attempts.
For registered routes, pass --route <relative-route> to initialize/bind-approval.
Keep numbered stages directly under the route; optional execution task directory
adds only needed subtask/variant depth. Read route docs/plan.md and shared input
versions before preparing tasks; shared/ is optional, not a mandatory 00_pseudo.
Unknown syntax needs Agent interpretation, not automatic escalation to a major conflict.

## Commands

Resolve `SKILL` from this skill's installed location; supply explicit project paths:

```bash
python "$SKILL/scripts/canonical_workflow.py" initialize --draft \
  --project-root <workspace> --composition <composition> --structure <structure> \
  --design <calculation_design.json>
python "$SKILL/scripts/canonical_workflow.py" bind-approval \
  --project-root <workspace> --composition <composition> --structure <structure> \
  --history <history.jsonl> --event-id <design_id>:r0001
python "$SKILL/scripts/canonical_workflow.py" submit --task-root <executable-leaf>
```

Use the software-named script selected through dft-submit, recorded in
`job.script`. Existing `job.sh` remains valid; never rename or replace it implicitly.
Preparation does not probe the cluster simply to create directories. Do not install
missing software or change the engine/environment to bypass a blocker.

## Results and recovery

Keep `scheduler_complete`, `artifact_complete` and `scientifically_accepted`
independent. User-specified parameters may execute without convergence evidence;
this does not validate their accuracy or accept the scientific result.

Technical failure retries in place after preserving replaced evidence in
`attempts/attempt-NNN/`. Scientifically unexpected completion creates a
`rerun_NNN` branch with `lineage.derived_from`; never overwrite completed outputs.
Registered routes put it inside the original task's revisions/ rather than beside
unrelated stages. Follow [project rework](../dft-contracts/references/project-records.md#rework):
impact analysis, explicit compatibility decisions, immutable inputs, bounded execution,
scientific acceptance and explicit selection. A new branch inherits no selected status.
Update existing plan/log/README and final-report sections at handoff, using stable
IDs and read hashes; run sync/check without auto-committing or creating report copies.
Submission uncertainty requires queue/receipt reconciliation before another scheduler call.

## Read only when needed

- New task/CLI details: [workflow order](references/workflow-order.md) and
  [directory layout](references/directory-layout.md).
- Parameter changes: [input reconciliation](references/input-review.md).
- Submission/cache issues: [receipt interface](references/submit-review.md) and
  [cache interface](references/resource-preflight.md); dft-submit owns policy.
- Relax-to-SCF handoff: [relax confirmation](references/iterative-relax-gate.md).
- Failed/rejected result: [recovery](references/error-recovery.md).
- Unsupported engine: [backend boundary](references/backend-contract.md).
- Wannier fitting only: use `dft-wannier`; its scientific diagnostics do not submit.
- Analysis or record export only when needed: `dft-analysis` / `dft-work-manager`.

## Compatibility only

Legacy `vwf`/`qewf` and `canonical_workflow.py prepare` remain compatibility
only. Their historical checklist and profiles do not define the new short path.
