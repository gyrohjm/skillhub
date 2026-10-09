# Resource cache interface

`.dft/resource-profile.json` is the project cache. Resource selection, cluster facts,
templates and launcher conventions belong exclusively to the available `dft-submit`
skill. This reference defines the workflow's technical cache interface, not another review.

Preparation creates directories and inputs without live environment probes. Before actual
submission, the adapter reuses checks matching cluster, activation, executable and resource
configuration. A scientific input-only change, another task or a new session does not
invalidate a matching entry. Different profiles must not overwrite each other's validity.

On a cache miss the necessary scheduler/partition/activation/executable probes run in
one target-shell invocation. Executable resolution happens inside the activated environment.
The result retains per-check evidence; fewer round trips must not hide a failed check.
Do not perform a broad queue, node, module, storage or account inventory by default.

Run `bash -n` when a submission script's content changes; reuse syntax evidence by
content hash. Use `sbatch --test-only` only for a new template/resource configuration
when needed according to dft-submit. Neither syntax checking nor test-only submits a job.

Invalidate only the relevant environment/resource entry on an explicit change or failure:
missing partition, activation or executable failure, or confirmed environment drift.
Classify scheduler rejection first: input/script, account limit or transient failures are
not proof that the executable/environment changed. Preserve the original error and
do not rerun unrelated probes.

`submit` consumes this cache inside its normal path. Do not run a separate Agent resource
review or manually repeat preflight before calling it. A failed check blocks execution,
notifies only when action is needed, and does not reopen scientific parameter approval.

## Compatibility only

Legacy `docs/project-resources.md` profiles remain readable. Their old discovery or
approval checklist is not the default. Existing cache formats may be upgraded without
treating unverified data as ready.
