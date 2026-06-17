---
name: simple-sci-ppt
description: Create, revise, and verify formal academic PowerPoint decks in a classroom card layout with formula cards, image/figure cards, comparison tables, code cards, orange section tabs, and blue/orange semantic containers for research reports, classroom lectures, course reviews, exercise sessions, thesis/group-meeting presentations, and single-topic scientific slides. Use when Codex is asked to use simple-sci-ppt, simple_sci_ppt, or simple_sci_ppt_gen, or when turning source materials such as PDFs, PPTX files, markdown notes, papers, notebooks, figures, reference folders with papers/images, or chapter folders into a planned PPTX with markdown content planning, MathJax-rendered formula images, editable `pptxgenjs` slide objects, formal declarative language, per-slide speaker notes, and PowerPoint validation.
---

# simple-sci-ppt

## Core Workflow

1. Identify the deck mode: research report, reference-folder group meeting report, classroom lecture/review, exercise session, targeted edit, or single-topic slide.
2. Read `references/style-guide.md` before visual work.
3. Read `references/layout-archetypes.md` before placing ordinary content-slide objects. Pick one archetype per content slide unless the user explicitly asks for a custom layout.
4. Read `references/workflow.md` for the common generation sequence.
5. Read `references/content-writing.md` before writing slide text.
6. Default to Chinese deck text unless the user explicitly requests English or another target language.
7. Create one markdown planning document that contains both the outline and the expanded slide-level content plan. Use `references/md-plan-template.md`.
8. For every ordinary content slide, include a layout box table with `slide`, `archetype`, `object_id`, `role`, `x`, `y`, `w`, `h`, and `expected_content` before writing generator code.
9. Prefer figures, paper crops, plots, diagrams, and compact tables over dense prose. Track every planned visual object to an actual PPT object, visible placeholder, or explicit missing-state note.
10. Generate the PPT with editable `pptxgenjs` objects and MathJax-rendered formula images.
11. Include a cover slide, an outline/storyline slide, content slides, and a final conclusion slide unless explicitly exempted.
12. Do not put a bottom conclusion box on the outline slide.
13. Add speaker notes to every slide. Notes should explain how to present the slide; formula notes must include the original LaTeX source; every slide-level image, cropped paper figure, generated plot, figure placeholder, or manually inserted visual must include its source information in the notes.
14. Use the starter generator's helper components for cover, outline, conclusion, cards, tables, citations, formulas, speaker notes, and code. Avoid unconstrained free-coordinate slide construction.
15. Keep ordinary content slides to at most 3 sentences/bullets; allow 4 only for justified data-heavy method/result pages.
16. Keep bottom conclusion boxes above the citation/footer region; do not use the conclusion as a paragraph container.
17. If a required paper figure cannot be cropped or extracted, insert a placeholder frame naming the paper, figure/page, expected content, and `待裁剪 / 需人工插入`; also write the same source and failure reason in the slide speaker notes.
18. Run the AI review iteration loop before delivery. Content and layout must both pass.

## Language Rule

Default deck language is Chinese. This applies to slide titles, visible body text, bottom conclusion sentences, table labels, placeholder text, citation explanations, and speaker notes. Use English only when the user explicitly requests English, when the source text must remain in English for technical accuracy, or when preserving proper nouns, formulas, code, variable names, journal names, and citation metadata.

## Image Source Notes Rule

Every slide with any image-like visual object must include an `Image sources:` section in its speaker notes. This applies to successfully inserted images and to failed crops represented by placeholders.

For each visual object, record:

- object id or visible label,
- source file / paper / URL / notebook / generated asset path,
- paper page and figure/panel number when available,
- crop asset path or generated output path when available,
- PPT status: `inserted`, `generated`, `placeholder`, `pending crop`, or `omitted`,
- failure reason and required manual action when the object is not inserted.

Do not treat a visible citation footer as a replacement for speaker-note source tracking. The footer is for audience attribution; the speaker notes are for later editing and source recovery.

## Implementation Resources

- `references/style-guide.md`: visual rules, fonts, colors, citation footer, figure layout.
- `references/layout-archetypes.md`: fixed non-overlapping content-slide templates and mandatory layout box tables.
- `references/workflow.md`: common plan -> generate -> verify sequence.
- `references/content-writing.md`: outline-first writing, anti-AI phrasing, slide content limits, cover rules, bottom conclusion sentence.
- `references/toolchain.md`: dependency installation and command usage.
- `references/reference-folder-workflow.md`: refs folder, papers, cropped figures, group meeting decks.
- `references/qa-iteration.md`: AI multi-round content and layout review loop.
- `references/md-plan-template.md`: markdown planning template.
- `scripts/pptxgenjs_simple_sci_template.js`: starter generator.
- `scripts/layout_archetypes.js`: reusable layout coordinates and collision audit helpers for generators.
- `scripts/inventory_refs.py`: inventory mixed reference folders.
- `scripts/crop_pdf_figure.py`: crop figures from rendered PDF pages.
- `scripts/verify_pptx.ps1`: open/export PPTX previews with PowerPoint.

## Hard Failure Examples

- A markdown plan promises a paper figure, spectrum, structure model, or comparison chart but the PPT contains only text.
- A required paper figure is unavailable but the PPT has no visible placeholder frame with target source and figure/page.
- A slide uses an inserted image, cropped paper figure, generated plot, or placeholder but the speaker notes do not include its source and status.
- A figure cannot be cropped and is represented by a placeholder, but the notes omit the original source, page/figure number, or failure reason.
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
- any unresolved caveat such as formula fallback to raw LaTeX or manual figure crop still pending.

Do not expose scratch preview directories unless the user asks for QA artifacts.
