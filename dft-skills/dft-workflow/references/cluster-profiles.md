# Cluster profile lookup

Cluster facts and submission conventions are owned by the installed `dft-submit`
skill. Resolve it through the active skill catalog; read only the selected cluster and
software references. Do not maintain a second cluster inventory here.

Use the current task's explicit cluster/path and the existing template or project resource
profile. Preserve user edits. Missing information requires a targeted check, not a default
scan of queues, nodes, modules or storage. Cached checks and profile I/O are described in
[resource cache](resource-preflight.md) and [job profile format](job-profiles.md).

## Compatibility only

Existing private `cluster-profiles.local.md` and `docs/project-resources.md` are readable
project evidence, not blanket authority or a reason to recreate inventory on every run.
Historical Phoenix/G3 notes do not override dft-submit's verified target configuration.

Resolve machine-local profiles and notes via [local environment storage](../../dft-contracts/references/local-environment.md). Existing private notes belong outside the repository.
