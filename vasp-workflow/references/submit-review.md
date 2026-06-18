# Mandatory Submit Review

Before any `sbatch`, generate and show a submit review. The review is not a
short checklist; it is the user-facing contract for the calculation. It must
include enough detail that the user can catch a wrong structure, pseudopotential,
K-path, or resource envelope before the job enters Slurm.

- `Workflow`: calculation stage, upstream dependency, and whether the dependency
  follows the approved order: `test -> relax -> electronic/scf -> downstream`.
  For phonon, state the relaxed `CONTCAR` source explicitly.
- `POSCAR`: source path, generation method, SHA256, whether it comes from
  relax, SCF, phonopy displacement, or user input, lattice constants/lattice
  vector lengths, atom counts, coordinate mode, selective-dynamics/fixed-atom
  status, and whether the atom order was intentionally sorted. For generated
  structures, state the ordering convention: generally sort atoms by descending
  `z`, then ascending `x`, then ascending `y`, unless the user requests another
  order for symmetry, constraints, or site labels.
- `INCAR`: source template or path, SHA256, the complete effective INCAR that
  will be submitted, and a separate list of inherited, appended, or overridden
  parameters for follow-up calculations. Do not show only `ENCUT` or a brief
  summary when asking for approval.
- `KPOINTS`: source path or generator, mesh/path summary, SHA256. For band
  calculations, list the high-symmetry path explicitly, e.g.
  `G-X-W-K-G-L-U-W-L-K` for FCC, and state whether it was generated manually,
  by VASPKIT, pymatgen, SeeK-path, or another package.
- `POTCAR`: functional, element order, POTCAR title lines or safe labels,
  SHA256, and source path. Default the functional to `PBE` when the user has not
  specified one, but ask the user which element-specific label/path to use when
  the local catalog is missing or ambiguous. Do not put POTCAR contents in a
  public repository.
- Resources: partition, QoS, account, nodelist, GRES/GPU request, node count,
  ntasks, ntasks-per-node, cpus-per-task, wall time, VASP command, module
  assumptions.
- Task count: one job count, or finite-displacement worker count plus total
  displacement count.

When a needed generator is not available, tell the user what to install instead
of fabricating the file. Common options are VASPKIT on the cluster, or a Python
virtual environment with packages such as `pymatgen`, `ase`, `phonopy`, and
`seekpath`.

Submission is invalid when any POSCAR/INCAR/KPOINTS/POTCAR hash, POTCAR
functional/label/path, module stack, VASP command, or resource field changes
after the review. Regenerate the review and get user approval again.

For FD phonon worker queues, the user approves the whole taskset envelope once:
all workers may claim displacements only inside that approved envelope.

In CLI automation, require either an explicit `--approved` flag or an approval
file whose hash matches the current `submission_review.dat`. Do not treat the
existence of an old review as approval when the inputs or resources changed.

For automatic workflow handoff, a workflow-level approval may authorize the
intended dependency graph and resource envelopes, but it does not remove the
per-stage review requirement. The cron/tick script must write or verify each
stage review with actual derived hashes before submitting that stage. If a
derived input, resource field, or dependency path is outside the approved
workflow envelope, block and ask the user or Agent to review.

Standard prepared stages (`prepare relax|scf|band|dos`) write their review and
approval directly inside the stage directory. FD worker queues write them inside
the taskset `input/` directory. Automation plans must point `review_file` and
`approval_file` at the right relative path.
