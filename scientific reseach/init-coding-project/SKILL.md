---
name: init-coding-project
description: Interview, challenge, inspect, plan, preview, and safely initialize language- and framework-agnostic coding projects. Use when starting a new application, service, library, CLI, automation, data, infrastructure, or monorepo project; when converting an idea into an executable engineering contract; or when auditing and supplementing an existing repository without overwriting its files.
---

# Initialize Coding Projects

Turn a software idea or existing repository into an executable, agent-readable project only after the user reviews the engineering blueprint and filesystem preview.

## Core workflow

1. Inspect the proposed root before writing. Run:

   ```bash
   python scripts/inspect_coding_project.py --root <project_path>
   ```

   Also read relevant manifests, CI configuration, agent instructions, architecture records, and existing plans. Do not ask questions the repository can answer.
2. Interview the user one decision at a time. Recommend an answer with every question and follow `references/interview_guide.md`.
3. Confirm an English lowercase kebab-case project slug. Do not invent a lossy translation of a non-English name.
4. Define the problem, users, measurable goals, in-scope and out-of-scope behavior, project types, architecture boundaries, constraints, deliverables, risks, and unresolved assumptions.
5. Detect the existing stack before proposing one. Read `references/stack_and_scaffolding.md` when selecting a stack or source layout. Ask permission before external ecosystem or package research.
6. Define an executable quality contract: environment, setup, development, test, lint, typecheck, build, CI, test seams, Definition of Done, and non-functional requirements. Mark unknown commands as `null` or `pending`; never guess.
7. Present the final blueprint and request confirmation before creating the machine-readable spec.
8. Build `project_spec.json` using `references/project_schema.md`. Keep JSON/YAML keys, paths, commands, code symbols, and technical identifiers in English. Write human-facing values in the user's language by default.
9. Run the initializer with `--dry-run`. Show the normalized identity, directories, files to create, existing files to preserve, and zero-overwrite guarantee.
10. Ask for explicit confirmation, then run with `--apply`. Existing files must never be overwritten.
11. Ask separately before passing `--git-init`.
12. Treat package installation, framework generators, remote repository changes, issue publication, CI configuration, and secrets as separate operations requiring their own review and authorization. The initializer never executes `scaffold.planned_commands`.

## Project contract

Always create missing control-plane directories:

```text
docs/product/
docs/architecture/adr/
docs/plans/
docs/records/
```

Always plan `PROJECT_CONTEXT.md` as the human and agent source of truth. For a new project, create a short `AGENTS.md` by default. For an existing project, preserve all agent files; if only `CLAUDE.md` exists, ask whether to create `AGENTS.md` and encode the answer in `agent_instructions.create_agents_md`.

Create `docs/reports/`, `docs/presentations/`, `assets/`, and `deliverables/` only when enabled in the spec. Classify working reports and presentation sources under `docs/`, reusable media under `assets/`, and approved external-facing outputs under `deliverables/`. Discuss Git LFS or external storage before adding large binaries.

Do not impose `src/`, `tests/`, `apps/`, or `packages/`. Create source directories only from the confirmed `scaffold.directories` list. Use ecosystem conventions for module/package names; use lowercase kebab-case only for the project slug.

Keep `AGENTS.md` concise and point it to `PROJECT_CONTEXT.md` and the engineering plans. Record durable architecture decisions under `docs/architecture/adr/` and material state changes in `docs/records/project_log.md`. Do not create daily logs unless the user explicitly needs them.

## Safety contract

- Inspect first and write nothing during interviewing or blueprint design.
- Preserve every existing file byte-for-byte.
- Reject absolute paths and `..` traversal in requested directories.
- Preview before apply.
- Never execute commands stored in the spec.
- Do not initialize Git without explicit approval.
- Do not install dependencies, call framework generators, publish issues, create remotes, or configure secrets as part of the default initializer.
- For an existing repository, prefer its established language, layout, naming, and quality commands over new conventions.
- Record unresolved claims and commands as pending rather than fabricating them.

## Commands

Paths are relative to this skill directory.

```bash
python scripts/inspect_coding_project.py --root <project_path>

python scripts/init_coding_project.py --root <project_path> --spec <project_spec.json> --dry-run
python scripts/init_coding_project.py --root <project_path> --spec <project_spec.json> --apply
python scripts/init_coding_project.py --root <project_path> --spec <project_spec.json> --apply --git-init
```

`--git-init` is valid only with `--apply` and only after separate user approval.

## Reference map

- `references/interview_guide.md`: one-decision-at-a-time engineering interview and final blueprint.
- `references/project_schema.md`: machine-readable specification and validation rules.
- `references/stack_and_scaffolding.md`: local stack detection, project-type prompts, layout selection, and scaffold authorization.

