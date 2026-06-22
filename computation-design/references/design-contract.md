# Calculation Design Contract

The live machine contract is `docs/plans/calculation_design.json`. Keep keys,
schema values, and identifiers in English. Use English `lowercase_snake_case`
for project, system, case, and matrix identifiers. Human-authored field values
and the companion Markdown plan should be Chinese by default; preserve English
technical names and do not duplicate bilingual prose.

## Required Top-Level Fields

- `schema_version`: currently `1`.
- `design_id`: stable lowercase identifier across revisions.
- `revision`: positive integer incremented for scientific changes.
- `status`: `draft`, `ready_for_review`, or `superseded`.
- `project_slug`, `title`, `research_questions`, `hypotheses`, `systems`.
- `observables`, `controls`, `convergence_studies`, `validation_checks`.
- `calculation_matrix`, `vasp_stage_envelopes`, `evidence`.
- `uncertainty_budget`, `resource_budget`, `stop_conditions`,
  `pending_decisions`.

## Entry Contracts

- Hypothesis: `id`, `statement`, `falsification`.
- Observable: `id`, `hypothesis_ids`, `quantity`, `decision_rule`,
  `uncertainty_target`.
- Matrix task: `id`, `class`, `system_slug`, `case_slug`, `hypothesis_ids`,
  `purpose`, `variables`, `fixed_parameters`, `stages`, `observable_ids`, and
  `completion_gate`.
- Evidence: `id`, `claim`, `source`, `kind`, `status`, `supports`; status is
  `verified` or `pending`.
- VASP envelope: `matrix_id`, `structure_source`, `incar_policy`,
  `kpoints_policy`, `potcar_labels`, `resource_profile`, and
  `completion_gates`. It defines scientific intent; `vasp-workflow` still
  generates and reviews the concrete files.

## Approval Contract

Run approval only when the live design is `ready_for_review`, has no pending
decisions, and every scoped matrix entry is complete. Scoped `production`
entries additionally require all evidence to be verified and convergence
studies to contain a selected value.

Approval creates:

```text
docs/records/design_reviews/<design_id>/rNNNN/
  calculation_design.json
  computation_plan.md
  approval.json
```

`approval.json` records the scope, reviewer, UTC timestamp, and SHA256 hashes of
both snapshots. The directory is immutable and cannot be reused.

## VASP Handoff

Pass `approval.json` and one approved matrix ID to `vasp-workflow`. Workflow
must verify both hashes, confirm the matrix ID is in scope, confirm the requested
stage is listed, and record design provenance in its task metadata and submit
review. Design approval never authorizes `sbatch` by itself.
