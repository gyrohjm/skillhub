# Workflow

Use this file for the common deck-generation sequence. Load the specialized references only when the task needs them.

## Source Priority

0. `talk_plan.md` from `sci-talk-planning` (if available).
1. User-specified PPT/PDF/MD/Jupyter files.
2. User-provided reference decks or accepted prior decks as style anchors.
3. Reference folders containing papers, figures, notes, BibTeX/RIS files, notebooks, and code outputs.
4. Lecture notes, papers, reports, experiment records, notebooks, figures, and code outputs.
5. Existing generated markdown plans, notebooks, and figures.

If a `talk_plan.md` is available, it takes priority for narrative-level decisions (deck mode, audience, narrative arc, claim-evidence matrix, material priorities). Do not re-derive these. If the user identifies an authoritative source, extract statements, formulas, and figures from that source first.

## Reference Routing

- Visual style, fonts, cards, citations, and figure placement: read `style-guide.md`.
- Fixed content-slide templates and object-collision rules: read `layout-archetypes.md`.
- Tool installation and command usage: read `toolchain.md`.
- Outline-first slide writing, anti-AI phrasing, content density, cover slide, conclusion sentences, language defaults, and speaker-note source tracking: read `content-writing.md`.
- Reference folder / group meeting decks: read `reference-folder-workflow.md`.
- Multi-round content and layout review: read `qa-iteration.md`.
- Markdown plan structure: use `md-plan-template.md`.

## Common Sequence

0. If a `talk_plan.md` from `sci-talk-planning` is available, read it first.
   Use its narrative arc, claim-evidence matrix, material priorities, and
   audience profile as input for the slide plan. If no talk plan exists,
   ask the user for minimum context (core argument, audience, time).
1. Confirm deck mode, `visual_mode`, `pacing_mode`, and slide scope. If a
   talk plan exists, use its handoff fields. Otherwise use
   `formal_research` and `standard` for research material unless the user
   explicitly requests classroom or `visual_micro` behavior.
2. Inventory and extract source facts. If a talk plan exists, import its
   material priority list, reading status, and anchor coverage
   requirements. Read every `essential` source in full before assigning a
   claim; if the user requests all papers, read every parseable source.
3. Select deck language. If a talk plan exists, use its `language` field.
   Otherwise use Chinese by default unless the user explicitly requests
   another language.
4. Create one markdown planning document before writing slide content.
5. Add a source-comprehension record for each anchor paper: research
   question, method, direct evidence, mechanism, limitation, and selected
   figure/page. Map every anchor source across at least two narrative
   beats before writing slide text.
6. Write the slide outline in that same markdown document. If a talk plan
   exists, map its narrative arc sections to specific slides.
7. Review the slide outline for source coverage, slide count, and the
   final conclusion slide.
8. Expand the outline into a slide-level content plan in the same markdown document.
9. For every ordinary content slide, select one layout archetype from `layout-archetypes.md` before writing generator code.
10. For every ordinary content slide, write a layout box table with `slide`, `archetype`, `object_id`, `role`, `x`, `y`, `w`, `h`, and `expected_content`.
11. Prefer figures, paper crops, generated plots, diagrams, and compact tables over prose-heavy slide bodies.
12. Apply the anti-AI writing pass in `content-writing.md`.
13. Record the generation route, tools, figure crops, formula assets,
   structured speaker notes, LaTeX source, fixed lower-left citation
   footer, chosen layout archetypes, layout box tables, and per-slide
   image-source notes in the plan.
