# nmg Cluster Notes

Use this file for nmg/Nano/Nanod VASP work and for the user's configured
MacBook SSH path.

## Known Local Access

- SSH alias: `nmg-macbook`
- Local key: `/Users/gyro/.ssh/id_nmg_macbook_ed25519`
- Preferred test root on cluster: `/home/jmhe/project/vaspmgr_test`
- Default managed project root: `/home/jmhe/projects/<project_slug>`
- Default production calculation root: `/home/jmhe/projects/<project_slug>/calculations/<system_slug>/<case_slug>`
- Default production archive root: `/home/jmhe/projects/<project_slug>/archive`
- Default ledger path: `/home/jmhe/projects/<project_slug>/ledger/vwm.sqlite`
- Default POTCAR root: `/home/jmhe/app/pot`
- Legacy paths observed before: `/home/jmhe/project/...` and
  `/home/jmhe/vasp-work-maneger`

Recheck these paths before relying on them.

## Safe Defaults

- Keep tests under `/home/jmhe/project/vaspmgr_test`, not the cluster home root.
- For managed production work, first create one short English project slug under
  `/home/jmhe/projects/<project_slug>`. If the local project name is Chinese,
  translate it to concise English `lowercase_snake_case` and confirm it.
- Keep production calculation cases under
  `/home/jmhe/projects/<project_slug>/calculations/<system_slug>/<case_slug>`.
- Keep archives under `/home/jmhe/projects/<project_slug>/archive`.
- Do not create cluster-side `raw_data/` or `formal_data/`. Run processing and
  plotting under each case's `analysis/` directory, and summarize paths and
  conclusions in `/home/jmhe/projects/<project_slug>/docs/project_summary.md`.
- Use explicit project and task directories.
- Use VASPKIT for KPOINTS/POTCAR only when the user asks or the workflow already
  depends on it.
- Do not change KPOINTS, ENCUT, or INCAR physical settings while testing
  performance unless the user explicitly approves that scientific change.

## Slurm Profile Memory

The historical lightweight profiles in the Python project included `Nano` and
`Nanod` CPU partitions with Intel/VASP module patterns. Treat those as examples,
not permanent facts. Before submission, run live read-only checks:

```bash
hostname -f
whoami
sinfo -o "%P|%a|%l|%D|%t|%N"
squeue -u "$USER" -o "%i|%P|%j|%u|%T|%M|%D|%R"
module avail vasp
df -h /home
```

## Archive Pattern On nmg

Use persistent storage:

```bash
PROJECT_ROOT=/home/jmhe/projects/sic_test
LEDGER=$PROJECT_ROOT/ledger/vwm.sqlite
ARCHIVE=$PROJECT_ROOT/archive
```

Example:

```bash
python /path/to/vasp-work-manager/scripts/vwm_archive.py \
  --source "$PROJECT_ROOT/calculations/sic_bulk/relax_pbe" \
  --project sic_test \
  --task sic_bulk.relax_pbe \
  --system-slug sic_bulk \
  --case-slug relax_pbe \
  --archive-root "$ARCHIVE" \
  --ledger "$LEDGER" \
  --cluster nmg
```

## Red Lines

- Do not run production VASP directly on login nodes.
- Do not delete old project directories with broad globs.
- Do not overwrite existing OUTCAR, OSZICAR, CONTCAR, WAVECAR, or CHGCAR
  without explicit intent.
- Do not make performance conclusions from changed scientific inputs.
