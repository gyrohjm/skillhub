# VASP Backend

Status: `operational`. Helper package: `scripts/vwf`.

Use `scripts/canonical_workflow.py prepare` for a new-layout leaf. It verifies
the `history.jsonl#event_id`, exact VASP values, canonical path, approved project
job profile, and single `workflow.json`. `vwf` writing commands remain
legacy-layout-only.

Read only the detailed references needed for the task:

- structure lookup/transformation: `structure-research.md`;
- complete input review: `input-review.md`;
- INCAR presets: `incar-templates.md`;
- POTCAR selection/licensing: `potcar-policy.md`;
- mandatory submit review: `submit-review.md`;
- cluster resources: `cluster-profiles.md` and `phoenix-submit.md`;
- finite displacement: `fd-worker-queue.md`;
- VASP/Slurm/Wannier90/phonopy errors: `common-errors.md`;
- bounded recovery: `error-recovery.md`;
- relax confirmation gate: `iterative-relax-gate.md`.

VASP-specific invariants:

- Review exact `POSCAR`, complete effective `INCAR`, `KPOINTS`, POTCAR labels,
  safe metadata/hashes, executable/module stack, Slurm resources, and task count.
- Never commit licensed POTCAR content to a public repository.
- Keep `POSCAR-ini` immutable for relax tasks and snapshot each continuation
  attempt before `CONTCAR -> POSCAR`.
- Require ionic convergence plus the configured confirmation gate before SCF.
- Use symlinks for reviewed `CHGCAR`/`WAVECAR` reuse where appropriate.
- Treat any schema-v1 `vasp_stage_envelopes` approval as engine `vasp`; reject a
  schema-v2 envelope selecting another engine before writing task inputs.
- Canonical preparation requires exact pre-reviewed `POSCAR`, `INCAR`,
  `KPOINTS`, and `POTCAR` sources inside the workspace. It does not create
  scientific defaults, select POTCAR labels, submit, or run VASP.