14. Generate with `pptxgenjs`; keep the generator script beside the PPTX when practical.
15. Include a cover slide, a PPT outline/storyline slide, content slides, and a final conclusion slide unless explicitly exempted.
16. Do not place a bottom conclusion box on the outline slide.
17. Use the starter template's helper components for cover, outline, conclusion, formula, code, table, fixed `addCitationFooter`, structured speaker notes, and cards. Do not scatter unconstrained `addText` / `addShape` coordinates across a new generator.
18. Use `scripts/layout_archetypes.js` or equivalent copied constants to reuse approved coordinates and run a collision audit where practical.
19. Render LaTeX formulas as image assets before insertion and preserve their source strings in speaker notes.
20. Add structured speaker notes to every slide. If the slide contains any image-like visual object, add an `Image sources:` section in the notes.
21. For every inserted image, cropped paper figure, generated plot, schematic asset, full-page fallback, or placeholder, record the source file/paper, page, figure/panel number, asset path, PPT status, and failure reason if any in the slide notes.
22. Crop paper figures from PDF pages when relevant, and never overlay the crop with labels, callouts, or citation text.
23. If a required paper figure cannot be cropped or extracted, insert a visible placeholder frame in the PPT, mark the visual object as `pending crop` in the markdown plan, and still write the original source/page/figure/failure reason in the slide notes.
24. Open/export the PPTX with PowerPoint.
25. Compare the exported preview against the markdown plan's visual traceability table, anchor coverage map, layout box table, sentence-count limits, outline-slide rule, conclusion-box position, conclusion slide, lower-left citation policy, page numbers, and speaker-note image-source entries.
26. Run the AI review loop for both content and layout.
27. Iterate until the deck passes or a blocker is documented.

## Generation Route

Default route:

```text
talk_plan.md (if available) -> slide markdown plan with imported sections 1-3 -> slide outline (mapped from talk plan sections) -> expanded content -> layout archetype selection + layout box table -> visual source traceability table -> anti-AI writing pass -> pptxgenjs generator -> cover + outline slide + content slides + conclusion slide -> MathJax/formula image assets + speaker notes with LaTeX source and Image sources -> PPTX -> PowerPoint preview -> AI review iterations
```

Do not default to artifact-tool, Python PPTX mutation, direct OOXML edits, or Markdown-only compilation for this skill.

Generator discipline:

- Start from `scripts/pptxgenjs_simple_sci_template.js` for new decks.
- Reuse helper functions such as `coverSlide`, `outlineSlide`, `conclusionSlide`, `conclusionBox`, formula/card helpers, speaker-note helpers, and the table helper.
- Add new layout helpers when needed instead of manually placing many free-coordinate objects.
- Use a declared archetype for each ordinary content slide unless a custom layout is explicitly justified in the markdown plan.
- Do not fix object collisions by transparency, z-order, or drawing a semi-transparent card over another object.
- If a planned visual object cannot be inserted, use a placeholder frame or update the markdown plan before claiming QA pass.
- A placeholder does not remove the source-tracking requirement: write the failed image source, page/figure, and reason in speaker notes.
- Keep ordinary content slides under 3 sentences/bullets by default; split dense slides before shrinking fonts.
- Avoid text-only content slides when source figures, generated plots, formulas, or tables can carry the message.
- Every slide must call `addStructuredNotes`, `addSlideNotes`, or `slide.addNotes(...)`; notes must include page role, speaking order, evidence/mechanism, limitation, and transition. Formula slides must include the LaTeX source in notes.
- Every slide containing an image, crop, generated plot, schematic, or placeholder must include `Image sources:` in notes.
- Use one `addCitationFooter` call per research slide. Do not insert citations in a header, title, figure card, table cell, or figure overlay.
- After preview export, record plan-vs-PPT mismatches with exact slide numbers.

## Naming

Do not overwrite unless explicitly requested. Use filenames that describe scope and version, for example:

- `课题组汇报_方法与结果_新版.pptx`
- `论文阅读汇报_机制与证据链.pptx`
- `课堂复习PPT_知识点扩充版.pptx`
- `DFT部分总结_单页.pptx`

## Delivery Summary

Report the final PPTX path, generator script path, slide count, deck language, PowerPoint export result, formula rendering status, image-source-notes status, citation/crop caveats, and remaining issues if any.
