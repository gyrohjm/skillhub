# Iterative Relaxation Gate

Use this gate for a relax-to-SCF chain unless the approved execution plan
records another policy. It is part of the canonical workflow and is covered by
the one scientific-parameter approval; normal continuation does not prompt for
another approval.

## Required loop

1. Keep the approved starting structure as immutable `POSCAR-ini` and record
   its hash in the leaf `workflow.json`.
2. Run the relax with the reviewed inputs and the project resource profile.
3. Parse the attempt. Require normal engine termination, electronic evidence,
   and formal ionic convergence; a scheduler success state or an existing
   `CONTCAR` alone is insufficient.
4. For a technical failure or continuation, preserve every file that will be
   replaced under the next `attempts/attempt-NNN/` directory. Record the
   manifest, hashes, reason, and prior `workflow.json` before changing the
   active leaf.
5. Copy the latest valid `CONTCAR` to active `POSCAR` when the approved
   continuation policy allows it. Never modify `POSCAR-ini`.
6. Run the fresh confirmation relax with identical scientific parameters. The
   reconciler runs first if a current input changed.
7. Advance to SCF only when the fresh run terminates normally, satisfies the
   formal ionic-convergence criterion, and contains exactly one completed ionic
   step. Use its `CONTCAR` as the SCF `POSCAR` and record the source hash.
8. If the fresh run uses more than one ionic step, repeat within the reviewed
   `max_relax_cycles`. A technical failure retries in place; do not silently
   change scientific inputs.

The leaf remains the same for technical recovery. If a completed result is
scientifically unexpected, preserve it and create the next `rerun_NNN` branch
instead of treating it as a failed relax.

## Review and workflow fields

The design and leaf ledger record:

```json
{
  "iterative_relax": true,
  "require_formal_ionic_convergence": true,
  "require_fresh_one_step_confirmation": true,
  "max_relax_cycles": 10,
  "attempts_path": "task_root:attempts",
  "scf_structure_source": "final one-step confirmation CONTCAR"
}
```

`max_relax_cycles` is a reviewed recovery bound. Automation may continue
inside the approved scientific and resource envelope without repeated user
approval. A major scientific conflict pauses the affected branch
for reconciliation and, where needed, a user decision.

## Completion distinction

Record `scheduler_complete`, `artifact_complete`, and
`scientifically_accepted` separately in the same `workflow.json`. Scheduler
completion does not establish a valid `CONTCAR`, and a valid `CONTCAR` does not
establish scientific acceptance.

## Compatibility only

The older `recovery_attempts/attempt-N/` naming is readable for existing relax
trees. New v2 leaves use `attempts/attempt-NNN/` and the single workflow ledger.
