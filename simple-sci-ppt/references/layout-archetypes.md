# Layout Archetypes

Use this file to prevent free-coordinate slide construction. Every ordinary content slide must choose one declared layout archetype before generator code is written, unless the user explicitly requests a custom layout.

## Mandatory Rules

1. Pick one layout archetype before placing slide objects.
2. Declare all high-level objects in a layout box table before writing PPTX code.
3. High-level boxes must not overlap. Child objects inside the same component are exempt.
4. Keep at least `0.06 in` spacing between unrelated high-level boxes.
5. Do not solve layout conflicts by transparency, z-order, or sending an object backward.
6. Semi-transparent cards must not cover figures, tables, formulas, citations, page numbers, or conclusion boxes.
7. If content does not fit the selected archetype, split the slide.
8. Do not reduce ordinary Chinese or English body text below `20 pt` to force content onto one slide.
9. Bottom summaries should be one sentence and preferably one line.
10. Every generated deck must pass a layout collision audit before delivery.

## Required Layout Box Table

Before writing generator code, create a table for every content slide:

| slide | archetype | object_id | role | x | y | w | h | expected_content |
|---:|---|---|---|---:|---:|---:|---:|---|
| 3 | twoFiguresSummary | fig_left | figure | 0.55 | 1.05 | 5.95 | 4.85 | left comparison figure |

Use these declared boxes exactly in code unless a QA failure requires revision.

## Roles

Use the following high-level object roles:

- `title`
- `figure`
- `table`
- `formula`
- `callout`
- `card`
- `summary`
- `reference`
- `pageNumber`

Role collision rules:

- `callout` must not overlap `figure`, `table`, `formula`, `reference`, `summary`, or `pageNumber`.
- `summary` must not overlap `reference` or `pageNumber`.
- `reference` must not overlap `pageNumber`.
- `table`, `figure`, and `formula` must not overlap each other unless explicitly grouped as a single composite component.

## Archetype 1: `twoFiguresSummary`

Use for two visual panels with a one-line bottom conclusion.

```text
Title
────────────────────────
┌──────────────┐ ┌──────────────┐
│   Figure A   │ │   Figure B   │
│              │ │              │
└──────────────┘ └──────────────┘

        ┌──── one-line summary ────┐
Reference                                  page
```

| object_id | role | x | y | w | h |
|---|---|---:|---:|---:|---:|
| fig_left | figure | 0.55 | 1.05 | 5.95 | 4.85 |
| fig_right | figure | 6.82 | 1.05 | 5.95 | 4.85 |
| summary | summary | 2.20 | 6.12 | 8.95 | 0.52 |
| reference | reference | 0.45 | 7.05 | 8.50 | 0.24 |

Typical uses: experiment vs calculation, Li vs Na, graphite vs BLG, Para vs Diag, before vs after.

## Archetype 2: `figureBulletsSummary`

Use for one large visual panel plus concise interpretation bullets.

| object_id | role | x | y | w | h |
|---|---|---:|---:|---:|---:|
| figure | figure | 0.55 | 1.05 | 6.10 | 4.85 |
| bullets | callout | 6.95 | 1.05 | 5.75 | 4.85 |
| summary | summary | 2.20 | 6.12 | 8.95 | 0.52 |
| reference | reference | 0.45 | 7.05 | 8.50 | 0.24 |

Limit the bullet card to 3 bullets. Split the slide if more explanation is required.

## Archetype 3: `formulaTableExplainSummary`

Use for formula + comparison table + short explanation. This archetype prevents the explanation callout from covering the table.

| object_id | role | x | y | w | h |
|---|---|---:|---:|---:|---:|
| formula | formula | 0.55 | 1.05 | 5.95 | 1.45 |
| table | table | 6.82 | 1.05 | 5.95 | 2.20 |
| explanation | callout | 0.55 | 3.55 | 12.22 | 1.85 |
| summary | summary | 2.20 | 6.12 | 8.95 | 0.52 |
| reference | reference | 0.45 | 7.05 | 8.50 | 0.24 |

Hard rule: `explanation.y >= table.y + table.h + 0.20`.

## Archetype 4: `threeCardsSummary`

Use for three mechanisms, three conditions, three evidence blocks, or three-step workflows.

| object_id | role | x | y | w | h |
|---|---|---:|---:|---:|---:|
| card_1 | card | 0.55 | 1.15 | 3.85 | 4.75 |
| card_2 | card | 4.75 | 1.15 | 3.85 | 4.75 |
| card_3 | card | 8.95 | 1.15 | 3.85 | 4.75 |
| summary | summary | 2.20 | 6.12 | 8.95 | 0.52 |
| reference | reference | 0.45 | 7.05 | 8.50 | 0.24 |

Each card should have one short heading and at most two bullets.

## Archetype 5: `fourPanelSummary`

Use for 2x2 figure or result grids.

| object_id | role | x | y | w | h |
|---|---|---:|---:|---:|---:|
| fig_1 | figure | 0.55 | 1.05 | 5.95 | 2.25 |
| fig_2 | figure | 6.82 | 1.05 | 5.95 | 2.25 |
| fig_3 | figure | 0.55 | 3.55 | 5.95 | 2.25 |
| fig_4 | figure | 6.82 | 3.55 | 5.95 | 2.25 |
| summary | summary | 2.20 | 6.12 | 8.95 | 0.52 |
| reference | reference | 0.45 | 7.05 | 8.50 | 0.24 |

Use for parameter scans, multi-panel data, or structure/band/DOS/charge comparisons.

## Archetype 6: `largeFigureSummary`

Use when one visual is the main evidence.

| object_id | role | x | y | w | h |
|---|---|---:|---:|---:|---:|
| figure | figure | 0.65 | 1.00 | 12.00 | 5.35 |
| summary | summary | 2.20 | 6.18 | 8.95 | 0.48 |
| reference | reference | 0.45 | 7.05 | 8.50 | 0.24 |

Use for one important paper figure, structure schematic, method diagram, band plot, phase diagram, or reaction-path plot.

## Failure Handling

If a slide fails layout QA:

1. Identify the collision or clipping failure code from `qa-iteration.md`.
2. Modify the layout box table first.
3. Regenerate the PPTX from the generator code.
4. Re-export preview images.
5. Re-run visual QA.

Do not patch the generated PPTX manually unless the user explicitly asks for manual editing.
