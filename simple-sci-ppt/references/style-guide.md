# Style Guide

## Default Visual System

Use a classroom board style similar to a well-organized exercise-session slide, not a plain corporate blue-white report deck.

- Background: plain white. Do not add background grids, dotted grids, or PowerPoint editing-view guide patterns unless the user explicitly requests them.
- Header: large exercise/topic title on the left. Do not place small topic text in the upper-right corner.
- Header divider: one thin dark-blue horizontal line under the title area.
- Main layout: left side for derivation/formula cards, right side for code or figure cards.
- Containers: rounded rectangles with pale fills and thin colored borders.
- Semantic colors: blue for definitions/principles, orange for weights/conclusions/code tags, red only for highlighted code or critical terms.
- Page number: bottom-right only, gray, no total page count.
- Avoid decorative gradients, shadows, dense icons, and large empty title pages.

The deck should feel like a carefully typeset teaching slide, not an editing screenshot and not a corporate template.

Default language: use English for slide text unless the user specifies Chinese or another language. Keep Chinese typography rules available for Chinese decks, but do not default to Chinese wording.

## Slide Anatomy

| Region | Rule |
|---|---|
| Left header | `习题 n.m：题目/主题` or concise research topic, 26-30 pt, bold, black |
| Right header | Empty by default |
| Divider | Thin blue line at y about 0.70-0.80 in |
| Left body | 2-3 formula cards stacked vertically |
| Right body | code card, algorithm box, result figure, or comparison table |
| Bottom callout | Required one-sentence summary card, pale orange fill, blue border, 20-22 pt |

Every content slide should have one bottom conclusion sentence. Use a pale orange callout or an equivalent low-emphasis conclusion band. Keep it to one short sentence at 20-22 pt, usually one line. Do not use the conclusion box as an extra paragraph area. Outline slides do not use bottom conclusion boxes.

## Safe Layout Region

Use the 16:9 layout as `13.333 x 7.5` inches. Keep ordinary objects inside these safe bounds:

| Object | Safe rule |
|---|---|
| Header title | `x >= 0.30`, `y <= 0.15`, `x + w <= 12.60` |
| Body cards / figures / tables | `0.40 <= x`, `0.95 <= y`, `x + w <= 12.90`, `y + h <= 6.70` |
| Bottom conclusion box | recommended `y = 6.02-6.12`, `h <= 0.72`, `y + h <= 6.84` |
| Citation footer | `y = 7.02-7.08`, `h <= 0.22`; keep separate from conclusion box |
| Page number | bottom-right only; it is the only ordinary object allowed near `x > 12.50`, `y > 7.00` |

Hard failures:

- any card, text box, table, or image extends beyond the slide boundary,
- bottom conclusion text is clipped or overlaps the citation,
- bottom conclusion box covers the citation footer or page number region,
- outline slide contains a bottom conclusion box,
- right-side cards are partially off-screen,
- cover metadata is cut off at the bottom,
- outline text is cut off on the right.

When a slide needs more space, split the slide. Do not shrink teaching text below 20 pt or move content outside the safe region.

Conclusion placement:

- Use a centered bottom callout by default: `x = 2.2-3.0`, `y = 6.02-6.12`, `w = 7.2-8.8`, `h <= 0.72`.
- Keep the conclusion to one compact sentence, normally no more than about 14 English words, 32 Chinese characters, or one concise bilingual sentence.
- If a slide has a citation footer, place the citation below the conclusion region at the lower-left, never inside or behind the conclusion box.
- If the conclusion needs two lines, shorten the sentence or split the slide. Do not grow the box downward.

For exercise-session PPTs, the preferred page rhythm is:

1. Problem statement and target quantity.
2. Formula transformation or numerical principle.
3. Code implementation or algorithm flow.
4. Result, error behavior, and interpretation.

## Cover Slide

Every new deck should include a cover slide unless the user asks for a single slide or an insertion into an existing deck.

Cover layout:

- White background.
- Large report topic at left, 34-40 pt, bold.
- Thin dark-blue divider under the title block.
- One small orange accent line or block near the title.
- Metadata near the lower-left: `汇报人：...` and `时间：...`, 20-22 pt; keep the full metadata box visible above `y = 6.45`.
- Optional subtitle or source scope in a blue-outline card, 20-22 pt.
- No upper-right topic text.
- No page number on the cover unless matching an existing deck.

Use placeholders when metadata is missing. Do not invent the presenter's name or exact date.

## Outline Slide

Every new deck should include an outline/storyline slide immediately after the cover unless the user asks for a single inserted slide or explicitly removes the outline.

Outline layout:

