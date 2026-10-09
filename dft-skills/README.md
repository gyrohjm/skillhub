# DFT skills

A lightweight research-agent toolkit: JSON task records, normal project directories,
and evidence-linked Markdown. The existing project skills need no database or
background service. The optional DFT Workbench prototype is maintained as a
separate project, with a local service and private SQLite state for simulated runs.

- [Project records](dft-contracts/references/project-records.md): naming, document
  fixed document updates, one main report, task screening/selection, scientific rework,
  final artifact publication, MEMORY.md and optional local Git history.
- [Workspace layout](dft-contracts/references/workspace-layout.md): ownership and paths.
- [Project organization](dft-work-manager/references/project-organization.md): inventory
  old calculations, preview reference-aware relocations, preserve sources and resume
  verified operations without creating another skill.
- [Local environments](dft-contracts/references/local-environment.md): private profiles,
  templates and notes outside Git. Never place credentials in this repository.
- [Capability registry](dft-contracts/capabilities.json): implemented and partial engines.

Use Python 3.12 with `pytest` and `jsonschema` for the full verification suite:

```bash
python -m pytest dft-skills -q
PYTHONPATH=dft-skills/dft-contracts python -m dft_contracts.privacy --root dft-skills
```

The record/profile/privacy helpers use the standard library. Full scientific contract
validation uses jsonschema; existing compatibility validators may perform fewer checks
when that dependency is absent.

`dft-contracts/hooks/pre-commit` is a local Git hook launcher. Install it into the
repository's resolved hooks directory only if no different hook exists, preserving any
existing hooks. It inspects staged blobs, including DFT documents and private resource
artifacts. The hook and ignore rules do not erase previously committed information or
prevent an intentional bypass. Private profile migration copies and verifies first,
refuses conflicts, and preserves local backups; Git history is left intact.

New paired projects register research routes in dft-project.json and use direct numbered
stages with optional shared inputs. Local plans/analysis accompany cluster execution
tasks; local analysis/ contains only the unique main report and selected final figures/tables.
Existing single-root projects retain results/ and task-local analysis products.
Existing calculations/ projects remain supported without automatic migration.

Project repositories use dft_project.py git-init/git-check for their own local hook.
This is separate from the skill repository privacy hook above; neither commits or
pushes automatically. The public skill tree contains no machine-local project data.

For reference-driven local/cluster initialization and reproducible result return, see
[paired projects](dft-contracts/references/paired-projects.md).
