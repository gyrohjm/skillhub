# Talk Plan Contract

Use this file to validate `talk_plan.md` before handing off to
`simple-sci-ppt`.

## Required Sections

`talk_plan.md` must contain these sections in this order. Missing or
empty sections are hard failures.

### 1. Talk Metadata

| Field | Required | Example |
|---|---|---|
| `talk_type` | yes | group meeting / conference / thesis defense / classroom lecture / invited seminar / progress update |
| `title` | yes | declarative title, not a generic label |
| `presenter` | yes | user name or placeholder |
| `date` | yes | talk date |
| `duration` | yes | total minutes including Q&A |
| `audience` | yes | brief description |
| `language` | yes | Chinese (default) / English / other |

### 2. Core Argument

- 1-3 takeaway statements.
- Each statement is declarative and falsifiable.
- Each statement maps to at least one evidence row in section 5.

### 3. Audience Profile

- Who they are: specialists, mixed research group, students, committee.
- Knowledge baseline: what they already know vs. what needs explaining.
- Expectations: what the audience expects from this talk type.

### 4. Narrative Arc

| Section | Purpose | Time (min) | Approx slides | Archetype | Is climax |
|---|---|---|---|---|---|
| `<section name>` | `<why>` | `<min>` | `<count>` | `<archetype name>` | yes / no |

- Exactly one section must be marked as the climax.
- The archetype must match one from `narrative-archetypes.md` or be a
  justified custom structure.
- Total time must not exceed the talk duration minus Q&A buffer.

### 5. Claim-Evidence Matrix

| Claim | Evidence | Type | Strength | Source | Limitation |
|---|---|---|---|---|---|

- Every claim in section 2 must appear in at least one row.
- No row may have an empty `source` field. Use `unspecified` if unknown
  and flag for confirmation.
- `preliminary` and `inferred` rows must have a non-empty `limitation`.

### 6. Material Priorities

| Source | Type | Priority | Rationale | Planned slide use |
|---|---|---|---|---|

- Every source referenced in the evidence matrix must appear here.
- At least one source must be `essential`.
- `essential` count should not exceed 5-7 for a 15-minute talk.

### 7. Predicted Questions

| Question | Likelihood | Response strategy | Evidence to cite |
|---|---|---|---|

- List at least 2 questions for any talk longer than 10 minutes.
- Each question should map to evidence in the matrix or to a known
  limitation.

### 8. Handoff to simple-sci-ppt

| Field | Required | Example |
|---|---|---|
| `recommended_deck_mode` | yes | research report / classroom lecture / review / exercise / single-topic |
| `approx_slide_count` | yes | integer |
| `key_figures` | yes | list of figure IDs or descriptions that must appear |
| `language` | yes | Chinese / English / other |
| `citation_style` | no | if specific style needed |
| `visual_constraints` | no | any known constraints |

## Validation Checklist

Before presenting `talk_plan.md` to the user:

- [ ] All 8 sections are present and non-empty.
- [ ] Every takeaway claim has at least one evidence row.
- [ ] No evidence row has an empty source.
- [ ] `preliminary` and `inferred` rows have limitations.
- [ ] Exactly one narrative section is marked as climax.
- [ ] Total section time does not exceed duration minus Q&A buffer.
- [ ] Every evidence-matrix source appears in material priorities.
- [ ] At least 2 predicted questions for talks longer than 10 minutes.
- [ ] Handoff section specifies deck mode and slide count.
- [ ] No slide-level details (layout archetypes, coordinates, generator
      code) appear anywhere in the plan.

If any item fails, fix the plan before presenting to the user.

## Backward Compatibility

`simple-sci-ppt` can operate without `talk_plan.md`. In that case it
performs a lightweight inline version of these decisions. But when
`talk_plan.md` is present, `simple-sci-ppt` must use it as the primary
input for sections 1-3 of its slide-level markdown plan and must not
re-derive the narrative arc, audience profile, or claim-evidence matrix.
