# Reference-Folder OpenDataLoader Addendum

This addendum strengthens `reference-folder-workflow.md` for PDF-heavy decks.

## Rule

When a reference folder contains PDFs that may provide figures, panels, captions, tables, equations, or diagrams, the agent must use the OpenDataLoader-first policy before crop planning.

## Required Steps

1. Inventory the reference folder.
2. Identify PDFs that may provide visual evidence.
3. Check whether OpenDataLoader is available.
4. If OpenDataLoader is available, parse each relevant PDF and save a parse artifact under the deck work directory.
5. If OpenDataLoader is not available, ask the user whether to install or configure it before using fallback tools.
6. Render each candidate PDF page to a screenshot.
7. Inspect the screenshot visually before crop selection.
8. Crop the selected visual or insert a placeholder.
9. Record source traceability in the markdown plan and speaker notes.

## Traceability Fields

For every PDF-derived visual, record:

| field | meaning |
|---|---|
| `object_id` | PPT object id or visible label |
| `source_pdf` | source PDF path or paper id |
| `page` | PDF page number |
| `figure/panel/table` | figure, panel, table, equation, or diagram id |
| `opendataloader_artifact` | parse artifact path or `OpenDataLoader unavailable` |
| `rendered_page_screenshot` | rendered candidate page screenshot path |
| `crop_box` | crop box when available |
| `final_asset` | final cropped/generated asset path when available |
| `status` | `inserted`, `placeholder`, `pending crop`, `fallback`, or `omitted` |
| `note` | failure reason or remaining manual action |

## Missing OpenDataLoader

If OpenDataLoader is unavailable, use this confirmation before fallback:

```text
当前环境没有检测到 OpenDataLoader。是否需要我先安装/配置 OpenDataLoader 以解析 PDF 版面？如果不安装，我会退回到 pdfplumber/PyMuPDF 渲染页面截图 + 手动裁剪/占位流程，并在备注中记录解析限制。
```

Do not proceed with fallback parsing unless the user approves fallback or the environment clearly cannot install additional packages.

## Placeholder Notes

If a figure cannot be cropped, the visible placeholder must include:

```text
待插入：<paper>，<figure/page>
内容：<expected visual content>
状态：待裁剪 / 需人工插入
```

The slide speaker notes must still include the PDF source, page number, OpenDataLoader status, rendered screenshot path or blocker, and failure reason.
