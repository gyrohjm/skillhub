# Reference-Folder MinerU Addendum

This addendum strengthens `reference-folder-workflow.md` for PDF-heavy decks.

## Rule

When a reference folder contains PDFs that may provide figures, panels, captions, tables, equations, or diagrams, the agent must use the MinerU-first policy before crop planning.

## Required Steps

1. Inventory the reference folder.
2. Identify PDFs that may provide visual evidence.
3. Run `scripts/mineru_extract.py` on each relevant PDF (single-file or batch mode).
4. Read the generated `full.md` for each PDF to locate candidate figures, tables, captions, and layout regions.
5. If MinerU fails or returns no parse artifact, ask the user whether to retry before using fallback tools.
6. Render each candidate PDF page to a screenshot.
7. Inspect the screenshot visually before crop selection.
8. Crop the selected visual or insert a placeholder.
9. Record source traceability in the markdown plan and speaker notes.

## Batch Parse

For a reference folder with multiple PDFs:

```powershell
python scripts/mineru_extract.py -d refs/ --limit 20
```

This parses all PDFs in the folder (up to the limit) and stores results under the output root, one subfolder per PDF stem.

## Traceability Fields

For every PDF-derived visual, record:

| field | meaning |
|---|---|
| `object_id` | PPT object id or visible label |
| `source_pdf` | source PDF path or paper id |
| `page` | PDF page number |
| `figure/panel/table` | figure, panel, table, equation, or diagram id |
| `mineru_parse_output` | `full.md` path and `images/` folder path, or `MinerU parse failed` |
| `rendered_page_screenshot` | rendered candidate page screenshot path |
| `crop_box` | crop box when available |
| `final_asset` | final cropped/generated asset path when available |
| `status` | `inserted`, `placeholder`, `pending crop`, `fallback`, or `omitted` |
| `note` | failure reason or remaining manual action |

## Missing MinerU Parse

If MinerU fails, use this confirmation before fallback:

```text
MinerU 解析失败：<错误信息>。是否需要重试（更换 model 版本 / 检查网络）？如果不重试，我会退回到 pdfplumber/PyMuPDF 渲染页面截图 + 手动裁剪/占位流程，并在备注中记录解析限制。
```

Do not proceed with fallback parsing unless the user approves fallback or the environment clearly cannot reach the MinerU API.

## Placeholder Notes

If a figure cannot be cropped, the visible placeholder must include:

```text
待插入：<paper>，<figure/page>
内容：<expected visual content>
状态：待裁剪 / 需人工插入
```

The slide speaker notes must still include the PDF source, page number, MinerU parse status, rendered screenshot path or blocker, and failure reason.
