# Content Writing Workflow

Use this file when creating the markdown plan and slide text. The goal is to make the deck read like a prepared research/classroom report rather than AI-generated notes.

## Two-Stage Planning

1. Create one markdown planning document before generating PPTX.
2. Write the deck outline in that same markdown document before expanding slide content.
3. Review the outline for storyline, source coverage, and slide count.
4. Expand each outline item into slide-level content only after the outline is coherent.
5. Rewrite slide text with a scientific-humanization pass before generating PPTX.
6. Keep the expanded content constrained by the per-slide limits below.

Do not split the outline and expanded slide content into two separate planning documents unless the user explicitly requests separate files. A reviewer should be able to read one markdown plan and see both the first-pass outline and the final expanded page content.

The outline should decide what each slide proves. The expansion should only add the evidence, formula, figure, table, or code needed to support that local message.

## Language Default

Use English as the default language for slide text, titles, labels, conclusion sentences, and speaker notes unless the user specifies Chinese or another target language. Preserve source-specific proper nouns, variable names, formulas, citations, and technical terms. If the user requests Chinese, use formal Chinese declarative phrasing and avoid casual classroom filler.

## Evidence-Tracked Expansion

The expanded slide plan must make every planned visual object traceable to an actual PPT object.

For each figure, table, formula, code box, or paper crop, record:

- source file, paper page, figure number, notebook output, or generated asset path,
- intended slide number and object role,
- actual PPT status: `inserted`, `generated`, `text-only fallback`, `pending crop`, or `omitted`,
- failure reason when not inserted.

Do not mark the writing pass as complete if the plan promises a figure, model, or spectrum but the generated PPT only contains text. A missing paper figure should be written as `pending crop` or `omitted`, not hidden behind a checked QA item.

## Outline Requirements

Every deck should include:

- a cover slide,
- a concise section outline or storyline slide immediately after the cover,
- a final conclusion slide that summarizes the main technical takeaways,
- slide titles that state the main message, not just the topic,
- one sentence that explains the role of each slide in the deck,
- planned figures/tables/formulas for each slide.

The PPT outline slide should summarize the planned structure, not repeat all slide titles verbatim. Use 3-6 items, each item naming a section and its local purpose. Do not add a bottom conclusion sentence to the outline slide. Only omit the outline slide when the task is a single inserted page or the user explicitly says not to include it.

## Slide Content Limits

For ordinary content slides:

- use at most 4 visual objects, including figures, tables, formulas, and code boxes,
- use at most 3 full sentences or bullet sentences by default,
- use at most 4 full sentences only for data-heavy method/result pages,
- use one clear bottom conclusion sentence,
- prefer at least one visual object when source material supports it,
- prefer compact tables for comparisons, parameters, evidence maps, and method/result summaries,
- keep each slide focused on one claim or one local teaching goal,
- split the slide if the content needs smaller than 20 pt body text.

Figures inside one multi-panel paper figure count as one visual object if they are inserted as one cropped image and discussed as one evidence unit.

If the slide needs more than 3 bullets, convert details into a table, split the slide, or move lower-priority details to speaker notes. A slide should not contain both a long bullet list and multiple side cards. For literature or group-meeting decks, avoid text-only slides unless the slide is a transition, conclusion, or source inventory.

## Title Rules

Use declarative titles that communicate the main point.

Prefer:

- `Raman 位移可分离电荷转移与应变响应`
- `BLG 限域稳定 Na 三层构型`
- `误差随迭代步数呈幂律放大`

Avoid:

- `背景介绍`
- `实验结果`
- `一些问题`
- `总结`

Exercise slides may use `习题 n.m：主题` as the title, but the topic after the colon should still be specific.

## Bottom Conclusion Sentence

Every content slide should include a bottom conclusion sentence in a pale orange callout or equivalent conclusion region.

The sentence should:

- state the local takeaway,
- avoid motivational or conversational phrasing,
- avoid overclaiming beyond the evidence,
- connect to the next slide when useful.

