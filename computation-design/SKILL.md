---
name: computation-design
description: Design scientifically defensible computational experiments and reviewable VASP calculation plans before task preparation. Use when converting research questions into falsifiable hypotheses, observables, controls, convergence studies, validation checks, uncertainty targets, calculation matrices, resource budgets, stopping rules, or approved design revisions. Do not generate VASP inputs, submit jobs, analyze completed outputs, or archive tasks; hand those stages to vasp-workflow, vasp-analysis, and vasp-work-manager.
---

# Computation Design

## Overview

Use this skill as the scientific design layer between project initialization
and calculation execution:

```text
init-research-project -> computation-design -> vasp-workflow -> vasp-analysis -> vasp-work-manager
```

Produce a human-readable rationale in `docs/plans/computation_plan.md` and a
machine-readable contract in `docs/plans/calculation_design.json`. Keep task
generation, Slurm submission, output interpretation, and archiving outside this
skill.

Write human-facing Markdown prose in Chinese by default. Keep code, JSON keys,
schema fields, paths, filenames, commands, units, VASP file names, and technical
parameter names in English. Do not repeat the same content bilingually.

## Required Workflow

1. Read `PROJECT_CONTEXT.md`, `docs/plans/research_plan.md`, the existing
   computation plan, and recorded scientific decisions.
2. Interview the user until the research question, falsifiable hypotheses,
   intended observables, constraints, and decision use are explicit.
3. Read `references/scientific-design.md` and challenge missing controls,
   confounded comparisons, unsupported causal claims, and calculations that
   cannot discriminate the hypotheses.
4. Ask before searching external literature or databases. For a production
   design, verify method and parameter claims against primary papers, official
   documentation, trusted databases, or completed convergence/benchmark data.
5. Read `references/design-contract.md`, then update both design files. Mark
   unsupported statements and unresolved production values explicitly; never
   fabricate them.
6. Run `scripts/computation_design.py validate`. Fix every contract error
   before presenting the design for review.
7. Present hypotheses, controls, task classes, parameter ranges, convergence
   rules, expected observables, validation, uncertainty, resources, and stop
   conditions. Ask the user to approve a named calculation-matrix scope.
8. Only after explicit approval, run `scripts/computation_design.py approve`.
   This creates an immutable hash-locked review bundle; it never marks the live
   plan as approved.
9. Hand the approved matrix IDs and `approval.json` to `vasp-workflow`.

## Scientific Rules

- Separate evidence, user decisions, agent proposals, and values that must be
  selected by convergence.
- Separate exploratory, convergence, validation, and production tasks. Do not
  promote exploratory results silently.
- Give every hypothesis a falsification condition and every observable a
  quantitative decision rule and uncertainty target.
- Vary one interpretable factor at a time unless a factorial design is
  justified. State all fixed conditions needed for comparisons.
- Design convergence against quantities supporting the scientific claim, not
  total energy alone.
- Include baseline and relevant positive/negative controls. If a meaningful
  control is impossible, record the limitation and reduce the claim.
- Production-critical values require verified evidence or completed
  convergence/benchmark results. The agent may propose ranges and rationale,
  but the user approves final production values.
- Keep failures and inconclusive results in the design record. Define stopping
  rules before expanding the matrix.

## Approval and Revision Rules

- Live design status is only `draft`, `ready_for_review`, or `superseded`.
- Approval is a separate record under
  `docs/records/design_reviews/<design_id>/rNNNN/` and is valid only for its
  listed matrix IDs.
- Never overwrite a review bundle. Increment `revision` after any scientific
  change and create a new approval.
- Scientific design approval does not replace `vasp-workflow` input/resource
  review and submission approval.
- A `vasp-analysis` recommendation is evidence, not authorization. Convert its
  `design_change_request.json` into a new design revision, review it, then hand
  the approved scope to `vasp-workflow`.

## Commands

Paths are relative to this skill directory:

```bash
python scripts/computation_design.py bootstrap --project <project_root> --dry-run
python scripts/computation_design.py bootstrap --project <project_root> --apply
python scripts/computation_design.py validate --design <project_root>/docs/plans/calculation_design.json
python scripts/computation_design.py approve --project <project_root> --reviewer <name> --scope matrix_id
python scripts/computation_design.py verify --approval <project_root>/docs/records/design_reviews/<design_id>/r0001/approval.json
```

For an existing project, `bootstrap` creates only missing files and directories.
It never overwrites `computation_plan.md` or `calculation_design.json`.

## Handoffs

- Use `init-research-project` for project framing, directory initialization,
  and data lifecycle rules.
- Use `vasp-workflow` only after a calculation scope has a verified scientific
  design approval; it owns VASP files, submit review, execution, and recovery.
- Use `vasp-analysis` for completed-output extraction and interpretation. Send
  proposed follow-up calculations back here as a design change request.
- Use `vasp-work-manager` to preserve design snapshots, approvals, task records,
  manifests, checksums, and project summaries.

## Reference Map

- `references/scientific-design.md`: hypotheses, observables, controls,
  convergence, validation, uncertainty, resources, and stopping rules.
- `references/design-contract.md`: JSON fields, task classes, evidence states,
  approval bundles, and VASP handoff contract.
- `assets/calculation_design.template.json`: machine-contract bootstrap template.
- `assets/computation_plan.template.md`: human-plan bootstrap template.
