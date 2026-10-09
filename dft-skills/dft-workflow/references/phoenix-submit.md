# Phoenix submission routing

Use the available `dft-submit` skill for Phoenix/YQH CPU/GPU templates,
environment selection, launcher conventions and current node-specific constraints.
This workflow does not keep a second Phoenix submission policy.

The project and user request determine the writable calculation path and execution scope.
Do not infer H100 compatibility from an A100 template or an old software inventory.
If relevant verification is missing, report that gap; do not automatically install software
or submit a validation job. The workflow records the chosen script, immutable attempt and
scheduler receipt through its normal [submission interface](submit-review.md).
