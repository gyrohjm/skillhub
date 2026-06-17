# Language And Image-Source Notes Policy

Use this policy when creating or revising any deck with `simple-sci-ppt`.

## Language Default

Default deck language is Chinese.

This applies to:

- slide titles,
- visible body text,
- table labels,
- figure placeholders,
- bottom conclusion sentences,
- speaker notes,
- QA notes and plan documents.

Use English only when the user explicitly requests English or another target language. Preserve proper nouns, journal names, code, file paths, variable names, formulas, citation metadata, and established technical terms when translation would reduce precision.

## Speaker Notes For Visual Sources

Every slide with an image-like visual object must include an `Image sources:` section in speaker notes.

Image-like visual objects include:

- inserted image files,
- cropped paper figures,
- generated plots,
- schematic assets,
- rendered full-page fallbacks,
- screenshots,
- visible placeholders for missing figures.

The rule applies whether the image was successfully inserted or not. A placeholder still needs a source note.

For each visual object, write one note entry:

```text
Image sources:
- <object_id>: source=<paper/file/notebook/url>; page=<page or n/a>; figure=<figure/panel or n/a>; asset=<crop/generated path or n/a>; status=inserted/generated/placeholder/pending crop/omitted; note=<crop details, failure reason, or manual action>.
```

## Placeholder Requirement

If a figure cannot be cropped or extracted, the PPT must contain a visible placeholder in the planned figure slot. The placeholder must state:

```text
待插入：<paper or source file>，<figure/page>
内容：<expected visual content>
状态：待裁剪 / 需人工插入
```

The same source, figure/page, expected content, status, and failure reason must also appear in the slide speaker notes under `Image sources:`.

## Hard Failures

- A deck defaults to English without an explicit user request.
- A slide has an inserted image, crop, generated plot, screenshot, or placeholder but no `Image sources:` section in notes.
- A placeholder exists on the slide but its original source and failure reason are missing from notes.
- A visual citation footer is present, but speaker notes omit source details needed for later editing.
