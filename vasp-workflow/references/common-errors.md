# Common Runtime Errors

Use this reference when reading `OUTCAR`, `OSZICAR`, `vasp.out`, `vasp.err`,
Slurm output, Wannier90 logs, or phonopy logs. Treat every adjustment as either
inside the approved workflow envelope or requiring a new review.

## Triage Rules

- Preserve `OUTCAR`, `OSZICAR`, `CONTCAR`, `vasp.out`, `vasp.err`, Slurm logs,
  and tool logs before retrying.
- Run `python -m vwf parse --task-dir <stage>` for VASP stages when available.
- Classify the failure before changing files. Prefer restart/restage/resubmit
  only when the current review envelope already allows it.
- Any change to POSCAR, POTCAR, ENCUT, KPOINTS, MAGMOM, smearing, force
  threshold, `ALGO`, mixing, `NBANDS`, `NCORE`, `KPAR`, Slurm resources, or
  Wannier/phonopy settings must be shown in a new review unless pre-approved.
- After troubleshooting, hand durable records and archives to
  `vasp-work-manager`.

## Slurm

| Signal | Likely cause | Allowed first action | Review-required adjustment |
|---|---|---|---|
| `DUE TO TIME LIMIT`, `TIMEOUT`, `CANCELLED AT ... DUE TO TIME LIMIT` | Wall time too short. | Preserve logs; resubmit unchanged only if the envelope allows retry. | Increase wall time, split tasks, or alter convergence/stage strategy. |
| `OUT_OF_MEMORY`, `oom-kill`, `Killed`, cgroup memory messages | Memory limit or node layout too small. | Preserve logs and record memory failure. | Change nodes, tasks, `NCORE`, `KPAR`, GPU/CPU profile, or system size. |
| `Invalid partition`, `Invalid qos`, `Invalid account`, `Requested node configuration is not available` | Stale Slurm profile or node/GRES request. | Run read-only `sinfo`, `sacctmgr`, `squeue`, `module avail`. | Change partition/QoS/account/nodelist/GRES/profile. |
| `module: command not found`, VASP command not found | Job shell did not initialize modules or module name is stale. | Inspect job script and shell startup lines. | Change module stack or VASP command. |
| `No space left on device`, quota exceeded, cannot write `WAVECAR` | Storage/quota/scratch problem. | Stop; preserve what exists; check `df -h` and quota. | Move case/archive location or change large-file retention policy. |
| MPI launch failure, PMI/PMIx/ORTE errors | MPI launcher and VASP build mismatch or bad node allocation. | Preserve logs; check module list and Slurm environment. | Change `srun`/`mpirun`, module stack, task layout, or node selection. |

## VASP

