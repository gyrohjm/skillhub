---
name: dft-submit
description: Prepare and submit authorized DFT jobs, adapt cluster resources and software launchers, and migrate or resume calculations using machine-local environment profiles.
---

# DFT Submission

For DFT project work, read the applicable AGENTS.md and project storage_role; MEMORY.md belongs to the local planning side.
Before saving documents or handing off decisions, follow
[project records](../dft-contracts/references/project-records.md) for fixed paths,
names and evidence-linked memory. Environment details stay in private local profiles.

For paired local/cluster projects, read [paired projects](../dft-contracts/references/paired-projects.md) before preparing inputs, writing analysis or transferring results.



Own cluster, resource, template and launcher conventions. Scientific inputs belong to
`dft-design`; task state and receipts belong to `dft-workflow`. Read the shared
[workspace layout](../dft-contracts/references/workspace-layout.md) for new projects.

## Read local environment information

Resolve the private directory through [local environment storage](../dft-contracts/references/local-environment.md).
Read its `dft-submit/references/clusters.md` and only the notes needed for the selected
cluster/software. Existing private notes retain their relative links and template paths.
Templates live at `<private-dir>/dft-submit/assets/templates/`, not in this public skill.
Use `profiles.json` for code-readable defaults. Missing configuration requires explicit
paths/resources or provisioning the local profile; do not invent accounts or addresses.
Private notes may contain historical authorization. Current task scope determines permission.

## Prepare and submit

1. Reuse the selected environment and existing user-edited scripts. Apply resource
   preferences from the local notes or explicit request. Verify only facts needed by this task.
2. Copy a software-named template such as `vasp.sh` or `qe.sh` into the authorized
   calculation directory without overwriting an existing script. Keep logs and scratch
   there. Do not modify remote templates or install software merely to prepare a job.
3. Match MPI ranks, threads, binding and Slurm allocation to the actual compute nodes.
   GPU/CPU and single/multi-node validation are separate; an old template is not evidence
   of compatibility. Tune only when needed using a representative workload.
4. Run `bash -n`; use `sbatch --test-only` when resource configuration needs validation.
   Neither command establishes scientific acceptance or production submission.
5. For an authorized ready leaf, use workflow's canonical `submit` command once so it
   records the actual script, immutable attempt and scheduler receipt. For explicitly
   authorized standalone jobs use `sbatch --parsable <script>` from the calculation directory.
   An ambiguous response requires reconciliation before another submission.
6. Use targeted scheduler checks and engine output to distinguish scheduler completion,
   artifact completion and scientific acceptance. Record evidence, not inferred success.

Use [migration](references/migration.md) for cross-cluster continuation. Keep the source
calculation and its records intact. Credentials remain in SSH-managed storage. Do not
copy private environment details into public docs, shared skills or project memory.
