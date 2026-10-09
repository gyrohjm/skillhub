---
name: sci-talk-planning
description: Design the research narrative for a scientific presentation before any slide-level work begins. Use when converting research materials, papers, notebooks, experiment results, or calculation outputs into a structured talk plan with a core argument, evidence chain, audience profile, narrative arc, time budget, material priorities, and predicted questions. Output a talk_plan.md that hands off to simple-sci-ppt for slide-level planning and PPTX generation. Do not create slides, write generator code, select layout archetypes, or produce PPTX files; hand those to simple-sci-ppt.
---

# Scientific Talk Planning

## Overview

This skill is the narrative design layer that sits upstream of
`simple-sci-ppt`:

```text
sci-talk-planning -> simple-sci-ppt
  (what to say)        (how to render it)
```

Produce a human-readable `talk_plan.md` containing the core argument,
audience profile, narrative arc, claim-evidence matrix, source-reading
status, material priorities, time budget, and predicted questions. Do
not plan slides, select layout archetypes, write generator code, or
produce PPTX files.

Write human-facing prose in Chinese by default. Keep code, JSON keys,
schema fields, paths, filenames, commands, units, and technical terms
in English. Do not repeat the same content bilingually.

## Core Workflow

1. Inventory available source materials: papers, notebooks, figures,
   experiment results, calculation outputs, prior slides, and user notes.
   Do not modify anything yet. If the user requests that all literature
   be read, read every parseable source before planning. Otherwise, read
   every source later classified as `essential` in full; do not use an
   unread source to support a takeaway claim.
2. Interview the user in rounds of one to three high-value questions.
   Follow `references/interview-guide.md`.
3. Identify the talk type: group meeting, conference talk, thesis
   defense, classroom lecture, invited seminar, or progress update.
4. Define the core argument: what are the 1-3 key takeaways the audience
   should remember after this talk?
5. Read `references/narrative-archetypes.md` and select a narrative
   structure. Challenge the user if the chosen structure does not serve
   the core argument.
6. Build the claim-evidence matrix. For each takeaway claim, list
   supporting evidence, evidence strength, source, and known
   limitations. Read `references/evidence-chain.md`.
7. Prioritize materials. Classify every available source as `essential`,
   `supporting`, or `cuttable` for this specific talk. For every
   `essential` anchor paper, record the reading status and a narrative
   coverage requirement: background problem, direct evidence, mechanism,
   and limitation. Read `references/material-prioritization.md`.
8. Determine the time budget and `pacing_mode`. Use `visual_micro` only
   when the user explicitly requests a high-page-count or fast
   figure-evidence deck; otherwise use `standard`. Allocate time across
   narrative sections. Read `references/time-allocation.md`.
9. Predict audience questions and identify weaknesses the user should
   prepare to address.
10. Read `references/talk-plan-contract.md` and write `talk_plan.md`
    using `assets/talk_plan.template.md`.
11. Present the plan to the user for review. Ask for explicit approval
    before handing off.
12. After approval, instruct the user to invoke `simple-sci-ppt` with
    the `talk_plan.md` path. Do not invoke `simple-sci-ppt` directly.

## Narrative Design Rules

- The core argument must be falsifiable or empirically grounded. If a
  takeaway cannot be challenged, it is a platitude, not a scientific
  claim.
- Every claim in the takeaway list must map to at least one evidence
  item in the claim-evidence matrix. Unmapped claims are flagged
  `evidence gap`.
- Evidence strength must be rated as `confirmed`, `preliminary`,
  `inferred`, or `pending`. Do not let `preliminary` evidence support
  a strong takeaway without an explicit caveat.
- The narrative arc must have a clear climax: the slide or section where
  the strongest evidence meets the central claim. Identify it explicitly.
- Time budget must be realistic. In `standard` mode, estimate slide count
  from content density. In explicitly requested `visual_micro` mode, a
  15-minute talk may use 20-25 slides when each evidence or transition
  page has one judgment, one visual focus, and a planned 20-40 second
  speaking interval. Reserve transitions and any requested Q&A time.
