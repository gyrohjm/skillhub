# Paired projects

For paired local/cluster projects, stage interpretation lives in the local stage README.
Keep cluster scripts/data/figures with their source task, and publish selected results
to the sole local analysis/main_report.md. See [paired projects](../../dft-contracts/references/paired-projects.md).
The existing single-root conventions follow.

# Report and stage conclusions

workflow.json is the sole live leaf ledger. Keep scheduler_complete, artifact_complete
and scientifically_accepted independent. An executable completion is not result selection.
For task-mode work report the requested observable and precision limitations;
never invent a hypothesis or validated precision.

## One synthesis, local evidence

The only current project main report is results/main_report.md. Update stable sections
by system, research route and scientific question. Its prior versions belong to Git.
Final figures/tables live in results/ and are explicitly published from selected tasks.

Stage conclusions, diagnostics, intermediate data, plots and specialized scripts stay
under the producing task's analysis/. Update analysis/README.md in place, using stable
sections for purpose, evidence, conclusions, limitations and next action. A different
session/date is not a new document identity. Directory READMEs explain contents and
link to the corresponding main-report section rather than repeat the full synthesis.

Use [project records](../../dft-contracts/references/project-records.md): read the fixed
role, retain its hash, document --section with --expected-sha256, then sync/check.
A write conflict means reread/merge, not report_new.md or a replacement main report.

## Evidence to retain

- composition/structure, task UUID, exact scientific revision and execution attempt;
- workspace-relative raw sources, parsed data, figures and analysis script;
- engine/parser version, units, columns, transformations and input hashes;
- design ID/revision and reviewed scope when applicable;
- scheduler terminal state, normal termination, artifact completeness and applicable
  convergence evidence, each separately established;
- observations, uncertainty, failed controls and evidence limitations;
- supported/falsified/inconclusive only where a research hypothesis actually exists;
- current selection, applicability to old/new conditions and any proposed rework.

Validate numeric data before plotting. Keep plot-ready .dat/.csv with units and source
references; a figure alone is insufficient. Follow the plot-style rules, including
axis_plan (xlim, ylim and reason), and visually inspect final exports.

## Failure and rework

Record failure_class (input_preparation, scheduler_resource, runtime_environment,
numerical_convergence, postprocess or unknown), exact diagnostic evidence, root-cause
confidence, missing artifacts, and what remains reusable or unresolved.
Missing evidence is inconclusive; file existence and scheduler COMPLETED are insufficient.

Update the same local analysis README. If proposing parameter changes, retain name,
old/new values, unit, reason, evidence, affected dependencies, acceptance rule and stopping
bound. Route a machine request through the document tool as report .json/data, rather
than inventing another main report. Ordinary authorized changes use reconciliation;
major scientific conflicts require a decision on the affected scope. A report grants
no execution authority, and the analysis skill never submits or deletes failed evidence.

Scientific rework gets a candidate revision; the old result is not replaced until the
new evidence is accepted and explicitly selected. If old evidence is invalidated,
remove its current-selection claim even when there is no successful replacement.
Record selection through the manager and update the main-report section accordingly.

At handoff update local conclusion, compact workflow evidence, route event log and
relevant main-report section. Publish only the final selected artifacts; retain staged
or failed analysis in its task. Checksummed provenance links the final artifact back
to its task, data and script. Regenerate published files from those sources.

## Compatibility only

Existing structure-level analysis/reports/<task>/<topic>.md remains usable without
relocation. Preserve existing report identities; migrate only with explicit scope and
verified links. Old task-spec change-request helpers keep their explicit legacy paths.