- Use the normal content-slide header, usually `Outline` or a more specific storyline title.
- Keep 3-6 outline items.
- Each item should name a section and its purpose, not merely list generic words.
- Prefer stacked cards or a two-column card layout. Avoid one long full-width line per item.
- Use 22-24 pt for outline item labels and 20-22 pt for descriptions.
- Do not add a bottom conclusion sentence or bottom conclusion box to the outline slide.
- Keep each item label short, roughly within 5 English words or 28 Chinese characters, and use one short sentence for the purpose.

Good outline items:

- `问题定义：明确数值误差来自舍入、截断和算法稳定性。`
- `方法比较：用公式和代码对应不同求解策略。`
- `结果解释：从误差曲线判断方法适用范围。`

Avoid:

- `背景`
- `方法`
- `结果`
- `总结`

## Conclusion Slide

Every complete deck should end with a conclusion slide unless the user explicitly asks for a single inserted page or partial deck.

Conclusion slide layout:

- Use a declarative title such as `Conclusion: ...`, not a generic `Summary` when a clearer claim exists.
- Prefer a compact takeaway table, 2-3 key conclusions, or a final schematic/evidence map.
- Include limitations or next steps when they are supported by the source material.
- Do not duplicate every section title. Synthesize the main technical implications.
- Speaker notes should provide the closing script and any caveat that should be stated orally.

## Card Types

| Card type | Fill | Border | Label color | Typical use |
|---|---|---|---|---|
| Definition card | `#E8F2FA` with about 70-80% transparency | `#1D4E89` | dark blue | definitions, transformed integrals, criteria |
| Formula card | `#EEF6FC` with about 70-80% transparency | `#1D4E89` | dark blue | core derivation, estimator, variance |
| Weight/conclusion card | `#FFF0DE` with about 70-80% transparency | `#D66A13` or `#2F6FD6` | dark blue/orange | weights, assumptions, final observations |
| Code card | near white or very pale blue | light blue border | orange tab | core Python function or pseudocode |
| Warning/emphasis | no full red box | no red border unless necessary | red text | one or two key lines only |

Card rules:

- Use rounded corners with thin borders.
- Put short labels such as `权重`, `方差`, `关键代码` near the upper-left of each card.
- Keep labels at 22-24 pt and bold.
- Use the starter template's card helpers instead of manually scattering `addText` and `addShape` coordinates.
- Keep formula images visually consistent by fixed card height rather than raw MathJax output size.
- Do not let the formula image become tiny. Split the formula or move it to another slide.

## Tables

Tables should be generated through a fixed table helper or manually drawn rectangles with fixed column widths. Do not rely on unconstrained full-width `addTable` output for dense comparison pages.

Rules:

- Prefer tables over prose for method comparisons, parameter lists, evidence maps, benchmark results, and literature contrasts.
- Keep table `x + w <= 12.70` and `y + h <= 6.55`.
- Use no more than 4 columns at 20 pt body text. If 5+ columns are needed, split the table or use two smaller tables.
- Keep each cell to 1-2 short lines.
- For method-comparison tables, prefer columns such as `方法`, `证据`, `结论`, `局限` instead of long prose fields.
- If the table must use 16-18 pt text, it is a compact reference table and cannot carry the slide's main explanation.

## Fonts And Sizes

- Chinese font: SimHei / 黑体.
- English font: Arial.
- Code font: Consolas.
- Main slide title: 26-30 pt, bold, left-aligned, black.
- Card label / small heading: 22-24 pt, bold.
- Body text: 20-22 pt. Do not use teaching text below 20 pt.
- Formula label: 22-24 pt, bold.
- Formula content: size to match 24-32 pt visual height where possible.
- Code: 18-20 pt. Use 20 pt for the main snippet when space allows; use 18 pt only for dense but still readable code.
- Page number: 18 pt, gray.
- Short annotations, comments, and references: 16-18 pt.

Only code, comments, short annotations, references, and page markers may use fonts below 20 pt. All ordinary teaching prose, derivation labels, conclusions, and comparison text must stay at 20 pt or above.

If a slide needs smaller teaching text, split it. Do not shrink below readability.

## Color Roles

| Role | Color | Usage |
|---|---|---|
| Black `#111111` | Main title and body text | default reading color |
| Dark blue `#174F8A` | formula borders, labels, divider | primary structure color |
| Pale blue `#E8F2FA` | formula card fill | derivation and principle cards |
| Orange `#D66A13` | code tabs and weight borders | code labels, sampling weights, important transitions |
| Pale orange `#FFF0DE` | conclusion/weight card fill | bottom callouts and weight cards |
| Red `#E00000` | highlighted code or critical equality | use sparingly |
| Gray `#5B6472` | page number, citations, and compact metadata | metadata only |
## Formula And Code

