# Experimental Design Checklist

Use this reference when project mode is `experimental` or `hybrid`.

## Minimum Design

- Define the target phenomenon and measurable response.
- Define independent variables and planned levels.
- Define negative, positive, baseline, and process controls where applicable.
- Identify nuisance variables and how they will be controlled, randomized, blocked, or recorded.
- Define biological/technical replication and distinguish them clearly.
- Define sample inclusion, exclusion, and failed-run rules before collecting production data.
- Define instrument calibration, standards, blanks, and quality-control samples.
- Define units, uncertainty, detection limits, and metadata captured per run.
- Define the statistical or physical analysis before choosing the final sample count.

## Experiment Matrix

For every experiment record:

```text
experiment_id | hypothesis | variable_set | controls | replicates |
measurement | acceptance | failure_action | expected_output
```

Start with the smallest discriminating pilot. Promote a pilot to production only after its measurement and quality-control behavior are reviewed.

## Stop and Decision Rules

- Stop when the predefined acceptance criterion is met with adequate replication.
- Stop or redesign when controls fail, calibration drifts, measurements saturate, or the hypothesis cannot be distinguished from alternatives.
- Do not change exclusion criteria after viewing outcomes without recording the decision and rationale.
- Record protocol changes in `docs/records/decisions.md` and task execution in `docs/records/task_logs/`.