The bottom conclusion may not be empty, `—`, `TBD`, or a repeated page title. If a slide is a cover, outline, conclusion, or reference list, mark the conclusion field as `cover slide`, `outline slide`, `conclusion slide`, or `reference slide` instead of pretending it is a content conclusion.

Keep the conclusion sentence short enough to fit in one visual line when possible, usually no more than about 14 English words, 32 Chinese characters, or one concise bilingual sentence. If the conclusion needs two lines, it should still remain separate from citations and the page number.

Examples:

- `该结果支持电荷转移主导 Raman 响应，但不能单独证明插层结构稳定。`
- `二分法的误差上界由区间长度控制，迭代步数可由精度要求直接估计。`
- `BLG 的低维限域改变了 Na 的稳定构型，因此不能直接套用 bulk graphite 的判断。`

## Anti-AI Writing Pass

Before generating PPTX, rewrite slide text using these checks:

- remove assistant language such as `下面介绍`, `我们来看`, `可以发现`, `值得注意的是` unless the user explicitly wants a speaking script,
- remove empty managerial words such as `全面`, `系统性`, `深度`, `闭环`, `赋能`, `底座`, `生态`,
- replace vague transitions with concrete relations: `因此`, `对应`, `限制`, `支持`, `不能说明`,
- preserve facts, formulas, numbers, citations, and evidence boundaries,
- use the order `problem -> method/evidence -> result -> limitation/conclusion`,
- downgrade claims when evidence is incomplete: use `提示`, `支持`, `可能`, `仍需验证` instead of `证明`, `揭示`, `显著`.

For classroom/exercise decks, concise declarative language is preferred over casual explanation. For group meeting decks, include limitations and discussion questions only when they follow from the evidence.

## Failed-Deck Anti-Patterns

Treat these as hard failures during content review:

- the markdown checklist is fully checked but does not cite preview slides or actual PPT objects,
- a slide promises `ADF-STEM image`, `Raman spectrum`, `DOS comparison`, or `structure model` but no image is inserted,
- a slide has more than 3 bullets plus additional tables/cards,
- the outline page repeats long paper titles and author names as one-line items that run off the slide,
- content slides contain large text boxes plus side cards without an evidence figure,
- paper-specific claims lack a nearby citation or a slide-level citation footer,
- title, conclusion, and body repeat the same sentence rather than forming a claim-evidence-conclusion chain.

## Cover Slide

Every new deck should include a cover slide unless the user explicitly asks for a single-page slide or an insertion into an existing deck.

Required fields:

- report topic,
- date,
- presenter.

Cover style:

- white background,
- large black title, 34-40 pt,
- thin blue divider,
- small orange accent block or line,
- metadata in 20-22 pt near the lower-left,
- no decorative icons unless provided by the user,
- no upper-right topic text,
- no page number on the cover unless the target deck already uses one.

If the user does not provide date or presenter, use placeholders such as `汇报人：<姓名>` and `时间：<日期>` rather than inventing personal information.

## Figure Placeholder Policy

When the agent cannot crop or extract a paper figure, it should insert a visible placeholder frame instead of filling the slide with extra text.

The placeholder must state:

- target paper or source file,
- target figure number or page,
- what the figure should show,
- crop status such as `待裁剪` or `需人工插入`.

Example:

`待插入：Lin et al., ACS Nano 2025, Fig. 1；内容：ADF-STEM 图与 fcc(111) Na 三层模型。`

The markdown plan should mark this visual object as `pending crop`, not `inserted`. The PPT can still be useful because it reserves the correct visual slot and tells the presenter what to add.

## Speaker Notes

Every generated slide must include speaker notes. The notes should explain how the presenter should talk through the slide, not repeat the visible text verbatim.

Speaker notes should include:

- the slide's role in the story,
- the intended speaking order for the visible objects,
- source caveats or citation reminders when relevant,
- image placeholder instructions when a figure crop is pending,
- original LaTeX source for every formula rendered as an image on that slide.

For formula-heavy slides, append a `LaTeX source:` section in the notes and list each formula exactly as it appears in the generator. This makes later manual editing possible even though the slide itself uses rendered formula images.