| Signal | Likely cause | Allowed first action | Review-required adjustment |
|---|---|---|---|
| Relax reaches `NSW` without convergence | Geometry still moving; run stopped cleanly. | Archive attempt; copy `CONTCAR` to `POSCAR` only inside approved relax continuation envelope. | Change `EDIFFG`, `NSW`, `IBRION`, `POTIM`, constraints, structure, or smearing. |
| `ZBRENT: fatal error in bracketing` | Ionic line search failed, often rough geometry/forces. | Restart from current `CONTCAR` only if allowed; preserve attempt files. | Change optimizer, `POTIM`, constraints, structure, or force criteria. |
| Electronic non-convergence, `not reached required accuracy`, many `DAV/RMM` steps | Electronic settings or starting charge are not stable. | Use parser/custodian diagnostics; keep outputs. | Change `ALGO`, `NELM`, mixing, smearing, MAGMOM, `ICHARG`, KPOINTS, ENCUT. |
| `BRMIX: very serious problems`, charge sloshing | Mixing instability, metallic/slab/large-cell sensitivity. | Preserve logs; do not blindly delete charge files unless approved. | Change mixing parameters, smearing, KPOINTS, magnetic initialization, or `ICHARG`. |
| `ZHEGV failed`, `LAPACK`, `Sub-Space-Matrix is not hermitian` | Numerical diagonalization problem or bad structure/parallel layout. | Block for review; record module and resource layout. | Change `ALGO`, parallel layout, precision, structure, ENCUT, or restart strategy. |
| `EDDDAV`, `EDDRMM`, `Call to ZHEGV failed` | Wavefunction/electronic instability. | Preserve `WAVECAR` status; consider disposable restart files only if review says so. | Change `ALGO`, `NELM`, mixing, smearing, `LREAL`, `PREC`, or remove/reuse `WAVECAR`. |
| `CHGCAR was not read`, charge density incompatible | `ICHARG` requests a missing or incompatible charge density. | Restage declared SCF `CHGCAR` symlink/source if available. | Change `ICHARG`, regenerate SCF, or change structure/source. |
| `WAVECAR` incompatible, bad `WAVECAR` | Restart file from different cell/bands/VASP build. | Remove or ignore only when stage review says `WAVECAR` is disposable. | Change restart policy, `ISTART`, `NBANDS`, or regenerate upstream SCF. |
| POSCAR/POTCAR element/order mismatch | Wrong POTCAR order, count, or labels. | Stop; compare POSCAR symbols/counts and POTCAR titles. | Regenerate POTCAR or POSCAR; review element order and labels. |
| `TOO FEW BANDS`, band/Wannier missing states | `NBANDS` too low for requested analysis. | Stop and record need. | Increase `NBANDS`; rerun SCF/band/Wannier envelope. |
| Symmetry errors, atoms equivalent unexpectedly, constraints ignored | Symmetry conflicts with slab/defect/magnetism. | Inspect POSCAR/selective dynamics and `ISYM`. | Change `ISYM`, constraints, MAGMOM, or structure. |

## Wannier90

| Signal | Likely cause | Allowed first action | Review-required adjustment |
|---|---|---|---|
| `wannier90.x: command not found`, `vasp2wannier90` missing | Module/build missing interface. | Check modules and executable paths. | Change module stack or build path. |
| Missing `.amn`, `.mmn`, `.eig`, `.win` | Interface step did not run or filenames mismatch. | Verify VASP `LWANNIER90`/post-processing outputs and working directory. | Change workflow ordering or rerun SCF/non-SCF/Wannier interface stage. |
| `num_wann larger than num_bands`, not enough bands | Too few bands in VASP stage or `.win`. | Stop and record required band count. | Increase `NBANDS` and rerun upstream stage; change `num_wann` only with review. |
| Disentanglement not converged, spread oscillates | Bad projections/window or insufficient bands. | Preserve `.wout`; inspect projections and frozen/outer windows. | Change projections, `dis_win_*`, `dis_froz_*`, `num_iter`, `num_bands`. |
| `mp_grid` mismatch, k-point mismatch | `.win` grid differs from VASP KPOINTS. | Compare `.win`, `KPOINTS`, `.mmn`. | Regenerate `.win` or rerun upstream with matching mesh. |
| Missing `UNK*` files for plotting | Real-space output not requested or not copied. | Check `wannier_plot` settings and file paths. | Rerun Wannier with required plot settings. |

## Phonopy

| Signal | Likely cause | Allowed first action | Review-required adjustment |
|---|---|---|---|
| Force files missing, displacement job incomplete | Failed or unfinished FD worker. | Retry only failed displacement inside same displacement set. | Regenerate displacement set or change supercell/relaxed structure. |
| Supercell/atom count mismatch | POSCAR used for forces differs from phonopy supercell. | Stop; compare hashes and atom counts. | Regenerate displacements and force calculations from the approved relaxed structure. |
| Large drift force warning | Poor force convergence or numerical noise. | Record drift; check convergence and symmetry. | Tighten force calculation settings, supercell, KPOINTS, ENCUT, or symmetry policy. |
| Imaginary modes near Gamma | May be numerical, acoustic sum rule issue, or real instability. | Validate convergence, supercell size, and ASR/NAC settings; do not hide modes. | Change supercell, convergence settings, structure, magnetic state, ASR/NAC policy. |
| `phonopy` command not found, import error | Environment missing. | Activate/install tool environment. | None scientific, but record environment change. |
| NAC/BORN missing for polar material | Non-analytical correction inputs absent. | Report missing BORN/NAC data. | Add DFPT/BORN workflow and review parameters. |
