# PPT Content Plan Template

Use this template before generating a PPT from user-provided material. Keep the deck outline and the expanded per-slide content in this same markdown file.

## 1. Source Inventory

| Source | Role | Notes |
|---|---|---|
| `<path or filename>` | lecture / exercise / figure / notebook / reference deck | `<what content it provides>` |

## 2. Deck Mode And Scope

- Deck mode: research report / classroom lecture / review / exercise-session / single-topic / targeted edit.
- Target audience: research group meeting / classroom lecture / course review / exercise class / thesis defense.
- Language: English by default / Chinese / user-specified language.
- Report topic:
- Date:
- Presenter:
- Expected slide count:
- Generation route: `pptxgenjs` JavaScript + MathJax-rendered formula images.
- Output PPTX path:
- Generator script path:
- Reference folder inventory path, if applicable:

## 3. Deck Outline

Write this section before expanding slide content. This is the first-pass structure of the deck and should remain in the same markdown document as the expanded plan.

| Slide | Draft title | Main message | Required evidence / object | Planned visual count | Bottom conclusion |
|---:|---|---|---|---:|---|
| 1 | `<cover title>` | `<deck topic>` | topic, date, presenter | 0-1 | cover slide |
| 2 | `Outline` / `<outline title>` | `<storyline of the deck>` | 3-6 outline items | 1 | outline slide; no bottom conclusion box |
| 3 | `<declarative title>` | `<one sentence>` | figure / table / formula / code | `<=4` | `<one sentence>` |
| Last | `Conclusion` | `<main takeaways>` | takeaway table / key figure / next-step list | 1-3 | conclusion slide |

Rules:

- Include a cover slide with report topic, date, and presenter unless the user explicitly asks for one inserted slide.
- Include a PPT outline/storyline slide immediately after the cover unless explicitly exempted.
- Include a final conclusion slide for every complete deck unless explicitly exempted.
- Use English by default unless the user specifies another language.
- Use titles that state the main point, not generic labels.
- Plan at most 4 visual objects and 3 sentences per ordinary content slide; allow 4 sentences only for data-heavy method/result pages.
- Prefer at least one figure, plot, diagram, formula, or table on evidence-bearing slides.
- Prefer tables for comparisons, parameters, evidence mapping, and method/result summaries.
- Plan one bottom conclusion sentence for every content slide, but not for the outline slide.

## 4. Expanded Slide Content

Expand the outline here after the storyline is coherent. This section is the final page-level content used by the PPT generator.

| Slide | Final title | Page role | Text / bullet content | Visual objects | Bottom conclusion | Speaker notes |
|---:|---|---|---|---|---|---|
| 1 | `<cover title>` | cover | topic, date, presenter | none / optional subtitle card | cover slide | how to introduce the talk |
| 2 | `Outline` | outline | 3-6 section items | optional simple section table | outline slide; no conclusion box | how the sections connect |
| 3 | `<declarative title>` | content | at most 3 sentences or bullet sentences | at most 4 figures/tables/formulas/code boxes | `<one sentence>` | speaking order, caveats, LaTeX source if any |
| Last | `Conclusion` | conclusion | 2-3 takeaways or compact table | optional summary table / schematic / next-step list | conclusion slide | how to close the talk |

Rules:

- The Deck Outline and Expanded Slide Content sections must stay in this same markdown plan.
- Do not create a second markdown file just for the expanded content.
- If a content slide exceeds the density limit, split it in the outline before generating PPT.
- Every planned visual object must appear again in the visual traceability table below.
- Every slide must have speaker notes in the generated PPT.

## 5. Visual Object Traceability

Use this table to prevent false completion. Each planned visual object must be traceable to a source and to an actual PPT object or explicit failure state.

| Slide | Object role | Source / asset | Planned use | Actual PPT status | Evidence or failure note |
|---:|---|---|---|---|---|
| 3 | paper figure / formula / table / code | `<PDF page, figure no., notebook output, image path, LaTeX source>` | `<why this object is needed>` | inserted / generated / text-only fallback / pending crop / omitted | `<PPT object, asset filename, or reason>` |

Rules:

- Use `inserted` only when the object is visibly present in the exported preview.
- Use `generated` for charts, formulas, or tables created by code and visible in preview.
- Use `pending crop` if the source figure is identified but not yet cropped.
- Use `omitted` only with a reason and without checking the corresponding QA item as passed.
- Do not let a slide claim a paper figure, spectrum, structure model, or comparison chart when the PPT contains only text.
- If a paper figure cannot be cropped, reserve a visible placeholder frame in the PPT and write the target paper, figure/page, and expected content in this table.

## 6. Knowledge Or Exercise Coverage

For research reports:

| Section | Must include | Evidence / figure / table | Omit or compress |
|---|---|---|---|
| background / method / result / limitation | `<key claims>` | `<objects>` | `<low-priority details>` |

For reference-folder group meeting decks:

| Source file | Paper / figure / note role | Claim or information extracted | Slide use |
|---|---|---|---|
| `<filename>` | paper / figure / note / data / prior slide | `<key fact, method, result, limitation>` | background / method / evidence / comparison / discussion |

Claim-evidence map:

