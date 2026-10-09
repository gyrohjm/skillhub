# DFT Skill Ownership Contract

The workspace layout is shared in
[workspace layout](../../dft-contracts/references/workspace-layout.md).
workflow.json is the sole live leaf ledger; all logs, dashboards and exports are derived.

- `dft-design`: exact parameters, sources, task graph and one initial review.
  Routine task mode does not require a research proposal.
- `dft-workflow`: prepare inputs, bind real approval, dependencies, submission
  receipts, monitoring and bounded recovery.
- `dft-submit`: cluster/environment, resource allocation, templates and launcher policy.
- `dft-wannier`: fitting diagnostics, candidates and electronic-model evidence;
  not a second scheduler or live ledger.
- `dft-analysis`: parse/validate results, figures, interpretation and evidence-linked requests.
- `dft-work-manager`: reference-driven paired initialization, record consistency, selection, final-result return and explicit export.
  Neither analysis nor manager is required merely to prepare a calculation.
- `dft-research-ideation`: literature-backed ideas only when a research question calls for them.

Prepare the full known tree and determinable inputs before parameter review.
A draft cannot submit. Once the real event is bound, the authorized graph runs
without repeated user approval. User edits take precedence over old hashes;
ordinary changes update plans, major conflicts pause only affected branches.

Technical failure retries in place after archiving replaced evidence.
Scientifically unexpected completion creates a `rerun_NNN` branch (nested in
revisions/ for registered routes) and records
`derived_from`; completed outputs are never overwritten or moved just because
they disagree with expectations. Movement/export/deletion requires explicit scope.
Existing legacy records remain readable and are not automatically migrated.

Fixed documents, explicit selection, screening, publication and Git rules are owned
by the shared [project records](../../dft-contracts/references/project-records.md).
The manager reads scientific acceptance evidence; it does not manufacture acceptance.
