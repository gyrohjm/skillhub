# Submission interface and receipts

The initial parameter approval authorizes the agreed task graph within its execution
scope. Submission is a program operation, not a second human review.
Cluster/template/launcher policy is delegated to `dft-submit`.

Call `canonical_workflow.py submit --task-root <leaf>` once. Internally it:

1. Rejects unapproved drafts and reconciles current input authority.
2. Evaluates dependencies deterministically; unresolved science goes to the Agent.
3. Reuses matching environment and script-syntax evidence.
4. Captures declared input files and the script resolved from `job.script` in an
   immutable `attempts/attempt-NNN/submission_snapshot/`.
5. Calls the scheduler in that leaf, recording exact argv, stdout, stderr and job ID.
6. Persists `sbatch.receipt.json` before updating the live `workflow.json`.

A successful durable receipt with an incomplete ledger must be recovered, not submitted
again. An ambiguous scheduler response must stop for queue/accounting reconciliation;
absence of a parsed ID alone does not prove no job exists. Never auto-cancel a job to
compensate for local persistence failure.

A later working-input edit cannot alter the recorded attempt. If contents change during
preparation for submission, re-evaluate before submitting instead of using stale evidence.
Reject absolute/traversing metadata script paths. Existing `job.sh` is compatible,
but the adapter must not silently replace a declared `vasp.sh` or `qe.sh`.

Keep scheduler completion, artifact completeness and scientific acceptance separate.
Cache failures and technical retries do not reopen parameter approval. Completed
scientifically unexpected results branch with `derived_from`; they are not overwritten.

## Compatibility only

Existing v1 reviews remain historical evidence. Do not generate a second approval,
preflight or task-state JSON file beside the canonical live ledger.