- Material priority is talk-specific. A paper that is `essential` for a
  group meeting may be `cuttable` for a conference talk with a different
  focus.
- If the user has a reference folder with many papers, do not plan a
  paper-by-paper summary unless explicitly requested. Select claims and
  figures that serve the narrative arc.
- An `essential` anchor paper cannot be reduced to an isolated result.
  Its narrative coverage must state how the study frames the problem,
  what evidence it provides, how the proposed mechanism is supported,
  and what remains unresolved. These are narrative requirements, not
  slide-layout instructions.
- Use formal scientific Chinese. Avoid conversational fillers,
  slogan-like wording, anthropomorphic descriptions, and rhetorical
  "story" framing. Write claims as evidence-bounded statements.

## Handoff Contract

The output `talk_plan.md` is the sole handoff artifact. It must contain
these sections in order:

1. **Talk metadata**: type, title, presenter, date, duration, audience.
2. **Core argument**: 1-3 takeaways with declarative statements.
3. **Audience profile**: who they are, knowledge baseline, expectations.
4. **Narrative arc**: sections with purpose, time allocation, and the
   identified climax.
5. **Claim-evidence matrix**: claims, evidence, strength, source,
   limitations.
6. **Material priorities**: `essential` / `supporting` / `cuttable`,
   reading status, narrative role, and anchor-source coverage requirement.
7. **Predicted questions**: likely audience questions and recommended
   response strategy.
8. **Handoff to simple-sci-ppt**: recommended deck mode, approximate
   slide count, key figures to include, `pacing_mode`, `visual_mode`,
   `citation_policy`, `speaker_notes_depth`, and language constraints.

`simple-sci-ppt` reads this file and uses it to pre-fill sections 1-3
of its slide-level markdown plan. If `talk_plan.md` is absent,
`simple-sci-ppt` can still work independently with a lightweight inline
version of these decisions.

## Hard Failure Examples

- A takeaway claim has no corresponding evidence row in the matrix.
- The time budget exceeds the talk duration without an explicit
  overflow plan.
- The narrative arc has no climax and reads like a flat list of topics.
- `preliminary` or `inferred` evidence is used to support a strong
  declarative takeaway without a caveat.
- The material priority list omits a source that the claim-evidence
  matrix depends on.
- A claim depends on a paper that was not read at the required scope.
- An `essential` anchor paper lacks a documented background, evidence,
  mechanism, or limitation coverage path.
- A requested `visual_micro` deck is assigned high page count without a
  one-claim/one-evidence pacing rationale.
- The plan defaults to paper-by-paper structure when the user did not
  request it.
- The plan includes slide-level details such as layout archetypes,
  coordinate boxes, or PPTX generation instructions (owned by
  `simple-sci-ppt`).
- The talk plan is not presented to the user for approval before
  handoff.

## Reference Map

- `references/interview-guide.md`: staged interview to extract the core
  argument, audience context, and constraints.
- `references/narrative-archetypes.md`: common research talk narrative
  structures with selection criteria.
- `references/evidence-chain.md`: claim-evidence matrix construction,
  evidence strength rating, and gap analysis.
- `references/material-prioritization.md`: source classification and
  cutting strategy for talk-specific focus.
- `references/time-allocation.md`: duration-based section budgeting and
  slide count estimation.
- `references/talk-plan-contract.md`: field definitions and validation
  rules for the handoff document.
- `assets/talk_plan.template.md`: skeleton template for `talk_plan.md`.

## Handoffs

- Use `simple-sci-ppt` for slide-level planning, layout archetype
  selection, PPTX generation, and QA iteration after this skill
  produces an approved `talk_plan.md`.
- Use `init-research-project` if the talk is part of a new project that
  has not been initialized yet.
- Use `dft-design` if the talk depends on computational
  experiments that have not been scientifically designed.
- Use `dft-analysis` if the talk needs figures or data from completed
  VASP calculations that have not been extracted yet.
- Keep this skill focused on narrative design. Do not generate slides,
  write code, or produce artifacts beyond `talk_plan.md`.
