# AI Review And Iteration Loop

Every generated deck must pass a multi-round AI review loop before delivery. Content and layout are equally important.

## Loop

1. Generate the PPTX from the `.js` generator.
2. Open/export the PPTX with PowerPoint using `scripts/verify_pptx.ps1`.
3. Inspect the exported PNG previews slide by slide.
4. Review content, layout, and technical rendering against the checklist below.
5. Compare the markdown plan against the exported PPT preview: title, conclusion, visual objects, citations, page number, language choice, and conclusion slide must match the plan.
6. If any item fails, write concrete findings with slide numbers in the markdown plan or QA notes.
7. Edit the generator, crop assets, formula assets, or slide plan.
8. Regenerate the PPTX and repeat from step 2.
9. Stop only when the deck passes, or when a blocker is explicitly documented.

Recommended cap: 3 full review loops for ordinary decks. Continue beyond 3 only when remaining issues are small and clearly fixable.

## Content Review

- The slide sequence has a clear logic and does not feel like isolated notes.
- The deck was planned by outline first, then expanded into slide content.
- The outline and expanded content are stored in one markdown planning document.
- The deck has a cover slide with report topic, date, and presenter unless explicitly exempted.
- The deck has a PPT outline/storyline slide immediately after the cover unless explicitly exempted.
- The outline slide has no bottom conclusion box.
- The deck has a final conclusion slide unless explicitly exempted.
- Each slide has one main message.
- Each content slide has a declarative title that reflects the main message.
- Each content slide has one bottom conclusion sentence.
- No ordinary content slide exceeds 4 visual objects or 3 full sentences/bullet sentences.
- A data-heavy method/result slide may use 4 sentences only when the markdown plan records why the density is necessary.
- Claims are traceable to source files, page numbers, figures, or user-provided notes.
- Planned figures, spectra, structure models, tables, and formulas appear in the actual PPT or are explicitly marked as missing in the plan.
- Evidence-bearing slides use figures, plots, cropped paper images, formulas, diagrams, or compact tables when source material supports them.
- Text-only content slides have a specific reason in the markdown plan.
- If a paper figure cannot be cropped/extracted, the actual PPT contains a visible placeholder frame that names the target paper, figure/page, expected content, and `待裁剪 / 需人工插入` status.
- Every slide has speaker notes.
- Formula slides preserve the original LaTeX source in speaker notes.
- Exercise decks include full problem statements before solutions.
- Group meeting decks include source inventory, claim-evidence mapping, and discussion points.
- Language is formal and declarative.
- Deck language is English by default unless the user specified another language.
- No conversational fillers, slogans, exam-cram phrases, assistant language, or empty AI-like managerial phrasing.
- Claims are not stronger than the source evidence.

## Layout Review

- The page communicates the hierarchy at a glance: title, main claim, evidence, conclusion.
- No upper-right topic text.
- Title is 26-30 pt and visually dominant.
- Cover title is 34-40 pt when a cover slide is used.
- Body text is at least 20 pt except code, comments, references, and page markers.
- Card labels are 22-24 pt and bold.
- Text does not overlap, clip, or touch borders.
- No object extends beyond the safe layout region in `style-guide.md`.
- Cover metadata is fully visible.
- Outline items do not run off the right edge.
- Outline slide does not contain a bottom conclusion box.
- Right-side cards and comparison tables are fully inside the slide.
- Related objects align cleanly; unrelated objects have enough spacing.
- Figure cards preserve aspect ratio and keep important details readable.
- Cropped paper figures are tight enough to remove article clutter while preserving panel labels, legends, axes, and scale bars.
- Formula cards use consistent visual size across similar roles.
- Citation footer does not compete with main content.
- Bottom conclusion sentence is readable, separated from citations, and not confused with the page footer.
- Bottom conclusion box stays above the citation/footer area and does not overlap the lower-left citation or bottom-right page number.
- If one slide uses multiple papers, each cited text block, figure card, or comparison column has its own nearby citation.
- Page number is bottom-right only.
- White background and blue/orange card system remain consistent.

## Technical Rendering Review

- PPTX opens in PowerPoint.
- Exported preview contains the expected number of slides.
- `ppt/media/` has no empty media files.
- Media count is consistent with the plan's visual-object traceability table. A low media count is acceptable only if visuals are generated as editable tables/shapes and documented as such.
- Formulas are rendered as image assets, not raw LaTeX text, unless fallback is reported.
- Paper figures are cropped images rather than full-page screenshots when possible.
- Image assets are not stretched.
- Tables are readable and not generated with fragile XML if PowerPoint rejects them.
- Speaker notes exist for every slide.
- Formula speaker notes include the original LaTeX source.

## DeepSeek Failure Regression Checks

Use these checks when a deck was generated by a weaker model or when the output feels AI-generated despite passing a checklist:

| Failure pattern | Required review action |
|---|---|
| Cover metadata cut off at bottom | record `Slide 1 metadata clipped`; move metadata above safe boundary or shrink title/subtitle |
| Outline page text cut off on the right | record `Slide 2 outline overflow`; rebuild as stacked cards with short labels |
| Right-side content cards off-screen | record exact slide, e.g. `Slide 4 right card overflow`; reduce content or split slide |
| Planned paper figure absent from PPT | record exact slide, e.g. `Slide 5 planned ADF-STEM figure not inserted`; crop/insert image or mark as omitted |
| Markdown QA says pass without preview evidence | mark QA as failed; replace checkbox-only QA with evidence table |
| Table extends beyond slide | rebuild with fixed table helper or split table |
| Bottom conclusion overlaps citation or page bottom | move conclusion to safe region and keep citation separate |
| Outline slide has a bottom conclusion box | remove the conclusion box; keep only outline cards/items |
| Complete deck lacks a conclusion slide | add a final conclusion slide with synthesized takeaways |
| Slide lacks speaker notes | add notes explaining how to present that slide |
| Rendered formula lacks LaTeX source in notes | add a `LaTeX source:` block to speaker notes |
| Evidence-bearing slide is text-only despite available figures/tables | add a figure/table/formula/diagram or record a reason in the plan |
| Slide has more than 3 bullets plus a table/card group | record `Slide N content too dense`; split the slide or convert bullets into a compact table |
| Missing paper image because crop tool is unavailable | insert a placeholder frame naming the paper and figure/page; mark visual status as `pending crop` |
| Slide title repeats a topic but not a conclusion | rewrite title as a declarative claim |

## QA Notes Template

```markdown
## QA Iteration N

- Preview path:
- Content findings with slide numbers:
- Layout findings with slide numbers:
- Technical findings with slide numbers:
- Plan-vs-PPT traceability findings:
- Fixes applied:
- Result: pass / repeat / blocked
```
