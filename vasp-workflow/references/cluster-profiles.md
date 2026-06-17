# Cluster Profiles

Treat cluster profiles as starting points, not current facts.

If `references/cluster-profiles.local.md` exists, read it before selecting a
profile. That file is intentionally ignored by git and may contain the user's
private cluster names, node inventory, queue observations, and local submission
preferences. If it does not exist, copy
`references/cluster-profiles.template.md` to
`references/cluster-profiles.local.md` and let the user fill it for their own
cluster.

Do not publish or commit local cluster snapshots unless the user explicitly
asks to sanitize and share them.

Before submitting on nmg, Phoenix, or G3/H100, run live read-only checks for
partition, QoS, nodes, modules, queue, and storage.

Check at least:

```bash
hostname -f
whoami
sinfo -o "%P|%a|%l|%D|%t|%N"
squeue -u "$USER" -o "%i|%P|%j|%u|%T|%M|%D|%R"
module avail vasp
df -h /home
```

The workflow CLI can render Slurm scripts from `--profile nmg`,
`--profile phoenix`, or `--profile generic`, but the submit review must show the
actual partition, node count, task count, wall time, and VASP command before
submission.

G3/H100 is high risk. Require live checks and a short validation job before
production VASP, especially for GPU builds and module stacks.
