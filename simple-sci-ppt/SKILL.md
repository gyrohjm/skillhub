---
name: simple-sci-ppt
description: Create, revise, and verify formal academic PowerPoint decks in a classroom card layout with formula cards, image/figure cards, comparison tables, code cards, orange section tabs, and blue/orange semantic containers for research reports, classroom lectures, course reviews, exercise sessions, thesis/group-meeting presentations, and single-topic scientific slides. Use when Codex is asked to use simple-sci-ppt, simple_sci_ppt, or simple_sci_ppt_gen, or when turning source materials such as PDFs, PPTX files, markdown notes, papers, notebooks, figures, reference folders with papers/images, or chapter folders into a planned PPTX with markdown content planning, MathJax-rendered formula images, editable `pptxgenjs` slide objects, formal declarative language, per-slide speaker notes, and PowerPoint validation.
---

# simple-sci-ppt

## Core Workflow

1. Identify the deck mode: research report, reference-folder group meeting report, classroom lecture/review, exercise session, targeted edit, or single-topic slide.
2. Read `references/style-guide.md` before visual work.
3. Read `references/workflow.md` for the common generation sequence.
4. Read `references/content-writing.md` before writing slide text.
5. Default to English deck text unless the user specifies Chinese or another language.
6. Create one markdown planning document that contains both the outline and the expanded slide-level content plan. Use `references/md-plan-template.md`.
7. Prefer figures, paper crops, plots, diagrams, and compact tables over dense prose. Track every planned visual object to an actual PPT object, visible placeholder, or explicit missing-state note.
8. Generate the PPT with editable `pptxgenjs` objects and MathJax-rendered formula images.
9. Include a cover slide, an outline/storyline slide, content slides, and a final conclusion slide unless explicitly exempted.
10. Do not put a bottom conclusion box on the outline slide.
11. Add speaker notes to every slide. Notes should explain how to present the slide; formula notes must include the original LaTeX source.
12. Use the starter generator's helper components for cover, outline, conclusion, cards, tables, citations, formulas, speaker notes, and code. Avoid unconstrained free-coordinate slide construction.
13. Keep ordinary content slides to at most 3 sentences/bullets; allow 4 only for justified data-heavy method/result pages.
14. Keep bottom conclusion boxes above the citation/footer region; do not use the conclusion as a paragraph container.
15. If a required paper figure cannot be cropped or extracted, insert a placeholder frame naming the paper, figure/page, expected content, and `待裁剪 / 需人工插入`.
16. Run the AI review iteration loop before delivery. Content and layout must both pass.

## Implementation Resources

- `references/style-guide.md`: visual rules, fonts, colors, citation footer, figure layout.
- `references/workflow.md`: common plan -> generate -> verify sequence.
- `references/content-writing.md`: outline-first writing, anti-AI phrasing, slide content limits, cover rules, bottom conclusion sentence.
- `references/toolchain.md`: dependency installation and command usage.
- `references/reference-folder-workflow.md`: refs folder, papers, cropped figures, group meeting decks.
- `references/qa-iteration.md`: AI multi-round content and layout review loop.
- `references/md-plan-template.md`: markdown planning template.
- `scripts/pptxgenjs_simple_sci_template.js`: starter generator.
- `scripts/inventory_refs.py`: inventory mixed reference folders.
- `scripts/crop_pdf_figure.py`: crop figures from rendered PDF pages.
- `scripts/verify_pptx.ps1`: open/export PPTX previews with PowerPoint.

## Hard Failure Examples

- A markdown plan promises a paper figure, spectrum, structure model, or comparison chart but the PPT contains only text.
- A required paper figure is unavailable but the PPT has no visible placeholder frame with target source and figure/page.
- A QA checklist says pass without citing exported preview slides or actual PPT objects.
- Cover metadata, outline items, right-side cards, tables, or bottom conclusion text are clipped in preview.
- A normal content slide exceeds 3 sentences/bullets, or a data-heavy slide exceeds 4, without splitting or justification.
- The outline slide contains a bottom conclusion box.
- The deck lacks a final conclusion slide when generating a complete deck.
- Slides lack speaker notes, or formula slides omit the LaTeX source in notes.
- A bottom conclusion box overlaps the citation footer or page number region.
- A generator rewrites the layout with many ad hoc `addText` / `addShape` coordinates instead of using or extending the template helpers.

## Required QA Summary

In the final response, report:

- final PPTX path,
- generator script path if created or modified,
- slide count,
- whether PowerPoint opened/exported successfully,
- whether formulas were inserted as MathJax-rendered image assets,
- any unresolved caveat such as formula fallback to raw LaTeX.

Do not expose scratch preview directories unless the user asks for QA artifacts.

