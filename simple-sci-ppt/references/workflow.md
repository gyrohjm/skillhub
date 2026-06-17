# Workflow

Use this file for the common deck-generation sequence. Load the specialized references only when the task needs them.

## Source Priority

1. User-specified PPT/PDF/MD/Jupyter files.
2. User-provided reference decks or accepted prior decks as style anchors.
3. Reference folders containing papers, figures, notes, BibTeX/RIS files, notebooks, and code outputs.
4. Lecture notes, papers, reports, experiment records, notebooks, figures, and code outputs.
5. Existing generated markdown plans, notebooks, and figures.

If the user identifies an authoritative source, extract statements, formulas, and figures from that source first.

## Reference Routing

- Visual style, fonts, cards, citations, and figure placement: read `style-guide.md`.
- Tool installation and command usage: read `toolchain.md`.
- Outline-first slide writing, anti-AI phrasing, content density, cover slide, and conclusion sentences: read `content-writing.md`.
- Reference folder / group meeting decks: read `reference-folder-workflow.md`.
- Multi-round content and layout review: read `qa-iteration.md`.
- Markdown plan structure: use `md-plan-template.md`.

## Common Sequence

1. Decide deck mode and slide scope.
2. Inventory and extract source facts.
3. Select deck language. Use English by default unless the user specifies Chinese or another language.
4. Create one markdown planning document before writing slide content.
5. Write the deck outline in that same markdown document.
6. Review the outline for storyline, source coverage, slide count, and the final conclusion slide.
7. Expand the outline into a slide-level content plan in the same markdown document.
8. Prefer figures, paper crops, generated plots, diagrams, and compact tables over prose-heavy slide bodies.
9. Apply the anti-AI writing pass in `content-writing.md`.
10. Record the generation route, tools, figure crops, formula assets, speaker notes, LaTeX source, and citation style in the plan.
11. Generate with `pptxgenjs`; keep the generator script beside the PPTX when practical.
12. Include a cover slide, a PPT outline/storyline slide, content slides, and a final conclusion slide unless explicitly exempted.
13. Do not place a bottom conclusion box on the outline slide.
14. Use the starter template's helper components for cover, outline, conclusion, formula, code, table, citation, speaker notes, and cards. Do not scatter unconstrained `addText` / `addShape` coordinates across a new generator.
15. Render LaTeX formulas as image assets before insertion and preserve their source strings in speaker notes.
16. Add speaker notes to every slide explaining how to present that slide.
17. Crop paper figures from PDF pages when relevant.
18. If a required paper figure cannot be cropped or extracted, insert a visible placeholder frame in the PPT and mark the visual object as `pending crop` in the markdown plan.
19. Open/export the PPTX with PowerPoint.
20. Compare the exported preview against the markdown plan's visual traceability table, sentence-count limits, outline-slide rule, conclusion-box position, conclusion slide, citations, and page numbers.
21. Run the AI review loop for both content and layout.
22. Iterate until the deck passes or a blocker is documented.

## Generation Route

Default route:

```text
single markdown plan with outline and expanded content -> anti-AI writing pass -> pptxgenjs generator -> cover + outline slide + content slides + conclusion slide -> MathJax/formula image assets + speaker notes with LaTeX source -> PPTX -> PowerPoint preview -> AI review iterations
```

Do not default to artifact-tool, Python PPTX mutation, direct OOXML edits, or Markdown-only compilation for this skill.

Generator discipline:

- Start from `scripts/pptxgenjs_simple_sci_template.js` for new decks.
- Reuse helper functions such as `coverSlide`, `outlineSlide`, `conclusionSlide`, `conclusionBox`, formula/card helpers, speaker-note helpers, and the table helper.
- Add new layout helpers when needed instead of manually placing many free-coordinate objects.
- If a planned visual object cannot be inserted, use a placeholder frame or update the markdown plan before claiming QA pass.
- Keep ordinary content slides under 3 sentences/bullets by default; split dense slides before shrinking fonts.
- Avoid text-only content slides when source figures, generated plots, formulas, or tables can carry the message.
- Every slide must call `addSlideNotes` or `slide.addNotes(...)`; formula slides must include the LaTeX source in notes.
- After preview export, record plan-vs-PPT mismatches with exact slide numbers.

## Naming

Do not overwrite unless explicitly requested. Use filenames that describe scope and version, for example:

- `课题组汇报_方法与结果_新版.pptx`
- `论文阅读汇报_机制与证据链.pptx`
- `课堂复习PPT_知识点扩充版.pptx`
- `DFT部分总结_单页.pptx`

## Delivery Summary

Report the final PPTX path, generator script path, slide count, PowerPoint export result, formula rendering status, citation/crop caveats, and remaining issues if any.