- Render LaTeX formulas into image objects before inserting them into PPT. Use MathJax as the default renderer. PNG is preferred when a downstream environment has SVG issues; SVG is acceptable only after PowerPoint export confirms it is visible. Raw LaTeX text is acceptable only as an explicit failure fallback and must be reported.
- Keep formula source strings in the `pptxgenjs` generator itself, not only in generated asset files. The generator should treat LaTeX source as truth, then emit formula assets automatically.
- Preserve the original LaTeX source in the slide speaker notes for every rendered formula image.
- Use fixed formula boxes and consistent formula viewport sizes. Store generated formula images in a local asset directory such as `.simple_sci_ppt_assets/formulas/` so the deck can be regenerated.
- Prefer a dual-asset pattern: keep a MathJax-generated `SVG` for maintenance and archive purposes, and insert a generated `PNG` into PowerPoint when SVG visibility is unreliable.
- Use `bmatrix` for matrices.
- In exercise slides, equations should carry the reasoning. Avoid replacing derivations with prose.
- Code cards should show only the key function or algorithm core.
- Highlight only the lines being discussed in red, usually 1-3 lines.
- Do not place full notebook code in PPT.

## Exercise PPT Content Rules

- Include the full problem statement when introducing an exercise.
- Keep the title explicit, for example `习题 10.19：重要性抽样`.
- Ensure titles communicate the local purpose or conclusion.
- Use multiple pages for one exercise when needed.
- Each page should have a clear local purpose: transformation, estimator, code, result, or interpretation.
- Keep ordinary content slides to at most 4 visual objects and 3 full sentences or bullet sentences.
- Allow 4 sentences only for data-heavy method/result pages, and record the reason in the markdown plan.
- If a slide needs more than 4 sentences, split it or convert details into a table/figure annotation.
- Prefer figure/table/formula-led explanations over text-only pages. Text-only content slides need a reason in the markdown plan.
- Add one bottom conclusion sentence to every content slide.
- Use formal declarative language. Avoid chatty phrases such as `我们来看`, `这个很重要`, `简单来说`, `大家注意`.
- Avoid `考试重点`, `必背`, `速查`, `秒懂`.

## Review Or Research Deck Adaptation

The same visual grammar can be used for non-exercise decks:

- Replace `习题 n.m` with the topic or section title.
- Use formula cards for models, assumptions, or objective functions.
- Use figures, cropped paper panels, generated plots, schematics, and tables as the default evidence carriers.
- Use code cards only when implementation details matter.
- Use tables for method comparison, parameter choices, limitations, and evidence mapping.
- Keep the white-background card system unless the user explicitly asks for a different report style.

For group meeting decks generated from a reference folder:

- Use one slide to establish the research question and source set.
- Use figure cards for the most important evidence and tables for paper-to-paper comparison.
- Crop paper figures directly from PDF-rendered pages when possible. Insert the cropped figure panel or figure group, not a full article page.
- If a paper figure cannot be cropped or extracted by the current agent/toolchain, insert a visible placeholder frame instead of replacing the figure with prose. The placeholder must state the target paper, figure/page, expected visual content, and status such as `待裁剪 / 需人工插入`.
- Use a unified citation footer. If one slide mainly cites one paper, place the citation at the lower-left in 16 pt.
- Citation format: `first corresponding author et al. + abbreviated journal + volume + pages + (year)`.
- Set the journal abbreviation in italic and the volume number in bold.
- Example: `Lin et al. ACS Nano 19 40612-40619 (2025)`, with `ACS Nano` italic and `19` bold.
- If one slide uses multiple papers, place each citation near the specific text, table column, or figure card it supports.
- Avoid one generic bottom source list when different parts of the slide come from different papers.
- Keep discussion pages concrete: unresolved mechanism, parameter sensitivity, method limitation, or next experiment/calculation.
- Avoid turning every paper into a separate summary slide unless the user explicitly asks for a paper-by-paper reading report.

## Figures

- Generated plots should avoid internal titles.
- Use English labels in figures.
- Prefer blue-orange tones.
- Axis labels should generally be at least 22 pt in source figures.
- Preserve image aspect ratio in PPT.
- Place figures inside bordered cards when mixed with formulas or code.
- Paper-figure crops must preserve readable axis labels, legends, panel labels, and scale bars.
- Evidence-bearing research slides should normally include a figure, table, formula, or diagram. Avoid replacing available source images with prose.

## Speaker Notes

- Add speaker notes to every slide using `slide.addNotes(...)`.
- Notes should describe how to present the slide, including the intended order of formulas, figures, tables, or code.
- Notes may be longer than slide text, but should remain formal and useful as a speaking guide.
- For each rendered formula image, include a `LaTeX source:` block in the notes.
- For figure placeholders, notes should state exactly which paper figure/page should be inserted later.



