# Input Review

Before preparing or submitting a VASP task, inspect the real files and report
the following to the user.

## POSCAR

- Source path and generation method.
- SHA256 hash.
- If generated from structure research, cite the chosen database/literature/user
  source, candidate comparison file, transformations, and user confirmation from
  `structure/metadata.json`.
- Lattice constants or vector lengths.
- Element order and counts.
- Coordinate mode and selective-dynamics/fixed-atom status.
- Whether the structure came from original input, relaxed `CONTCAR`, SCF,
  phonopy displacement, or user-provided file.
- For generated structures, generally sort atoms by descending `z`, then
  ascending `x`, then ascending `y`, unless symmetry/site labels require another
  order.

## INCAR

- Source template/path and any inherited/appended/overridden parameters.
- Complete effective INCAR, not only a summary.
- Built-in relax defaults, when used: `EDIFF=1E-6`, `EDIFFG=-0.01`,
  `NSW=80`, `IBRION=2`, `ISIF=3`, `ISMEAR=0`, `SIGMA=0.05`,
  `PREC=Accurate`, `LREAL=.FALSE.`. These defaults still require review before
  submit, and user-provided CLI/template values override them.
- Built-in SCF defaults, when used: `EDIFF=1E-7`, `IBRION=-1`, `NSW=0`,
  `ISIF=2`, `LWAVE=.TRUE.`, `LCHARG=.TRUE.`, plus the reviewed smearing and
  precision settings.
- General relax jobs do not use an automatic EDIFF ladder by default. Treat
  `EDIFF=1E-6` as the fixed reviewed relax default; any tightening to `1E-7`
  or `1E-8` is a new scientific-parameter change that needs explicit review.
- Explicitly call out ENCUT, EDIFF, EDIFFG, IBRION, NSW, ISIF, ISMEAR, SIGMA,
  ISPIN, MAGMOM, LORBIT, LWAVE, LCHARG, ICHARG, NEDOS, NCORE/KPAR if present.
- Any change after approval invalidates the old submit approval.

## KPOINTS

- Source path or generator.
- Mesh for relax/SCF/DOS, or full high-symmetry path for band.
- For band tasks, list labels in order and state whether the path came from
  VASPKIT, pymatgen, SeeK-path, a built-in template, or manual input.
- If the expected generator is missing, stop and tell the user to install or
  activate the environment instead of fabricating a path.

## POTCAR

- Default functional is PBE.
- Element order, concrete POTCAR label/title, source path, and SHA256 hash.
- Use `potcar-policy.md` for catalog behavior and licensing rules.

## job.sh / Slurm

- Partition/QoS/account, nodes, nodelist, ntasks, ntasks-per-node,
  cpus-per-task, GPU GRES, walltime, modules if known, and exact VASP command.
- Task quantity: one VASP job, number of worker jobs, or number of displacement
  tasks under an approved worker envelope.
