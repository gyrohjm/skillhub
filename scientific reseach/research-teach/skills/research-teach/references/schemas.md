# Project and Note Schemas

## Project layout

```text
project/
├── papers/
├── references/library.bib
├── knowledge/
│   ├── Sources/Inbox/
│   ├── Sources/Verified/
│   ├── Assets/
│   ├── Concepts/
│   ├── Maps/Controversies/
│   ├── Learning/
│   │   ├── 00-overview.md
│   │   ├── 01-foundations/
│   │   ├── 02-core/
│   │   └── 03-deep-dive/
│   └── Records/
├── dashboard/
└── .research/
    ├── config.yaml
    ├── global -> approved AgentContext/
    ├── proposals/
    ├── cache/
    ├── state/
    └── logs/
```

## Source note frontmatter

```yaml
---
node_type: source
status: inbox
title: "Paper title"
authors: "Author A; Author B"
year: 2026
doi: "10.xxxx/example"
source_url: "https://..."
source_file: "papers/example.pdf"
document_use: both
journal_tier: tier-1
verification_level: L1
conversion_engine: mineru-api
file_sha256: "..."
---
```

Use `status: verified` only in `Sources/Verified`.

## Concept note frontmatter

```yaml
---
node_type: concept
status: proposed
title: "Concept name"
aliases: ["Alias"]
---
```

Write explicit graph relations under a `## Relations` heading:

```markdown
- prerequisite -> [[Other concept]] | status: verified | evidence: [[Source note#p. 4]]
- supports -> [[Claim]] | status: proposed | evidence: [[Source note#Results]]
```

Supported relation names are open-ended but should be precise: `prerequisite`, `supports`, `contradicts`, `extends`, `applies-to`, `measured-by`, and `taught-in`.

## Controversy note

Record each position separately with:

- claim,
- supporting evidence,
- study-design and sample differences,
- evidence strength,
- limitations,
- current consensus,
- unresolved questions.

Do not collapse disagreement into an artificial single answer.

## Learning records

Store only demonstrated learning, confirmed prior knowledge, corrected misconceptions, or mission changes. Do not use learning records as session logs.

## Proposal schema

Proposal files are JSON and may target only:

- `profile.md`
- `preferences.md`
- `misconceptions.md`
- `projects.md`

The acceptance script appends an audited entry. It does not permit arbitrary paths or arbitrary code execution.

## Version-control defaults

The initializer ignores raw papers, cache, learner records, learning documents, dashboard output, state, logs, proposals, and the global symlink. Concept notes, source metadata, maps, and `library.bib` remain eligible for explicit versioning.
