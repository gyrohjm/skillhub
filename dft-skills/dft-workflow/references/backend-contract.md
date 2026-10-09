# DFT Execution Backend Contract

An operational backend must provide all of these capabilities before production
submission:

1. identify the engine and executable/module stack;
2. validate an approved `dft-design` engine envelope;
3. prepare deterministic input files with source provenance and hashes;
4. prepare draft inputs and bind the real initial parameter review without overwriting them;
5. reconcile user changes and consume dft-submit templates and technical cache evidence;
6. submit, monitor, and record scheduler state without hidden parameter changes;
7. parse termination, electronic/ionic convergence, energy, forces, and known
   failures conservatively;
8. apply only bounded, preapproved recovery actions;
9. write engine/backend identifiers, approved hashes, resources, submission,
   status, and compact parsed result into the leaf's single `workflow.json`;
10. accept an explicit executable leaf under the discovered calculations root
    without deriving a machine-specific or category-specific destination.

Backend status values:

- `operational`: implemented and covered by local tests; execution is allowed
  after normal review and approval.
- `contract-only`: common design, records, and analysis contracts exist, but
  input generation/submission is blocked.
- `disabled`: backend exists but failed validation or was explicitly disabled.

The canonical registry lives in `../dft-contracts/capabilities.json` and is
loaded by `scripts/dft_backend.py`. Do not infer operational
status from the presence of an executable alone.

New backends should be isolated adapters, not conditionals spread through the
core workflow. Add engine-specific references, templates, parser tests, submit
review tests, and a dry-run fixture before changing registry status.
