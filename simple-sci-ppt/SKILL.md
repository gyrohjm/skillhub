---
name: simple-sci-ppt
description: Create, revise, and verify formal academic PowerPoint decks with formula/image/table/code cards, section tabs, and semantic containers for research reports, lectures, course reviews, exercise sessions, thesis/group meetings, and single-topic scientific slides. Use when Codex is asked to use simple-sci-ppt, simple_sci_ppt, or simple_sci_ppt_gen, or to turn PDFs, PPTX files, notes, papers, notebooks, figures, or reference folders into a planned PPTX with Markdown planning, MathJax formulas, editable `pptxgenjs` objects, speaker notes, and PowerPoint validation. This skill owns slide-level planning and PPTX generation. For narrative design, use `sci-talk-planning` first and pass its `talk_plan.md`.
---

# simple-sci-ppt

## Talk Plan Integration

This skill accepts an optional `talk_plan.md` from `sci-talk-planning` as
upstream input. When present, the talk plan provides the deck mode,
audience profile, narrative arc, claim-evidence matrix, and material
priorities. Use these to pre-fill sections 1-3 of the markdown slide plan
(see `references/md-plan-template.md`). Do not re-derive narrative-level
decisions that the talk plan already settled.

When no `talk_plan.md` is available, this skill can operate independently.
Ask the user for minimum context (core argument, audience, talk duration)
and perform a lightweight inline version of these decisions.

## Core Workflow

0. If a `talk_plan.md` from `sci-talk-planning` is available, read it
   first and use its narrative arc, claim-evidence matrix, material
   priorities, and audience profile as input for the slide plan. If no
   talk plan exists, ask the user for minimum context (core argument,
   audience, time) before proceeding to slide-level planning.
1. Confirm the deck mode. If a talk plan exists, use its
   `recommended_deck_mode`. If not, determine from user input:
   research report, reference-folder group meeting report, classroom
   lecture/review, exercise session, targeted edit, or single-topic
   slide.
2. Read `references/style-guide.md` before visual work.
3. Read `references/layout-archetypes.md` before placing ordinary content-slide objects. Pick one archetype per content slide unless the user explicitly asks for a custom layout.
4. Read `references/workflow.md` for the common generation sequence.
5. Read `references/content-writing.md` before writing slide text.
6. Read `references/mineru-pdf-policy.md` before using any figure, table, formula, caption, or diagram from a PDF.
7. For reference-folder or literature-report decks with PDFs, also read `references/reference-folder-mineru-addendum.md`.
8. Default to Chinese deck text unless the user explicitly requests English or another target language.
9. When using figures, panels, tables, formulas, or diagrams from PDFs, first run MinerU (`scripts/mineru_extract.py`) to parse the PDF into structured Markdown and extracted images. If MinerU fails, ask the user whether to retry before falling back to lower-level parsing tools.
10. Render the relevant PDF page to an image and inspect that page screenshot before selecting a crop or placeholder.
11. Create one markdown planning document that contains both the outline and the expanded slide-level content plan. Use `references/md-plan-template.md`.
12. For every ordinary content slide, include a layout box table with `slide`, `archetype`, `object_id`, `role`, `x`, `y`, `w`, `h`, and `expected_content` before writing generator code.
13. Prefer figures, paper crops, plots, diagrams, and compact tables over dense prose. Track every planned visual object to an actual PPT object, visible placeholder, or explicit missing-state note.
14. Generate the PPT with editable `pptxgenjs` objects and MathJax-rendered formula images.
15. Include a cover slide, an outline/storyline slide, content slides, and a final conclusion slide unless explicitly exempted.
16. Do not put a bottom conclusion box on the outline slide.
17. Add speaker notes to every slide. Notes should explain how to present the slide; formula notes must include the original LaTeX source; every slide-level image, cropped paper figure, generated plot, figure placeholder, or manually inserted visual must include its source information in the notes.
18. Use the starter generator's helper components for cover, outline, conclusion, cards, tables, citations, formulas, speaker notes, and code. Avoid unconstrained free-coordinate slide construction.
19. Keep ordinary content slides to at most 3 sentences/bullets; allow 4 only for justified data-heavy method/result pages.
20. Keep bottom conclusion boxes above the citation/footer region; do not use the conclusion as a paragraph container.
21. If a required paper figure cannot be cropped or extracted, insert a placeholder frame naming the paper, figure/page, expected content, and `待裁剪 / 需人工插入`; also write the same source and failure reason in the slide speaker notes.
22. Run the AI review iteration loop before delivery. Content and layout must both pass.

