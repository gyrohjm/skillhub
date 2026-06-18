---
name: init-research-project
description: Interview, challenge, plan, preview, and initialize scientific research projects with a reproducible docs/code/raw_data/formal_data structure. Use when starting a new research project, converting an early idea into testable hypotheses and executable experimental or computational objectives, standardizing an existing project directory without overwriting files, or establishing a validated data lifecycle for publication-ready results.
---

# Initialize Research Projects

Turn a research idea into an executable, AI-readable project only after the user has reviewed the research design and filesystem preview.

## Core Workflow

1. Inspect the proposed project path and any existing project files. Do not create or modify anything yet.
2. Interview the user in rounds of one to three high-value questions. Follow `references/interview_guide.md`.
3. Confirm an English `lowercase_snake_case` project slug. Never invent a lossy translation of a Chinese project name without confirmation.
4. State the research question, falsifiable hypotheses, objectives, success criteria, constraints, deliverables, and unresolved assumptions.
5. Ask permission before searching external literature or databases. Mark unsupported claims as pending validation when permission or network access is absent.
6. Design an executable plan. Read `references/experimental_design.md` for experimental work and `references/computational_design.md` for computational work.
7. Build `project_spec.json` using `references/project_schema.md`. Use bilingual Chinese/English content unless the user requests otherwise.
8. Run the initializer with `--dry-run`. Show the normalized project name, directory tree, files to create, and files that will remain untouched.
9. Ask for explicit confirmation, then run with `--apply`. Existing files must never be overwritten.
10. Ask separately before passing `--git-init`.

## Project Contract

Always create these top-level directories:

```text
docs/
code/
raw_data/
formal_data/
```

Use English `lowercase_snake_case` for directories, Python files, notebooks, and data files. Root convention files may use standard uppercase names such as `README.md`, `PROJECT_CONTEXT.md`, and `AGENTS.md`.

Treat `PROJECT_CONTEXT.md` as the human and agent source of truth. Keep `AGENTS.md` short and point it to the project context and research plans.

## Data Integrity

Follow `references/data_lifecycle.md`:

```text
raw_data -> code processing -> validation -> user approval -> formal_data
```

- Never modify source files in `raw_data` in place.
- Never promote data automatically.
- Preview promotion first; require the explicit `--approve` flag.
- Never overwrite an existing formal artifact.
- Record provenance, processing code, parameters, validation, approval, manuscript usage, and SHA256 in `formal_data/MANIFEST.csv`.

## Commands

Paths below are relative to this skill directory.

```bash
python scripts/init_research_project.py --root <project_path> --spec <project_spec.json> --dry-run
python scripts/init_research_project.py --root <project_path> --spec <project_spec.json> --apply
python scripts/init_research_project.py --root <project_path> --spec <project_spec.json> --apply --git-init

python scripts/promote_formal_data.py --project <project_path> --source <processed_file> --category plot_data --dry-run
python scripts/promote_formal_data.py --project <project_path> --source <processed_file> --category plot_data --approve <metadata options>
```

`--git-init` is valid only after the user explicitly approves Git initialization. `--approve` is valid only after the user explicitly confirms the artifact is publication-ready.

## Handoffs

- For calculation-specific VASP setup, review, or submission, hand off to `vasp-workflow`.
- For extraction, plotting, or interpretation of completed VASP outputs, hand off to `vasp-analysis`.
- For archiving or integrity verification, hand off to `vasp-work-manager`.
- Keep this skill focused on project definition, initialization, and data-governance boundaries.

## Reference Map

- `references/interview_guide.md`: staged research interview and assumption challenge.
- `references/project_schema.md`: machine-readable project specification.
- `references/experimental_design.md`: controls, replication, measurements, statistics, and stopping rules.
- `references/computational_design.md`: model hierarchy, convergence, validation, resources, and stopping rules.
- `references/data_lifecycle.md`: raw and formal data governance.
