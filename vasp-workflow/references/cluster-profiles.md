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
`--profile phoenix`, `--profile phoenix-gpu-a100`,
`--profile phoenix-gpu-g3`, or `--profile generic`, but the submit review must
show the actual partition, node count, task count, wall time, and VASP command
before submission. For Phoenix CPU/GPU submission templates and G3/H100
cautions, read `phoenix-submit.md`.

Default persistent calculation root for nmg/Phoenix work:

```text
/home/jmhe/project/<project_slug>/calculations/<system_slug>/<case_slug>
```

For new cases intended for `vasp-work-manager` intake/records, prefer:

```text
/home/<user>/projects/<project_slug>/calculations/<system_slug>/<case_slug>
```

Pass that path with `--case-root` until the helper default is intentionally
migrated.

Default POTCAR roots are `/home/jmhe/app/pot` on nmg and
`/home/jmhe/app/pot_database` on Phoenix profiles. These roots are search
starting points only; submit review must still show the resolved per-element
POTCAR paths and hashes.

For GPU VASP on Phoenix, prefer `g3`/H100 after live checks and a short
validation job, but throttle job count because the node has limited CPU cores
and concurrent GPU jobs can cause CPU contention. See `phoenix-submit.md`.