## Language Rule

Default deck language is Chinese. This applies to slide titles, visible body text, bottom conclusion sentences, table labels, placeholder text, citation explanations, and speaker notes. Use English only when the user explicitly requests English, when the source text must remain in English for technical accuracy, or when preserving proper nouns, formulas, code, variable names, journal names, and citation metadata.

## MinerU PDF Parsing Rule

For PDF-derived figures, tables, formulas, captions, or diagrams, the agent must use MinerU (`scripts/mineru_extract.py`) as the PDF layout parsing layer. MinerU converts a paper PDF into structured Markdown (`full.md`) and an extracted `images/` folder via its online API. Before choosing crop coordinates or placeholders, run MinerU on the source PDF and read the generated `full.md` to identify candidate pages, figures/tables, captions, and layout regions. If MinerU fails, ask the user whether to retry before using fallback tools such as `pdfplumber`, PyMuPDF, manual page screenshots, or placeholders.

### MinerU Path Configuration

| Component | Path / value |
|---|---|
| MinerU script | `scripts/mineru_extract.py` |
| MinerU API endpoint | `https://mineru.net/api/v4` |
| API Token | Environment variable `MINERU_API_TOKEN`, or `scripts/mineru_config.json`（参考 `mineru_config.example.json`） |
| Default output root | `D:\yychen\MinerU\output` (override with `--output`) |
| Per-PDF output | `<output_root>/<pdf_stem>/full.md` and `<output_root>/<pdf_stem>/images/` |

Do not silently downgrade to a fallback parser. If the user declines retry or the API is unreachable, record `MinerU parse failed` and the approved fallback path in the markdown plan and speaker notes.

## PDF Page Screenshot Rule

For every PDF-derived visual object, the agent must render the candidate PDF page to an image and inspect that screenshot as visual input before deciding the crop boundary or placeholder content. Do not select PDF crop coordinates from text extraction alone.

The markdown plan and slide speaker notes should record the PDF file, page number, figure or panel label, MinerU parse output path or failure status, rendered page screenshot path when available, crop box when available, final crop asset path or placeholder status, and any failure reason.

## Image Source Notes Rule

Every slide with any image-like visual object must include an `Image sources:` section in its speaker notes. This applies to successfully inserted images and to failed crops represented by placeholders.

For each visual object, record:

- object id or visible label,
- source file / paper / URL / notebook / generated asset path,
- paper page and figure/panel number when available,
- MinerU parse output path or `MinerU parse failed` when the source is a PDF,
- rendered PDF page screenshot path when the source is a PDF and a screenshot was available,
- crop asset path or generated output path when available,
- PPT status: `inserted`, `generated`, `placeholder`, `pending crop`, or `omitted`,
- failure reason and required manual action when the object is not inserted.

Do not treat a visible citation footer as a replacement for speaker-note source tracking. The footer is for audience attribution; the speaker notes are for later editing and source recovery.

## Implementation Resources

