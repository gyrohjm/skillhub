# Cluster Profiles Template

Copy this file to `references/cluster-profiles.local.md` and edit it for the
clusters you actually use. The `.local.md` file is ignored by git so private
cluster details, current node state, and local account rules stay on your
machine.

Update this file from live read-only checks before submitting production jobs:

```bash
hostname -f
whoami
sinfo -o "%P|%a|%l|%D|%t|%N"
scontrol show node <node>
squeue -u "$USER" -o "%i|%P|%j|%u|%T|%M|%D|%R"
module avail vasp
df -h /home
```

## Cluster: <name>

| Partition | Nodes | CPU/node | GPU/node | Memory/node | Notes |
|---|---:|---:|---:|---:|---|
| <partition> | <node expression> | <cores> | <gpu count/type or none> | <memory> | <idle/alloc/down notes, QoS, module caveats> |

Recommended defaults for submit scripts:

- CPU partition: `<partition>`
- `--ntasks-per-node`: `<cpu per node>`
- GPU partition: `<partition>`
- VASP command: `<mpirun/srun command>`
- Required modules: `<module list>`
- Account/QoS constraints: `<account/qos>`

## Notes

- Slurm inventory fields can be stale or incomplete. Prefer live `sinfo`,
  `scontrol show node`, and a short validation job before production.
- Keep scientific inputs separate from resource tuning. Do not change POSCAR,
  INCAR, KPOINTS, or POTCAR just to make a performance test faster unless the
  user explicitly approves that scientific change.
- The submit review must still show POSCAR/INCAR/KPOINTS/POTCAR provenance,
  hashes, partition, node count, task count, worker count, wall time, and VASP
  command before any `sbatch`.
