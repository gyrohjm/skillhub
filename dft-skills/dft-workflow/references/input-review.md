# Current-Input Reconciliation

This reference defines the input check immediately before preparation,
submission, or retry of a v2 task. The initial scientific-parameter approval
belongs to `dft-design`; this step keeps the current files and the live ledger
consistent without creating a new approval for an ordinary edit.

## Authority and invariant

Current on-disk inputs are authoritative. The authority order is:

1. current engine files and submission script on disk;
2. the synchronized `calculation_design.json`;
3. the current leaf `workflow.json` snapshot;
4. historical approval events and old hashes.

Hash mismatch triggers reconciliation, not re-approval. A hash is a detection
and provenance value, not a mechanical lock. A file marked `user_override` is
parsed, preserved, and recorded; the Agent never restores an older whole file.

## Reconciliation steps

1. Identify the exact composition, structure, task/variant, engine, design
   event, matrix ID, and leaf `workflow.json`.
2. Parse the current `POSCAR`, `INCAR`, `KPOINTS`, `POTCAR`, Quantum ESPRESSO
   input, declared restart files, and submission script as applicable.
3. Compare normalized semantic parameters with the latest synchronized design,
   separating scheduler fields under `execution.*` from scientific fields.
4. Record each changed name, old value, current value, impact class, previous
   hash, current hash, detection time, and input authority in `workflow.json`.
5. Adopt non-major changes inside the approved boundary. Rebuild only
   unsubmitted generated descendants affected by a propagating change.
6. For a submitted or running task, preserve its immutable attempt snapshot and
   mark the current edit `pending_override` for a later attempt.
7. For a completed task, preserve its outputs and create a rerun lineage when
   the current parameters make the result scientifically unexpected or invalid.
8. For a major conflict, preserve the user's file, pause the affected branch,
   and report the exact impact for a scientific decision.

The stable result is:

```json
{
  "status": "synchronized | adopted | propagated | pending_override | major_conflict | needs_agent",
  "verdict": "ADVANCE | MAJOR_CONFLICT | NEEDS_AGENT",
  "changed_parameters": [
    {"name": "ENCUT", "old": 520, "new": 600, "impact": "L2"}
  ],
  "affected_tasks": ["p2_scf"],
  "current_parameter_hash": "sha256:..."
}
```

## Impact classes

- `L0`: execution settings such as resources, modules, and executable path.
- `L1`: local numerical controls such as `NELM`, mixing, or output switches.
- `L2`: propagating scientific values such as `ENCUT`, smearing, k/q meshes,
  and convergence thresholds.
- `L3`: changes to functional, pseudopotential family, engine, composition,
  atom order, magnetism, SOC, charge, constraints, symmetry, or task graph.
- `UNKNOWN`: syntax or meaning is not safely classified; return
  `NEEDS_AGENT`, not an automatic major conflict.

Engine adapters perform the semantic classification. VASP `NELM` is normally
L1 and `ENCUT` L2; QE `electron_maxstep` and `mixing_beta` are normally L1,
while cutoffs, occupations, smearing, and k meshes are normally L2. Changes to
the physical model or identity of the structure/pseudopotentials are L3.

## File-specific review

For each current file record source, authority, hash, and the semantic fields
that were actually parsed.

- `POSCAR`: lattice, elements, counts, order, coordinate mode, constraints,
  and source structure/relaxation artifact.
- `INCAR` or QE input: complete effective parameters, units, defaults, and
  inherited versus stage-specific settings.
- `KPOINTS` or QE k mesh: mesh/path, centering, generator, and units.
- `POTCAR` or UPF: functional, labels, exact private registry identity, and
  hash; never copy licensed contents into a public record.
- Script resolved from `job.script`: profile identity and execution fields only; it is not a
  scientific parameter file.

Formatting or comment-only changes have no semantic parameter impact but still
refresh the current file hash. User-edited files are never rewritten by
reconciliation. When automatic propagation is needed, only fields with no
semantic conflict may be changed in generated, unsubmitted descendants.

## Completion and snapshot boundary

The current leaf keeps one `workflow.json` with separate
`submission_snapshot`, `scheduler_complete`, `artifact_complete`, and
`scientifically_accepted` records. A submitted or running snapshot remains
immutable even when the working-tree input changes. Reconciliation must finish
before the dependency gate, resource gate, or scheduler call; a failed ledger
update stops the operation before submission.

## Compatibility only

Legacy input-review checklists and v1 approval hashes remain readable for
existing trees. They do not override current files and are not the recommended
v2 reconciliation contract.