- `references/style-guide.md`: visual rules, fonts, colors, citation footer, figure layout.
- `references/layout-archetypes.md`: fixed non-overlapping content-slide templates and mandatory layout box tables.
- `references/mineru-pdf-policy.md`: MinerU PDF parsing, script usage, retry-confirmation, and fallback rules.
- `references/reference-folder-mineru-addendum.md`: extra MinerU requirements for PDF-heavy reference-folder decks.
- `references/workflow.md`: common plan -> generate -> verify sequence, with talk plan integration.
- `references/content-writing.md`: slide-level writing, anti-AI phrasing, slide content limits, cover rules, bottom conclusion sentence.
- `references/toolchain.md`: dependency installation and command usage.
- `references/reference-folder-workflow.md`: refs folder, papers, cropped figures, group meeting decks.
- `references/qa-iteration.md`: AI multi-round content and layout review loop.
- `references/md-plan-template.md`: slide-level markdown planning template, with talk plan import sections.
- `references/language-and-source-notes.md`: language defaults and image-source note rules.
- `scripts/pptxgenjs_simple_sci_template.js`: starter generator.
- `scripts/layout_archetypes.js`: reusable layout coordinates and collision audit helpers for generators.
- `scripts/mineru_extract.py`: parse PDF papers into Markdown and extracted images via MinerU online API.
- `scripts/inventory_refs.py`: inventory mixed reference folders.
- `scripts/crop_pdf_figure.py`: crop figures from rendered PDF pages.
- `scripts/verify_pptx.ps1`: open/export PPTX previews with PowerPoint.

## Hard Failure Examples

- A `talk_plan.md` is provided but the slide plan re-derives the
  narrative arc, audience profile, or claim-evidence matrix instead of
  importing them.
- A `talk_plan.md` specifies `essential` materials that are omitted from
  the slide plan without an explicit reason.
- A markdown plan promises a paper figure, spectrum, structure model, or comparison chart but the PPT contains only text.
- A PDF-derived visual is cropped, inserted, or represented by a placeholder without first running MinerU, unless the plan records that the user approved a fallback path.
- A PDF-derived visual is cropped, inserted, or represented by a placeholder without first rendering and visually inspecting the candidate PDF page screenshot, unless the plan records a toolchain blocker.
- MinerU fails, but the agent silently falls back to another parser without asking the user whether to retry.
- A required paper figure is unavailable but the PPT has no visible placeholder frame with target source and figure/page.
- A slide uses an inserted image, cropped paper figure, generated plot, or placeholder but the speaker notes do not include its source and status.
- A figure cannot be cropped and is represented by a placeholder, but the notes omit the original source, page/figure number, MinerU parse status, rendered page screenshot path when available, or failure reason.
- The deck defaults to English even though the user did not explicitly request English.
- A QA checklist says pass without citing exported preview slides or actual PPT objects.
- Cover metadata, outline items, right-side cards, tables, or bottom conclusion text are clipped in preview.
- A normal content slide exceeds 3 sentences/bullets, or a data-heavy slide exceeds 4, without splitting or justification.
- The outline slide contains a bottom conclusion box.
- The deck lacks a final conclusion slide when generating a complete deck.
- Slides lack speaker notes, or formula slides omit the LaTeX source in notes.
- A bottom conclusion box overlaps the citation footer or page number region.
- A generator rewrites the layout with many ad hoc `addText` / `addShape` coordinates instead of using or extending the template helpers.
- A content slide omits the required layout archetype selection and layout box table.
- Any high-level content object overlaps another unrelated high-level object, including semi-transparent callout boxes covering tables, figures, formulas, citations, or page numbers.
- A layout conflict is hidden by transparency or z-order instead of being fixed by moving, resizing, or splitting the slide.

## Required QA Summary

In the final response, report:

- final PPTX path,
- generator script path if created or modified,
- slide count,
- deck language and whether it followed the default Chinese rule or an explicit user override,
- whether PowerPoint opened/exported successfully,
- whether formulas were inserted as MathJax-rendered image assets,
- whether all inserted/placeholder image sources were recorded in speaker notes,
- whether PDF-derived visuals were first parsed with MinerU or had user-approved fallback/blocker notes,
- whether PDF-derived visuals were checked against rendered page screenshots or had documented blockers,
- any unresolved caveat such as formula fallback to raw LaTeX or manual figure crop still pending.

Do not expose scratch preview directories unless the user asks for QA artifacts.

## Handoffs

- For pre-slide narrative design (core argument, audience analysis,
  evidence chain, time budget, material prioritization), use
  `sci-talk-planning`. This skill owns slide-level planning and PPTX
  generation only.
- For VASP calculation figures or data needed in the deck, use
  `vasp-analysis` to extract plot-ready `.dat` files and figures first.
- Keep this skill focused on slide-level planning, layout, generation,
  and QA.
