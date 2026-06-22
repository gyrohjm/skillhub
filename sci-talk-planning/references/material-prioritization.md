# Material Prioritization

Use this file to classify source materials as `essential`,
`supporting`, or `cuttable` for the specific talk being planned.

## Classification Rule

Priority is talk-specific, not source-specific. A paper that is
`essential` for a group meeting on charge transfer may be `cuttable`
for a conference talk on structural stability.

Classify each material against the core argument and evidence matrix:

| Priority | Criterion | Treatment |
|---|---|---|
| `essential` | Directly supports a takeaway claim in the evidence matrix. Without it, the argument is incomplete. | Must appear in the talk. Allocate a slide or visual slot. |
| `supporting` | Provides context, background, method detail, or a comparison baseline. Strengthens the argument but is not load-bearing. | Include if time permits. Compress into a table or side reference if not. |
| `cuttable` | Available but not needed for this talk's argument. May be interesting but does not serve the narrative arc. | Omit from the talk. Do not allocate slide time. |

## Source Types

Apply the classification to each source type:

### Papers

- `essential`: the paper provides a figure, data point, or method that
  the claim-evidence matrix depends on.
- `supporting`: the paper provides background context or a comparison
  baseline.
- `cuttable`: the paper is in the reference folder but no claim in the
  matrix depends on it.

### Figures and Plots

- `essential`: the figure is the primary visual evidence for a
  takeaway claim.
- `supporting`: the figure illustrates a method step or provides
  context.
- `cuttable`: the figure is available but no claim requires it.

### Notebooks and Code

- `essential`: the notebook contains the analysis or plot that
  supports a claim.
- `supporting`: the notebook documents the method but the output is
  already extracted.
- `cuttable`: the notebook is exploratory and its results were not
  used.

### Calculation Outputs

- `essential`: the calculation result is cited in the evidence matrix
  as `confirmed` or `preliminary`.
- `supporting`: the calculation provides a parameter or baseline used
  indirectly.
- `cuttable`: the calculation was exploratory and its results were
  superseded.

## Cutting Strategy

When the talk has too much content for the time budget:

1. Cut all `cuttable` materials first.
2. Compress `supporting` materials into tables, comparison rows, or
   single-figure references rather than dedicated slides.
3. Do not cut `essential` materials. If an essential item cannot fit,
   the time budget or the talk scope must be revised, not the evidence.
4. If cutting still does not fit, ask the user to reduce the number of
   takeaways rather than weakening the evidence for remaining ones.

## Output

Record the priority list in `talk_plan.md` section 6 (Material
priorities) as a table:

| Source | Type | Priority | Rationale | Planned slide use |
|---|---|---|---|---|
| `<filename or paper>` | paper / figure / notebook / calculation | essential / supporting / cuttable | `<why>` | `<slide role or omitted>` |

## Rules

- Every source in the evidence matrix must appear in the priority list
  with at least `supporting` priority.
- A source not in the evidence matrix can still be `essential` if it
  provides a method or figure the talk depends on.
- Do not assign `essential` to more than 5-7 items for a 15-minute talk.
  If more are essential, the talk scope is too broad.
