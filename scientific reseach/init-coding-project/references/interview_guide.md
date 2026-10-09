# Coding Project Interview Guide

Ask one question at a time, wait for the answer, and include a recommended answer with concrete reasoning. Summarize settled decisions before moving to a dependent branch. Do not initialize files until the user confirms the final blueprint.

## 1. Inspect before asking

Resolve locally discoverable facts first:

- Existing files, manifests, lockfiles, source layout, tests, CI, Git state, and remotes.
- `AGENTS.md`, `CLAUDE.md`, `PROJECT_CONTEXT.md`, product documents, ADRs, and implementation plans.
- Existing setup, development, test, lint, typecheck, and build commands.
- Whether the repository is empty, single-package, multi-package, or a monorepo.

Report conflicts and uncertainty. Do not interpret an empty directory as a confirmed design choice.

## 2. Identity and outcome

Resolve:

1. Project name and confirmed English lowercase kebab-case slug.
2. One-sentence problem statement.
3. Target users or operators.
4. Measurable goals and success criteria.
5. Concrete deliverables.

Challenge solution-first descriptions until the user problem and success signal are explicit.

## 3. Scope and project shape

Choose one or more project types:

- `application`
- `service`
- `library`
- `cli`
- `automation`
- `data`
- `infrastructure`
- `monorepo`

Separate in-scope behavior, out-of-scope behavior, future ideas, and unresolved assumptions. For a monorepo, identify independently deployable or publishable units and shared packages.

## 4. Stack and architecture

Prefer detected conventions for an existing repository. For a new project, resolve in dependency order:

1. Deployment or distribution target.
2. Runtime and language.
3. Framework and package manager.
4. Persistence and external integrations.
5. Major modules, their interfaces, and ownership boundaries.
6. Source layout only after the preceding choices are stable.

Do not use popularity as the only reason for a stack choice. State tradeoffs involving team knowledge, deployment, maintenance, compatibility, and operational cost.

## 5. Quality and operation

Confirm:

- Supported environment and version constraints.
- Setup, development, test, lint, typecheck, and build commands.
- The highest useful test seams and required test layers.
- CI gates and release/deployment expectations.
- Security, privacy, performance, accessibility, reliability, compatibility, and observability requirements that apply.
- Definition of Done and stop conditions.

Unknown commands remain `null`; unresolved requirements remain `pending`.

## 6. Supporting artifacts and governance

Decide whether the project needs:

- Working reports under `docs/reports/`.
- Presentation sources under `docs/presentations/`.
- Reusable media under `assets/`.
- Approved external deliverables under `deliverables/`.
- Git LFS or external storage for large binaries.
- Local-only planning or later issue-tracker synchronization.

Keep local project documents authoritative unless the user explicitly chooses a different source of truth.

## 7. Side-effect approvals

Treat these as separate decisions:

- Apply the local filesystem plan.
- Initialize Git.
- Run package installers or framework generators.
- Create or change remote repositories.
- Publish issues or pull requests.
- Configure CI, deployment credentials, or secrets.

Approval for one does not imply approval for another.

## Final blueprint

Before writing, present:

1. Name, slug, project types, problem, users, and measurable goals.
2. Scope, non-goals, deliverables, constraints, and unresolved assumptions.
3. Stack evidence and architecture boundaries.
4. Quality commands, test strategy, CI gates, and Definition of Done.
5. Proposed directory tree and agent-file policy.
6. Existing-file conflict report.
7. Supporting-artifact classification.
8. Planned scaffold commands and every external side effect, clearly marked as not yet authorized.

Ask for explicit confirmation before creating the spec and dry-run preview.

