# Job profile data interface

`dft-submit` chooses the existing environment/template and launcher convention.
This document describes the compatible profile representation consumed by the workflow,
not a second resource review or benchmark procedure.

Existing `docs/project-resources.md` contains a marked `dft.project-resources.v1`
JSON block between `<!-- dft-workflow:profiles:start -->` and
`<!-- dft-workflow:profiles:end -->`. Its `profiles` mapping identifies reusable
configurations. Do not generate a per-leaf copy of that resource document.

The current renderer accepts `status: approved`, engine, software, partition,
nodes, ntasks_per_node, cpus_per_task, environment, executable and launch_template.
Optional fields include ntasks, qos, account, nodelist, gres, pre_commands and walltime.
With a complete supplied `job_script`, renderer-only nodes/ntasks_per_node/cpus_per_task
and launch_template fields are not mandatory. The selected complete script is copied,
not reconstructed. These values describe execution configuration, not scientific acceptance.
dft-submit determines defaults, MPI layout and whether any optional directive applies.

Environment uses either `method: modules` with the exact module list/module_init/purge,
or `method: source-script` with `source_command`. Older availability_probe,
verify_command and documentation_url fields remain readable. Normal cache reuse does
not repeat module inventories. Never select a new executable just because activation failed.

`launch_template` supports `{executable}`, `{primary_input}`, `{primary_stem}`.
Do not replace an existing selected complete script with a reconstructed launcher.
In execution tasks `job_script` may name the workspace-relative source script;
the leaf records its actual path in `job.script`. Old `job.sh` remains supported.
There is no universal bare-srun or ph.x launch-argument policy in this workflow.

Preparation performs local validation and preserves inputs without environment probes.
Submission uses [cached technical checks](resource-preflight.md) and
[durable receipts](submit-review.md), with no repeated human resource review.
Ordinary user resource edits update the applicable profile and invalidate only related
technical evidence; they do not automatically reopen scientific parameter approval.
