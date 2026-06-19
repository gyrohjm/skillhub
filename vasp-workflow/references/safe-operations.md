# Safe Operations

- Do not run production VASP directly on login nodes.
- Do not submit jobs before showing POSCAR/INCAR/KPOINTS/POTCAR provenance and
  resource counts to the user.
- Do not let cron or an automation tick bypass submit review. Automation may
  submit only stages that have a matching approval file or an explicit
  `preapproved_by_workflow: true` entry inside the approved workflow envelope.
- Do not let automatic recovery make unapproved scientific changes. Recovery
  may restart, clean known-bad restart files, or apply pre-approved custodian
  style fixes only when the workflow plan explicitly allows it.
- Do not overwrite existing OUTCAR, OSZICAR, CONTCAR, WAVECAR, CHGCAR, or
  vasprun.xml without explicit intent.
- For relax continuation, preserve each attempt's `OUTCAR` and `CONTCAR` under
  `recovery_attempts/attempt-N/` before the next run can overwrite them.
- Do not overwrite `POSCAR-ini`; it is the initial approved structure backup.
- Do not prepare SCF from a relax `CONTCAR` unless relax convergence has been
  confirmed by parser/review.
- Do not copy SCF `CHGCAR` or `WAVECAR` into downstream electronic tasks; use
  symbolic links so the large restart files have one source of truth.
- Do not change KPOINTS, ENCUT, EDIFF, EDIFFG, ISMEAR, SIGMA, MAGMOM, POTCAR,
  or structures as a performance shortcut.
- Do not cancel jobs without listing exact job ids, owners, and paths.
- Do not clean queue directories with broad globs. Use exact task labels.
- Do not archive or commit licensed POTCAR content into public repositories.
