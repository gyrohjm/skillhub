# Reference-Folder Group Meeting Workflow

Use this when the user provides a folder such as `refs/` with papers, images, notes, data, code, notebooks, or previous slides and asks for a group meeting, literature report, paper reading, or research update deck.

## Narrative Design

Narrative storyline design for group meeting decks is owned by
`sci-talk-planning`. If a `talk_plan.md` is available, use its narrative
arc, claim-evidence matrix, and material priorities as input for the
slide plan. Do not re-derive the storyline.

If no `talk_plan.md` is available, ask the user for minimum context
(core argument, audience, time) and proceed with a lightweight inline
version. The storyline structure below can serve as a reference template
for the inline case.

## Required Flow

1. If a `talk_plan.md` exists, read it first. Import its material
   priorities and claim-evidence matrix.
2. Run `scripts/inventory_refs.py <refs-folder> --out <plan-dir>/refs_inventory.md`.
3. Classify materials into papers, figures, notes, datasets/code, and previous slides.
4. Extract paper metadata: title, authors, year, journal/conference, DOI/arXiv ID if available, research question, method, main result, and limitation.
5. Inspect figures and captions. Mark each candidate image as evidence, mechanism, workflow, result comparison, or background illustration.
6. For PDF-derived visuals, render every candidate page to an image screenshot and inspect that screenshot before deciding the crop or placeholder.
7. Crop paper figures directly from PDF-rendered pages before PPT insertion. Use `scripts/crop_pdf_figure.py` for reproducible crops.
8. Build a slide-level markdown plan with source inventory (imported from talk plan if available), claim-evidence map (imported from talk plan if available), selected figures, comparison tables, visual-object traceability, rendered PDF page screenshots, speaker notes, and slide-by-slide outline.
9. Generate the PPTX with `pptxgenjs`.
10. Run the AI review loop in `qa-iteration.md`.

## Paper Figure Crops

Do not insert full article pages unless the slide is explicitly about page layout or no clean crop is possible.

Good paper-figure crops:

- include the relevant panel or figure group,
- preserve axis labels, legends, panel labels, and scale bars,
- remove unrelated article columns and footers,
- keep the source PDF, page number, rendered page screenshot path, crop box, and output file in the markdown plan.

Render the full candidate PDF page to an image and inspect it visually before selecting the crop box. This is mandatory for PDF-derived figures, tables, equations, or diagrams because text extraction alone is not reliable enough for crop boundaries.

If an agent cannot infer crop coordinates after visual inspection, it should keep the rendered page screenshot path, insert a placeholder frame, and record the reason.

For each selected paper figure, record its state in the markdown plan:

- `selected`: figure is relevant but not yet cropped,
- `page-rendered`: candidate PDF page screenshot exists and was inspected,
- `cropped`: crop asset exists,
- `inserted`: crop appears in exported PPT preview,
- `pending crop`: the PPT contains a visible placeholder frame because the current agent/toolchain cannot crop or extract the figure,
- `omitted`: figure was not used, with reason.

Do not describe a slide as containing a paper figure unless the status is `inserted`. If the figure is necessary but unavailable, reserve the slide space with a placeholder frame instead of filling the area with extra prose.

Placeholder frame requirements:

- Write `待插入：<paper>，<figure/page>` as the first line.
- Write `内容：<expected visual content>` as the second line.
- Write `状态：待裁剪 / 需人工插入` as the third line.
- Keep the placeholder inside a figure card at the same size and position where the final image should appear.
- Record the rendered page screenshot path in the speaker notes when available; if unavailable, record the rendering failure reason.

## Group Meeting Storyline Reference

When no `talk_plan.md` is available and a lightweight inline storyline
is needed, prefer this structure:

1. Research question and source set.
2. Background and unresolved problem.
3. Method/model or experimental design.
4. Key evidence from cropped paper figures.
5. Comparison across papers or methods.
6. Limitations and discussion points.
7. Next experiment/calculation or reading target.

Avoid paper-by-paper summary unless explicitly requested. Select claims
and figures that support the storyline.

For group meeting decks, prefer:

- cropped paper figures for direct evidence,
- compact tables for literature comparison, method parameters, model assumptions, and unresolved questions,
- generated schematics when the sources describe a mechanism but provide no reusable figure,
- speaker notes that explain how to connect each evidence object to the slide claim.

Avoid text-only literature slides when a figure, table, or schematic can carry the evidence more clearly.

## Citation Footer

If one slide mainly cites one paper, place the citation at the lower-left in 16 pt.

Format:

`first corresponding author et al. + abbreviated journal + volume + pages + (year)`

Rules:

- journal abbreviation is italic,
- volume is bold,
- use a consistent footer style across the deck,
- if one slide cites multiple papers, cite each referenced content block separately near that block.
- do not replace local citations with one undifferentiated source list when different blocks come from different papers.
- for multi-source comparison tables, put a short citation under each column, row group, or figure card that uses that source.
- a compact source list at the lower-left is acceptable only when the whole slide jointly summarizes the same source set and no block-level attribution is needed.

Example:

`Lin et al. ACS Nano 19 40612-40619 (2025)`, with `ACS Nano` italic and `19` bold.

`pptxgenjs` rich text helper pattern:

```js
slide.addText([
  { text: "Lin et al. ", options: { fontSize: 16 } },
  { text: "ACS Nano", options: { fontSize: 16, italic: true } },
  { text: " ", options: { fontSize: 16 } },
  { text: "19", options: { fontSize: 16, bold: true } },
  { text: ", 40612-40619 (2025)", options: { fontSize: 16 } },
], { x: 0.45, y: 6.86, w: 8.5, h: 0.24, fontFace: "Arial", color: "5B6472", margin: 0 });
```

For multi-source slides, use the same rich text style but place each citation near the corresponding content object:

```js
// Under the left comparison column.
slide.addText(puechCitationRuns, { x: 2.3, y: 3.40, w: 4.2, h: 0.22, fontFace: "Arial", fontSize: 16, color: "5B6472", margin: 0 });

// Under the right comparison column.
slide.addText(linCitationRuns, { x: 7.4, y: 3.40, w: 4.2, h: 0.22, fontFace: "Arial", fontSize: 16, color: "5B6472", margin: 0 });
```
