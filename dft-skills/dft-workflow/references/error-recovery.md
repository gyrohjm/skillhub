# Error Recovery

Recovery is a workflow decision recorded in the affected leaf's one
`workflow.json`. The reconciler and deterministic dependency program run first;
a professional Agent is consulted only when the evidence is inconclusive. The
user is involved only when a major conflict or scientific parameter revision is
needed.

## Technical failure: same-leaf recovery

Technical failure retries in place. Typical cases include scheduler rejection,
MPI startup, memory or walltime failure, module/path/permission errors,
transient file errors, and a known numerical stability repair that does not
change the approved scientific problem.

1. Keep the original task identity and directory.
2. Select the next free `attempts/attempt-NNN/` directory and create its
   manifest atomically; refuse an existing attempt directory.
3. Preserve only the declared files that will be replaced: engine inputs,
   the script resolved from `job.script`, scheduler stdout/stderr, and the pre-repair `workflow.json`.
4. Record the reason, evidence, parameter/reconciliation status, and prior
   hashes in the attempt manifest.
5. Apply an envelope-safe technical repair in the live leaf and update its
   `workflow.json` before the next scheduler call.
6. Reconcile current on-disk inputs, rerun the dependency/resource gates, and
   submit the next immutable snapshot without repeated user approval.

The repair must not silently change KPOINTS, cutoff, pseudopotential, structure,
magnetic order, smearing, charge, SOC, convergence policy, or another
scientific parameter. If such a change is necessary, pause for design review
and a major-conflict decision. Do not delete or overwrite the archived attempt.

## Scientifically unexpected completion: new lineage

Scientifically unexpected completion creates a `rerun_NNN` branch. This applies
when scheduler and artifact gates complete but the target magnetic state,
phonon behavior, EPC, band result, defect ordering, or another scientific
expectation is not resolved.

1. Keep the completed source leaf, outputs, and `workflow.json` byte-for-byte
   intact.
2. Select the next free sibling name (`rerun_001`, `rerun_002`, ...).
3. Copy only declared current inputs and the job template into the new leaf;
   do not copy completed outputs as if they were new evidence.
4. Reset scheduler and completion fields in the new ledger and record
   `lineage.derived_from`, the reason, and every parameter change.
5. Let a professional Agent choose same-parameter rerun within the approved
   boundary. A changed physical model or invalidated result requires a user
   scientific design decision.

This branch is not a technical retry and never replaces the source result.

## Deterministic and Agent verdicts

The deterministic program emits exactly:

```text
ADVANCE | RETRY_IN_PLACE | NEEDS_AGENT | MAJOR_CONFLICT
```

Only `NEEDS_AGENT` is sent to the professional Agent. Its exact verdicts are
`advance`, `retry_in_place`, `rerun_same_parameters`,
`request_parameter_revision`, and `block`; the verdict, evidence, and reason
are recorded in `workflow.json`. `request_parameter_revision` and an unresolved
`MAJOR_CONFLICT` pause the affected branch for the user.

## Recovery boundaries

- `workflow.json` remains the sole live leaf ledger; no parallel retry or parse
  state file is introduced.
- A submitted/running attempt remains bound to its immutable snapshot even if
  the current working input is edited.
- Scheduler completion, artifact completion, and scientific acceptance remain
  separate: `scheduler_complete`, `artifact_complete`, and
  `scientifically_accepted`.
- Stop after the approved retry bound and report the evidence; do not invent a
  scientific parameter or environment.
- If the ledger or snapshot cannot be written atomically, do not submit a new
  job.

## Quantum ESPRESSO / EPW coarse-grid consistency

For an EPW Wannierization or electron--phonon interpolation stage, the NSCF
wavefunctions must represent the **full, uniform coarse k-grid** that EPW is
configured to read. The numerical grid dimensions alone are not sufficient:
an ordinary symmetry-reduced QE NSCF run can report only irreducible k-points
and fail in EPW with `inconsistent nscf and elph k-grids`.

Before running `epw.x`, compare the intended dimensions in the EPW input
(`nk1`, `nk2`, `nk3`) with the k-point count written by the upstream NSCF. For
a Gamma-centered grid, the expected full-list count is `nk1*nk2*nk3`. If the
NSCF output is symmetry reduced, preserve the approved mesh dimensions and
make the representation full-BZ in the next technical retry by adding to the
QE NSCF `&SYSTEM` namelist:

```text
nosym = .true.
noinv = .true.
```

Then rerun the NSCF and recheck that the emitted list has the expected full
count before launching EPW. Treat this as an interface-format repair, not a
scientific k-mesh change, provided the mesh dimensions, shift, structure,
pseudopotential, cutoffs, occupations, and other approved physics remain
unchanged. Preserve the failed NSCF/EPW evidence in the attempt snapshot; do
not reuse its symmetry-reduced wavefunction set.

## Compatibility only

The legacy `vwf` classification and `recovery_attempts/` paths remain readable
for existing task bundles. They are compatibility-only recovery surfaces. New
v2 tasks use `attempts/attempt-NNN/`, immutable snapshots, and the lineage rules
above.
