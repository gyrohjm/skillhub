# Research and Teaching Workflow

## Modes

### Research

1. Diagnose the user's goal, prior knowledge, time budget, and intended output with 5–10 focused questions.
2. Draft the research question, scope, search concepts, inclusion/exclusion criteria, and expected source count.
3. Propose a field-specific core-journal list:
   - Tier 1: flagship journals.
   - Tier 2: important specialist journals.
   - Cite authoritative indexing, society, or field sources and record the review date.
4. Wait for confirmation gate 1.
5. Search metadata and classify candidates as `Research`, `Teaching`, `Both`, or `Reject`.
6. Score journal tier, topical match, abstract match, document type, year, evidence quality, corrections/retractions, and likely teaching value.
7. Present reasons and wait for confirmation gate 2.
8. Download at most 20 approved items through the user's authenticated browser.

Do not equate journal prestige with study quality. A whitelist controls discovery priority, not automatic acceptance.

### Build

1. Preserve the original file and provenance.
2. Convert through MinerU API when policy permits; otherwise use OpenDataLoader.
3. Keep unverified output in `knowledge/Sources/Inbox`.
4. Verify:
   - L1: metadata, readability, page/section integrity.
   - L2: key claims and citations checked against the source.
   - L3: methods, data, limitations, and conclusions closely assessed.
5. Promote a source only after its required verification level is met.
6. Create atomic concept notes and explicit relation records.
7. Put unresolved disagreements in `knowledge/Maps/Controversies`.
8. Rebuild the offline graph and inspect it for unsupported or orphaned nodes.

### Teach

1. Read the project mission and only the approved files under `.research/global`.
2. Confirm the progressive document outline and first section at confirmation gate 3.
3. Teach from Verified project sources.
4. Keep the primary learning artifact as Markdown: overview, foundations, core, deep dive.
5. Use dialogue for explanation, questions, examples, and checks for understanding.
6. Record demonstrated learning in project-local records.
7. Propose, but never directly apply, global learner-profile updates.

## Evidence language

Always distinguish:

- source fact,
- mainstream interpretation,
- disputed interpretation,
- agent inference.

Every research claim and every graph relation used for teaching needs a traceable source and page/section locator when the source format permits it.
