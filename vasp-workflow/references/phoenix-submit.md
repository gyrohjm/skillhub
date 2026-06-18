# Phoenix Submit Profiles

Use this reference for Phoenix CPU and Phoenix-GPU VASP submissions. It folds
the previous `g3-node-job-submission-skill` scheduling guidance into
`vasp-workflow`, while keeping VASP input review mandatory.

## Mandatory Checks

Before any Phoenix CPU/GPU `sbatch`, run read-only checks and include the result
in the submit review or working notes:

```bash
hostname -f
whoami
df -h /home /mnt/burstbuffer
sinfo -o "%P|%a|%l|%D|%t|%N"
sinfo -N -n g1,g2,g3 -o "%N|%P|%t|%c|%m|%G|%f"
scontrol show partition Phoenix
scontrol show partition Phoenix-GPU
scontrol show node g1
scontrol show node g2
scontrol show node g3
squeue -w g1,g2,g3 -o "%i|%P|%j|%u|%T|%M|%D|%R"
squeue -u "$USER" -o "%i|%P|%j|%u|%T|%M|%D|%R"
module avail vasp
module avail cuda
module avail nvhpc
```

Do not target nodes in `down`, `drain`, `fail`, `maint`, `unk`, `no_respond`,
or states marked with `*`/`?` unless the administrator confirms they are usable.

## GPU VASP Scheduling Policy

When using the GPU build of VASP on Phoenix, prefer `g3`/H100 after the live
checks pass and the module stack has been validated. Use `g1`/`g2` A100 only
when `g3` is unavailable, unsuitable for the module/environment, or the user
explicitly wants an A100 node for comparison.

Do not submit large batches or many simultaneous GPU VASP jobs to `g3`. The
node has only 20 CPU cores and GPU jobs still consume CPU threads for MPI,
OpenMP, I/O, and GPU feeding. Too many concurrent jobs can starve the CPUs,
hurt other users, and make performance worse even if GPUs appear idle.

Default policy for `g3`:

- Start with one smoke/validation job.
- Prefer one VASP job per GPU request unless the user has explicitly reviewed a
  multi-job plan.
- Keep `--cpus-per-task` modest and reviewed; default helper value is `5` for
  one H100.
- Before adding more jobs, inspect `squeue -w g3`, `scontrol show node g3`,
  CPU allocation, GPU allocation, and recent job performance.
- For parameter sweeps, FD phonons, or many independent structures, throttle the
  number of active `g3` jobs and leave excess tasks queued or run them on CPU
  nodes/A100 nodes when appropriate.
- Treat any increase in job count, GPU count, CPU count, or simultaneous worker
  count as a resource-envelope change that requires submit review.

## g3 Access Model

After the `g3` reinstall, the login banner has reported RK8.10 and glibc 2.28.
Environment builds on `g3` are not compatible with the older GPU nodes by
default.

Interactive access may require a two-step login:

```bash
ssh <phoenix-mgt>
ssh g3
```

The second hop can require the user's password. Do not build automation that
depends on non-interactive `ssh g3` unless key or passwordless access has been
explicitly configured and tested.

Normal batch work should go through Slurm instead:

```bash
sbatch -w g3 job.sh
```

Live testing on June 18, 2026 showed that `sbatch -w g3` can allocate the H100
node even when non-interactive `ssh g3` fails with `Permission denied
(publickey,password)`. Therefore, use direct `ssh g3` only for interactive
debugging or environment setup; use Slurm for VASP jobs.

## CPU Profile

Use `--profile phoenix` for ordinary Phoenix CPU VASP jobs. Default resource
shape follows the user's working script:

```bash
#!/bin/sh
#SBATCH -N 1
#SBATCH -n 112
#SBATCH -J cpu_test
#SBATCH -p Phoenix
#SBATCH -q huge
#SBATCH --ntasks-per-node=112
module load intel_parallel
module load vasp6.4.2-avx512
unset I_MPI_PMI_LIBRARY
ulimit -s unlimited
srun vasp_std
```

The helper renders this as a reviewed Slurm job with no default walltime. The
user may still override partition, QoS, nodes, task counts, module command, or
walltime; any change must appear in `submission_review.dat`.

Example:

```bash
python -m vwf prepare scf \
  --case-root ./SiC \
  --source-poscar ./SiC/relax/CONTCAR \
  --potcar /path/to/POTCAR \
  --encut 520 \
  --kmesh "12 12 12" \
  --profile phoenix
```

## g1/g2 A100 Profile

Use `--profile phoenix-gpu-a100` for VASP GPU smoke tests, A100 comparison
runs, or production runs when `g3` is unavailable or unsuitable. Default target
is `g1`; use `--nodelist g2` to target `g2`, or clear `--nodelist ""` only when
Slurm can choose any suitable A100 node.

Default resource shape:

```bash
#!/bin/bash
#SBATCH -N 1
#SBATCH -J gpu
#SBATCH -p Phoenix-GPU
#SBATCH -A nano
#SBATCH -w g1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --gres=gpu:a100:1
#SBATCH --output=slurm-%j.out

module load nvhpc/22.9_mu
module load cuda/12.1
module load gcc/12.3
module load vasp6.3.2-gpu-mkl

export OMP_NUM_THREADS=$SLURM_CPUS_PER_TASK
export OMP_PLACES=cores
export OMP_PROC_BIND=close
export OMPI_MCA_btl_openib_warn_no_device_params_found=0

nvidia-smi
mpirun -np $SLURM_NTASKS vasp_std
```

## g3 H100 Profile

Use `--profile phoenix-gpu-g3` as the preferred Phoenix GPU VASP path after the
live checks pass and the calculation/module stack has been validated on `g3`.
Default resource shape is:

- partition: `Phoenix-GPU`
- account: `nano`
- nodelist: `g3`
- ntasks: `1`
- cpus-per-task: `5`
- GRES: `gpu:h100:1`
- module stack: `nvhpc/22.9_mu`, `cuda/12.1`, `gcc/12.3`,
  `vasp6.3.2-gpu-mkl`

`g3` is a high-risk path because OS, driver, CUDA, module, or rebuild state may
differ from g1/g2. Always live-check `scontrol show node g3`, `module avail`,
and run a short validation job before production. If the VASP GPU module is not
valid for H100, stop and ask the user to confirm the correct module; do not
silently reuse an A100 stack.

The Slurm script must start from the submit directory, not the Slurm spool
directory. Use:

```bash
cd "${SLURM_SUBMIT_DIR:-$PWD}"
```

or an explicit project path before writing `vasp.out`, `vasp.err`, or other
result files.

Example:

```bash
python -m vwf prepare scf \
  --case-root ./SiC \
  --source-poscar ./SiC/relax/CONTCAR \
  --potcar /path/to/POTCAR \
  --encut 520 \
  --kmesh "12 12 12" \
  --profile phoenix-gpu-g3
```

## Review Requirements

For Phoenix CPU/GPU jobs, `submission_review.dat` must show:

- POSCAR/INCAR/KPOINTS/POTCAR sources and hashes.
- partition, QoS, account, node count, task count, cpus-per-task, nodelist,
  GRES, walltime, and full VASP command/module stack.
- task count: one VASP job, number of worker jobs, or FD worker count.
- whether the job is CPU, g1/g2 A100, or g3 H100.
- for g3/H100, the intended simultaneous job count and a short statement that
  CPU contention was considered.

Any change to `INCAR`, `KPOINTS`, `POTCAR`, `POSCAR`, module stack, partition,
account, nodelist, GRES, task count, CPU count, walltime, or VASP command
invalidates the old approval.
