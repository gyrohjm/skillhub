---
name: dft-analysis
description: Use when DFT outputs need convergence checks, evidence-linked analysis, scientific figures or failure diagnosis. Not required just to prepare inputs or submit an already approved task.
---

# DFT Analysis

For DFT project work, read the applicable AGENTS.md and project storage_role; MEMORY.md belongs to the local planning side.
Before saving documents or handing off decisions, follow
[project records](../dft-contracts/references/project-records.md) for fixed paths,
names and evidence-linked memory. Environment details stay in private local profiles.

For paired local/cluster projects, read [paired projects](../dft-contracts/references/paired-projects.md) before preparing inputs, writing analysis or transferring results.



Own extraction, interpretation and diagnostic recommendations, not input mutation,
submission, technical recovery or cleanup. workflow.json is the sole live leaf ledger.
Read the source leaf and applicable project instructions, not the complete upstream
design/review history again. For a new layout consult
[workspace layout](../dft-contracts/references/workspace-layout.md).

## Results first

Use `assess_completion` / `scripts/analysis_decision.py completion` before accepting
outputs; use `diagnose_failure` / `analysis_decision.py diagnose` for failures.
Keep these facts independent:

- `scheduler_complete`: scheduler terminal success only.
- `artifact_complete`: required files and parser/engine evidence are complete.
- `scientifically_accepted`: applicable scientific criteria are met.

User-specified parameters without convergence evidence may have run successfully
while their precision remains unverified. Do not invent acceptance or a hypothesis
for a routine task. Missing/ambiguous evidence remains `inconclusive`.

## Conditional work

- Parsing: [engine adapters](references/engine-adapters.md).
  `scripts/parse_result.py --task-dir <leaf> --engine auto`.
- Numeric extraction: [data contract](references/data-contract.md).
  Preserve source/version, units, columns and transformations; validate data before figures.
- Figures only: [plot style](references/plot-style.md) and
  [plot catalog](references/plot-catalog.md). Apply proportional typography,
  legend layout and boundary-tick rules; dispersion plots also require a
  sample-only companion. Specify final `--xlim` and `--ylim` and visually inspect exports.
- Diagnosis: [failure handoff](references/failure-diagnosis.md).
- Report: [report format](references/report-format.md).
- EPC/Tc only: [EPC analysis](references/epc-tc-analysis.md).
- Defects/surfaces only: [domain analysis](references/defects-surfaces-interfaces.md).
- Wannier fitting only: `dft-wannier` owns fitting/model validation.
  Electronic interpolation acceptance does not establish EPC/Tc acceptance.

Keep raw engine outputs in the source leaf. Registered routes keep intermediate
data, plots and analysis scripts in task-local analysis/; update analysis/README.md
in place. Existing structure-level analysis remains compatible. Reusable tools live
under `<workspace_root>/code/`; existing `<structure_root>/scripts/` remains usable.
Update stable sections of results/main_report.md for the project synthesis; it is the
only current main report. Publish selected final figures/tables with source hashes
through the project tool, not an automatic collection of every intermediate artifact.

Technical failure retries in place through `dft-workflow`, after preserving evidence.
Scientifically unexpected completion creates a `rerun_NNN` branch; do not overwrite
the completed source. Registered routes nest candidates in revisions/rerun_NNN/
under the original task. Normal bounded revisions use current-input reconciliation.
Use rework-impact to identify downstream compatibility reviews; unknown reuse stays blocked.
Major physical conflicts return to `dft-design` and the user. A report does not grant
new execution authority. `dft-submit` owns resource and launcher policy.

Logs through `dft-work-manager` are optional derived views, not another gate.
Scientific reports must retain source pointers and evidence limitations.

## Compatibility only

Legacy v1 workflow/parser records remain readable. Missing v2 evidence is not
silently inferred from filenames or scheduler status.