| Claim | Evidence source | Figure/table/formula | Confidence / caveat |
|---|---|---|---|
| `<declarative claim>` | `<paper/image/page>` | `<object>` | `<boundary>` |

For review decks:

| Topic | Must include | Formula / table / figure | Omit or compress |
|---|---|---|---|
| `<topic>` | `<key concepts>` | `<objects>` | `<low-priority details>` |

For exercise decks:

| Exercise | Full statement source | Solution elements | Required figure/table/code |
|---|---|---|---|
| `<n.m>` | `<PDF/page/image>` | analysis, formula, code, result | `<objects>` |

## 7. Slide Blueprint

| Slide | Title | Main message | Content objects | Notes |
|---:|---|---|---|---|
| 1 | `<declarative title>` | `<one sentence>` | formulas / table / code / figure | `<layout notes>` |

Rules:

- Use formal declarative slide titles.
- Avoid conversational phrasing.
- Keep each slide to one main message.
- Use at most 4 visual objects per content slide.
- Use at most 3 full sentences or bullet sentences per ordinary content slide.
- Use at most 4 full sentences only for data-heavy method/result pages.
- Add one bottom conclusion sentence to each content slide.
- Keep teaching text at least 20 pt and headings at least 22 pt.
- Standardize formula image sizes by role.

## 8. Formula And Visual Plan

| Object | LaTeX / source | Display role | Size rule |
|---|---|---|---|
| `<formula>` | `<latex>` | inline / standard / main / derivation | `<box height>` |

Rules:

- Keep the original LaTeX source in the generator and in the speaker notes for the slide that displays the rendered formula image.
- If a formula is split across multiple images, list each LaTeX source separately in the notes.

## 9. Speaker Notes Plan

Every generated slide must have notes. Use this table before writing the generator.

| Slide | Notes content | Formula LaTeX source to preserve |
|---:|---|---|
| 1 | `<how to introduce the deck>` | none |
| 2 | `<how to explain the outline; no bottom conclusion box>` | none |
| 3 | `<speaking order and caveats>` | `<latex source or none>` |

## 10. Writing Pass

Use evidence statements rather than bare checkmarks.

| Item | Evidence / slide reference | Result |
|---|---|---|
| Outline was written before expansion | `<section and slide refs>` | pass / fail |
| Outline and expanded content are in one markdown plan | `<file path>` | pass / fail |
| PPT includes cover and outline slide | `<preview slide refs>` | pass / fail |
| PPT includes a final conclusion slide | `<preview last slide>` | pass / fail |
| Titles state the main message | `<slides checked>` | pass / fail |
| Each content slide has a bottom conclusion sentence; outline slide has none | `<slides checked; list exceptions>` | pass / fail |
| No content slide exceeds 4 visual objects | `<slides checked>` | pass / fail |
| No ordinary content slide exceeds 3 full sentences or bullet sentences | `<slides checked>` | pass / fail |
| Data-heavy slides with 4 sentences are justified | `<slides checked or none>` | pass / fail |
| Evidence-bearing slides use figures/tables/formulas where available | `<slides checked>` | pass / fail |
| Planned visual objects are inserted or explicitly marked missing | `<traceability rows checked>` | pass / fail |
| Every slide has speaker notes | `<slides checked>` | pass / fail |
| Formula LaTeX source is preserved in speaker notes | `<formula slides checked>` | pass / fail |
| Conversational and AI-like filler phrases were removed | `<slides checked>` | pass / fail |
| Claims match evidence strength | `<claims checked>` | pass / fail |

## 11. QA Checklist

Do not use a checkbox-only QA list. Record specific preview evidence.

| Category | Check | Evidence / failed slide | Result |
|---|---|---|---|
| Content | Source statements and formulas are traceable | `<slide refs>` | pass / fail |
| Content | Slide sequence has a coherent storyline | `<slide refs>` | pass / fail |
| Content | Deck language follows default English or user-specified language | `<slide refs>` | pass / fail |
| Layout | Cover metadata is visible and not clipped | `<preview slide 1>` | pass / fail |
| Layout | Outline slide text stays inside page bounds and has no bottom conclusion box | `<preview slide 2>` | pass / fail |
| Layout | No card, text, table, or conclusion box is clipped | `<failed slide refs or pass evidence>` | pass / fail |
| Layout | Figure crops preserve readability and aspect ratio | `<figure slide refs>` | pass / fail |
| Layout | Figure placeholders are used when crops are unavailable | `<placeholder slide refs or none>` | pass / fail |
| Notes | Every slide contains speaker notes | `<slides checked>` | pass / fail |
| Notes | Rendered formula slides include LaTeX source in notes | `<formula slide refs>` | pass / fail |
| Citation | Single-source and multi-source citations follow rules | `<slide refs>` | pass / fail |
| Technical | PPTX opens and exports via PowerPoint | `<verify output>` | pass / fail |
| Technical | Preview images were visually inspected | `<preview folder and slide refs>` | pass / fail |
| Traceability | Planned visual objects match actual PPT objects | `<traceability rows>` | pass / fail |

## 12. AI Review Iterations

| Iteration | Preview path | Findings | Fixes applied | Result |
|---:|---|---|---|---|
| 1 | `<preview folder>` | `<content / layout / technical issues>` | `<generator or asset changes>` | pass / repeat / blocked |
