# Phoenix Cluster Notes

Use this file for Phoenix CPU and GPU VASP work. For G3/H100, also read
`g3-cautions.md`.

## Read-Only Preflight

Run the relevant subset before writing or submitting a job:

```bash
date '+%Y-%m-%d %H:%M:%S %Z %z'
hostname -f
whoami
df -h /home /mnt/burstbuffer
sinfo -o "%P|%a|%l|%D|%t|%N"
sinfo -N -o "%N|%P|%t|%c|%m|%G|%f"
scontrol show partition Phoenix
scontrol show partition Phoenix-GPU
sacctmgr show qos format=name,priority,maxnodesperjob -P
squeue -u "$USER" -o "%i|%P|%j|%u|%T|%M|%D|%R"
module avail vasp
```

## CPU Guidance

- Prefer CPU VASP for routine relax/static/DOS/band workflows unless a GPU
  benchmark for the same workload exists.
- Verify the current VASP module instead of copying old module names blindly.
- Use Slurm resources and MPI/OpenMP layout for performance tests. Do not
  change physical inputs as an acceleration shortcut.

## GPU Guidance

- Verify node state and GPU type before requesting a node.
- Use one MPI rank per GPU as a starting point for GPU VASP unless a benchmark
  for the exact build says otherwise.
- Do not use GPU VASP on an unvalidated module stack for production.
- Archive GPU validation output with the module list and VASP startup lines.

## Storage

- Use `/home/$USER/projects/<project_slug>` for managed persistent project
  files and final archives. For `jmhe`, use `/home/jmhe/projects/<project_slug>`.
- If the local project name is Chinese, translate it to a concise English
  `lowercase_snake_case` project slug before creating cluster directories.
- Use `/home/jmhe/projects/<project_slug>/calculations/<system_slug>/<case_slug>`
  as the default persistent calculation case path.
- Use `/home/jmhe/projects/<project_slug>/archive` as the default persistent
  archive root and `/home/jmhe/projects/<project_slug>/ledger/vwm.sqlite` as
  the default ledger path.
- Do not create cluster-side `raw_data/` or `formal_data/`. Keep processed
  `.dat`, figures, and reports under each source case's `analysis/` directory,
  and summarize them in
  `/home/jmhe/projects/<project_slug>/docs/project_summary.md`.
- Record existing `/home/jmhe/project/...` paths as legacy sources when needed,
  but do not create new managed projects there.
- Use `/mnt/burstbuffer` only as scratch, and copy final archives/results back
  to `/home`.
- Default Phoenix POTCAR root is `/home/jmhe/app/pot_database`.

## Red Lines

- Do not run production compute on login or management nodes.
- Do not target nodes in `down`, `drain`, `fail`, `maint`, `unk`, or
  `no_respond`.
- Do not cancel jobs without checking the exact job id and owner.
- Do not store credentials, private keys, or tokens in job scripts or archives.
