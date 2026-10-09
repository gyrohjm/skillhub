# Stack Detection and Scaffolding

## Detection order

1. Read explicit project and agent documentation.
2. Read workspace and package manifests.
3. Read lockfiles to identify the active package manager.
4. Read CI jobs and developer scripts to confirm real commands.
5. Inspect source and test layout.
6. Treat filenames as evidence, not proof; report ambiguity.

Use `scripts/inspect_coding_project.py` for the first pass, then inspect the files it identifies.

## Common evidence

| Evidence | Likely ecosystem |
|---|---|
| `pyproject.toml`, `uv.lock`, `poetry.lock` | Python |
| `package.json`, `pnpm-lock.yaml`, `yarn.lock` | Node.js / JavaScript / TypeScript |
| `Cargo.toml`, `Cargo.lock` | Rust |
| `go.mod`, `go.sum` | Go |
| `pom.xml`, `build.gradle*` | JVM |
| `Gemfile` | Ruby |
| `composer.json` | PHP |
| `*.sln`, `*.csproj` | .NET |
| `Terraform`, `Pulumi`, or deployment manifests | Infrastructure |

Do not select a framework from a language marker alone. Read dependencies and configuration.

## Project-type prompts

- `application`: client targets, navigation, state, accessibility, packaging, distribution.
- `service`: protocol, API contract, persistence, authentication, migrations, observability, deployment.
- `library`: public interface, compatibility policy, packaging, versioning, documentation, examples.
- `cli`: commands, stdin/stdout/stderr contract, exit codes, config, shell completion, packaging.
- `automation`: triggers, idempotency, retries, credentials, audit trail, failure recovery.
- `data`: input contracts, reproducibility, lineage, validation, storage, scheduling.
- `infrastructure`: environments, state, drift, secrets, rollback, policy checks.
- `monorepo`: workspace tool, package graph, ownership, shared configuration, release strategy.

## Layout policy

For an existing repository, preserve its established layout. For a new project, derive directories from deployment and packaging decisions. Do not create source directories merely because they are common.

Examples that require explicit confirmation:

- `src/` versus flat package layout.
- `apps/` and `packages/` in a monorepo.
- Co-located tests versus top-level `tests/`.
- `infra/`, `migrations/`, `examples/`, or `benchmarks/`.

Record only confirmed directories in `scaffold.directories`.

## Scaffold authorization

Framework and package generators can install dependencies, run lifecycle scripts, initialize Git, contact networks, or overwrite files. Before execution:

1. Show the exact command and expected version.
2. Explain files, dependencies, network access, and lifecycle scripts it may create or run.
3. Run the generator's preview/help mode when available.
4. Obtain separate approval.
5. Re-inspect the resulting tree and run the agreed quality commands.

The deterministic initializer records proposed generator commands but never executes them.

