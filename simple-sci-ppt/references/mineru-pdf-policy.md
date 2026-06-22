# MinerU PDF Parsing Policy

Use this policy when the deck uses figures, tables, formulas, captions, or diagrams from PDF files.

## Default Rule

Prefer MinerU for PDF document parsing before using lower-level fallback tools.

MinerU (online API via `scripts/mineru_extract.py`) is the first-choice PDF ingestion layer because it converts a paper PDF into structured Markdown (`full.md`) plus an extracted `images/` folder, providing text, figure, table, caption, and layout information that is more useful for slide planning than raw text extraction alone.

## Required Decision Flow

1. Run `scripts/mineru_extract.py` on the source PDF to obtain the Markdown parse and image assets.
2. Read the generated `full.md` to locate candidate pages, captions, figure/table regions, and layout metadata.
3. Render each candidate PDF page to an image screenshot (using the MinerU-extracted images or a separate page render).
4. Inspect the rendered page screenshot as visual input before deciding the crop boundary or placeholder.
5. Record the MinerU parse output path, rendered page screenshot path, selected figure/table/page, crop box, crop asset path, and status in the markdown plan and speaker notes.
6. If MinerU fails or returns no parse artifact, ask the user whether to retry before falling back to `pdfplumber`, PyMuPDF, manual screenshot rendering, or placeholder-only handling.

## Tool Configuration

| Component | Path / value |
|---|---|
| MinerU script | `scripts/mineru_extract.py` |
| MinerU API endpoint | `https://mineru.net/api/v4` |
| API Token | Environment variable `MINERU_API_TOKEN`, or `scripts/mineru_config.json`（copy `mineru_config.example.json` and fill in your token）. The config file is git-ignored. |
| Default output root | `D:\yychen\MinerU\output` (override with `--output`) |
| Per-PDF output layout | `<output_root>/<pdf_stem>/full.md` and `<output_root>/<pdf_stem>/images/` |

### Single-file parse

```powershell
python scripts/mineru_extract.py -f refs/paper.pdf
```

### Batch parse

```powershell
python scripts/mineru_extract.py -d refs/ --limit 20
```

The script uploads the PDF, polls the API until parsing completes, then downloads and extracts the result zip into the output root. The output folder preserves the PDF stem name.

## Expected Use

When successful, MinerU produces a structured parse artifact under the output root:

```text
<output_root>/<paper_stem>/full.md
<output_root>/<paper_stem>/images/
```

`full.md` contains the paper's title, authors, abstract, body text, tables, formulas, and figure references. The `images/` folder contains all extracted figure images.

The markdown plan should include a traceability row for every PDF-derived visual:

| object_id | source_pdf | page | figure/panel/table | mineru_parse_output | rendered_page_screenshot | crop_box | final_asset | status | note |
|---|---|---:|---|---|---|---|---|---|---|

## Missing Environment Rule

If MinerU returns an error, the API is unreachable, or no parse artifact is produced:

1. State that the MinerU parse failed and include the error message.
2. Ask the user whether to retry (different model version, network check) before falling back.
3. Do not silently downgrade to another parser unless the user has already allowed fallback tools or retry is impossible in the current environment.
4. If the user declines retry, continue with the approved fallback path and record the blocker in the markdown plan and speaker notes.

Recommended user-facing confirmation:

```text
MinerU 解析失败：<错误信息>。是否需要重试（更换 model 版本 / 检查网络）？如果不重试，我会退回到 pdfplumber/PyMuPDF 渲染页面截图 + 手动裁剪/占位流程，并在备注中记录解析限制。
```

## Fallback Rule

Fallback tools are allowed only after the missing-environment rule is satisfied.

Allowed fallbacks include:

- `pdfplumber` or PyMuPDF for page rendering and text/crop support,
- manual rendered-page screenshot inspection,
- user-provided screenshots or figure files,
- placeholder frames with source, page, expected content, and failure reason.

Fallback does not remove the screenshot inspection requirement. Even without MinerU, every PDF-derived visual must still be tied to a rendered page screenshot or an explicit rendering blocker.

## Speaker Notes Requirement

Every PDF-derived visual must include an `Image sources:` entry in speaker notes. The entry must record:

- source PDF path or paper identifier,
- page number,
- figure/panel/table label when available,
- MinerU parse output path or `MinerU parse failed`,
- rendered page screenshot path or rendering failure reason,
- crop box and crop asset path when available,
- PPT status: `inserted`, `placeholder`, `pending crop`, `omitted`, or `fallback`,
- remaining manual action if any.

## Hard Failures

- The agent uses a PDF-derived figure without first running MinerU or recording that the user approved a fallback path.
- The agent silently falls back to another parser when MinerU fails without asking the user.
- The agent uses PDF text extraction alone to decide crop boundaries.
- The agent inserts or placeholders a PDF-derived visual without a rendered page screenshot path or documented rendering blocker.
- The speaker notes omit the PDF source, page, parse artifact/status, screenshot path/status, or crop/placeholder status.
