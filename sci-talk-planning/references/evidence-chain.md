# Evidence Chain

Use this file to build the claim-evidence matrix in `talk_plan.md`.

## Matrix Structure

For each takeaway claim, create one or more evidence rows:

| Claim | Evidence | Type | Strength | Source | Limitation |
|---|---|---|---|---|---|
| `<declarative takeaway>` | `<what evidence supports it>` | calculation / experiment / published / inferred | confirmed / preliminary / inferred / pending | `<file, paper, notebook, figure>` | `<boundary or caveat>` |

## Evidence Strength Levels

| Level | Definition | Usage rule |
|---|---|---|
| `confirmed` | Completed calculation or experiment with validated output, or a claim from a peer-reviewed paper with no known contradiction. | Can support a strong declarative takeaway. |
| `preliminary` | In-progress calculation, unvalidated result, or a single-run output without convergence check. | Can support a takeaway only with an explicit caveat in the talk plan. |
| `inferred` | Not directly computed or measured; derived from analogy, literature interpolation, or theoretical reasoning. | Cannot support a strong takeaway. Must be paired with `confirmed` evidence or downgraded to a hypothesis. |
| `pending` | Evidence is planned but not yet available. | The talk plan must mark the gap and recommend either completing the work before the talk or using a placeholder. |

## Gap Analysis

After filling the matrix:

1. List any claim with no evidence row as `evidence gap`.
2. List any evidence row with strength `pending` and no fallback as
   `delivery risk`.
3. If a takeaway relies entirely on `preliminary` or `inferred`
   evidence, recommend that the user either:
   - downgrade the takeaway to a hypothesis, or
   - add a `confirmed` evidence item before the talk.
4. If there is a competing explanation that the evidence cannot rule
   out, record it as `alternative interpretation` in the limitation
   column.

## Source Tracking

Each evidence row must trace to a concrete source:

- For calculations: project path, system slug, case slug, and output
  file.
- For experiments: notebook path, figure number, or raw data file.
- For published papers: author, journal, year, page/figure number.
- For user-provided notes: note file or conversation reference.

Do not leave the source column empty. If the source is unknown, write
`unspecified` and flag the row for user confirmation.

## Rules

- One claim can map to multiple evidence rows. List them all.
- One evidence item can support multiple claims. Cross-reference it.
- Do not invent evidence. If the user mentions a result but cannot
  provide the source, mark strength as `pending` and source as
  `unspecified`.
- Limitations are mandatory for `preliminary` and `inferred` rows. They
  are recommended for `confirmed` rows when the evidence has a boundary
  condition.
