# DFT Contracts

Internal, non-skill package that is the single machine-readable contract source
for the DFT skill family. It owns JSON schemas, migrations, validators, stable
canonical hashing helpers, and the execution/analysis capability registry.

The canonical human-readable workspace layout is in
`references/workspace-layout.md`. New executable leaves use one
`workflow.json` validated by `workflow-v2`; `workflow-v1` and the older
`task-spec-v2` contract remain readable for compatibility with existing task
trees and helpers. The v2 leaf keeps current input authority, reconciliation,
dependency, attempt, submission, completion, and lineage records together.
See `examples/workflow-v2.example.json` for a compact canonical leaf and
`examples/workflow-v1.example.json` for the legacy shape.

Resource checks are represented by the `resource-profile-v1` contract and are
cached at `.dft/resource-profile.json`. A v1 workflow can be copied into a v2
document with the non-destructive migration below; the source document is
never overwritten:

```bash
python migrations/migrate.py workflow-v1-to-v2 old-workflow.json new-workflow.json
```

The shared `dft_contracts.layout` helpers discover the workspace dynamically and
resolve registered research routes and their docs/plan.md and docs/log.md, plus
legacy plans/, logs/ and code/ paths. The project helper manages fixed document roles,
selection, impact screening and final artifact provenance without another task ledger. They reject unsafe composition/structure slugs and paths
that escape the corresponding workspace root.

This directory intentionally has no `SKILL.md`: agents enter through
`dft-design`, `dft-workflow`, `dft-analysis`, or `dft-work-manager`.
`dft-research-ideation` also uses `research-idea-v1` for its proposal-only
literature/idea portfolio.

```bash
python validators/validate.py result-v1 /path/to/result.json
python validators/validate.py workflow-v1 /path/to/workflow.json
python validators/validate.py workflow-v2 /path/to/workflow.json
python validators/validate.py resource-profile-v1 /path/to/resource-profile.json
python validators/validate.py research-idea-v1 /path/to/idea_portfolio.json
python validators/validate.py capabilities capabilities.json
python migrations/migrate.py task-spec-v1-to-v2 old.json new.json
```
