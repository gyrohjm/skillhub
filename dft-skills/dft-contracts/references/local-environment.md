# Local environment storage

Environment details live outside Git at `~/.config/dft-skills/`, or the absolute
directory selected by `DFT_SKILLS_CONFIG_DIR`. Resolve it with:

```bash
python <dft-contracts>/dft_contracts/local_config.py
```

The directory must be outside every Git worktree. Use directory mode `0700` and
file mode `0600`. Keep credentials in SSH configuration/key storage, not here.

- `profiles.json`: machine-readable profile resources, `project_root`, `potcar_root`.
- `dft-submit/references/`: private cluster, software and historical workflow notes.
- `dft-submit/assets/templates/`: private submission templates, used via `bash` or `sbatch`.
- `dft-workflow/references/`: migrated private catalog and profile notes.
- `privacy-markers.json`: local-only strings checked before committing DFT files.
- `original/`: verified migration backups; never copy these back into a repository.

Example (fictional values):

```json
{"profiles": {"example_cpu": {
  "resources": {"partition": "example", "nodes": 1, "ntasks_per_node": 8,
                "cpus_per_task": 1, "vasp_cmd": "srun vasp_std"},
  "project_root": "/opt/example/projects",
  "potcar_root": "/opt/example/potentials"
}}}
```

Explicit CLI arguments override a selected local profile; generic resource defaults
fill unspecified fields. Unknown profiles and malformed configuration fail explicitly.
Without a profile, supply explicit project and pseudopotential paths. Reuse only the
target environment; do not probe unrelated clusters to fill this file.

Read the selected private notes when a task needs the environment. Historical
permissions are context, not current authorization. Preserve templates and scientific
inputs; actual output and scratch files remain within the authorized calculation tree.

For a new machine, explicitly provision the private directory through a private channel;
it is not installed from Git. `preserve_private_files` copies and verifies a batch,
refuses conflicting existing files, and never removes sources. Clean source copies
only after verification succeeds. No keys are migrated.

The local pre-commit privacy check reads staged Git blobs. It can be bypassed and
does not rewrite old commits. Keep generated environment baselines, resource caches,
rendered job scripts and licensed potentials out of public commits as well.
