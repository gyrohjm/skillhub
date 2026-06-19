# Error Recovery

Automatic recovery is optional. Use it only when the user asks for automated
handoff or retry behavior, and keep it explicit, logged, and bounded.

## Preferred Helpers

- `custodian`: preferred wrapper for common VASP runtime errors and controlled
  restarts. Use it inside `job.sh` when available, so many known VASP failures
  are handled during the allocation instead of waiting for cron.
- `pymatgen`: parse VASP inputs/outputs, validate structures, inspect INCAR,
  KPOINTS, POTCAR metadata, and convergence evidence.
- `ase`: lightweight structure checks and file conversion.
- `phonopy`: validate phonon displacement/supercell inputs and force sets.

If these packages are missing, ask the user to install or activate a Python
environment before enabling automated correction.

For concrete Slurm, VASP, Wannier90, and phonopy failure signatures, read
`common-errors.md` before proposing parameter or resource changes.

## Recovery Rules

- Default is no automatic recovery.
- Set `auto_recover=true`, `max_retries`, and a `recovery_strategy`
  (`classify` or `command`) per stage only after user approval.
- Recovery commands must write stdout/stderr to the stage directory and be
  recorded in `automation/automation.log`.
- A recovery command may restart from approved files, remove known-corrupt
  `WAVECAR`/`CHGCAR` when approved, or run custodian/pymatgen diagnostics.
- A recovery command must not silently change KPOINTS, ENCUT, POTCAR, structure,
  magnetic order, smearing, or other scientific parameters outside the approved
  review envelope.
- General relax defaults are fixed at `EDIFF=1E-6` and `EDIFFG=-0.01`; SCF
  defaults are fixed at `EDIFF=1E-7`. Automatic recovery must not tighten or
  loosen these values unless the current review envelope explicitly approved
  that parameter change.
- Stop after `max_retries`; mark the stage `blocked` and wait for Agent/user
  review.

## Built-in Classification Engine (`recovery_strategy: classify`)

`vwf` ships a conservative engine that turns a parsed failure (from `vwf parse`)
into exactly one envelope-safe action. It is the default when no
`recovery_command` is configured. It never edits scientific parameters; every
condition whose only real fix is a scientific or resource change is mapped to
`block` with a recommendation. The action table and per-stage `recovery_actions`
allow-list are documented in `automation-cron.md` (Recovery). Behavior summary:

- Safe actions it may run: `restart_from_contcar` (continue a relax from its own
  latest `CONTCAR` geometry), `restage_inputs` (re-pull a declared `inputs_from` file
  such as CHGCAR), `resubmit` (transient/walltime with no restart geometry yet).
- Always blocks for review: out-of-memory, missing VASP/module, ZHEGV/LAPACK
  numerical failures, and electronic non-convergence (these need ALGO / NELM /
  mixing / resource / NCORE-KPAR decisions).
- Before each retry it moves the prior `OUTCAR/OSZICAR/vasp.out/vasp.err` into
  `recovery_attempts/attempt-N/`. For relax continuations it also preserves
  `CONTCAR`, so the exact geometry and debug output for every unconverged
  attempt remain available.
- `restart_from_contcar` copies the latest `CONTCAR` to `POSCAR`, then archives
  the prior attempt files before the next run. It must not overwrite
  `POSCAR-ini`, the initial approved structure backup.
- Use `recovery_strategy: command` + `recovery_command` when you need a richer,
  user-owned repair (e.g. a custodian run); the engine and the command path are
  mutually exclusive per stage.

## Common Recovery Categories

- Walltime or node failure: resubmit from existing approved inputs; preserve
  outputs and append an event note.
- Electronic non-convergence: prefer custodian diagnostics. Any change to
  ALGO, mixing, smearing, ENCUT, KPOINTS, or MAGMOM needs explicit approval.
- Ionic non-convergence: continuation from `CONTCAR` can be pre-approved for
  relax only; changing POTIM, IBRION, ISIF, constraints, or force thresholds
  needs explicit approval.
- Do not advance to SCF just because `CONTCAR` exists. Use the parser/review
  convergence verdict; a one-step final continuation is only supporting
  evidence.
- Corrupt restart files: deleting `WAVECAR` or `CHGCAR` may be safe only when
  the stage review says those files are disposable for that task.
- Phonon FD failures: retry the failed displacement first. Do not regenerate the
  displacement set unless the relaxed structure, phonopy settings, and hashes
  remain inside the approved envelope.
