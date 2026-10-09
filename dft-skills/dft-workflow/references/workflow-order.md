# Canonical workflow order

The design's `execution_plan.tasks[]` defines scientific dependencies; directory
numbers only show that order.

```text
prepare complete draft tree and all determinable inputs
-> one user scientific-parameter approval
-> bind-approval without regenerating inputs
-> submit (reconcile -> dependency gate -> cached checks -> snapshot -> receipt)
-> monitor and interpret only the outputs needed for the next step
```

Program first, professional Agent second, user only for a major conflict.
No independent Agent preflight is needed before the submit command.

Draft leaves are `planned`, with no approval. Binding a real reviewed event changes
them to `prepared` or `awaiting_upstream`. It must check the exact current inputs,
task identity and reviewed scope; it must not approve by modifying filenames or old hashes.
Already-approved designs can initialize directly without using drafts.

The gate returns `ADVANCE`, `RETRY_IN_PLACE`, `NEEDS_AGENT` or `MAJOR_CONFLICT`.
Advance requires declared artifacts, compatible identity and appropriate upstream
completion evidence, not simply a terminal scheduler state. Future artifacts are recipes,
not missing files to invent. An unresolved dependency pauses its downstream branch.

The normal execution states are `prepared/awaiting_upstream -> submitted -> running
-> completed/inconclusive/failed`. Keep `scheduler_complete`, `artifact_complete`
and `scientifically_accepted` independent. Executing user-specified parameters does
not establish convergence accuracy. Record only conclusions supported by actual evidence.

Technical failure retries in place after archiving replaced evidence.
Scientifically unexpected completion creates a `rerun_NNN` branch with
`lineage.derived_from`; preserve the complete source.
Raw outputs remain in task leaves; derived data/reports belong in structure analysis.
Manager logs are optional views, not another readiness gate.
Cluster/resource/launcher conventions come from `dft-submit`.

## Compatibility only

Old v1 state bundles and legacy stage names remain readable. They do not define new
approval requirements or permit duplicate live task ledgers.
