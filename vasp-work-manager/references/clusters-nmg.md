# nmg Cluster Notes

Use this file for nmg/Nano/Nanod VASP work and for the user's configured
MacBook SSH path.

## Known Local Access

- SSH alias: `nmg-macbook`
- Local key: `/Users/gyro/.ssh/id_nmg_macbook_ed25519`
- Preferred test root on cluster: `/home/jmhe/project/vaspmgr_test`
- Existing project copy observed before: `/home/jmhe/vasp-work-maneger`

Recheck these paths before relying on them.

## Safe Defaults

- Keep tests under `/home/jmhe/project/vaspmgr_test`, not the cluster home root.
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
LEDGER=/home/jmhe/project/vaspmgr_test/vwm.sqlite
ARCHIVE=/home/jmhe/project/vaspmgr_test/archive
```

Example:

```bash
python /path/to/vasp-work-manager/scripts/vwm_archive.py \
  --source /home/jmhe/project/vaspmgr_test/runs/sic_relax \
  --project sic-test \
  --task sic-relax \
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
