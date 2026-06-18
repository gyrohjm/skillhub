# OpenDataLoader PDF Parsing Policy

Use this policy when the deck uses figures, tables, formulas, captions, or diagrams from PDF files.

## Default Rule

Prefer OpenDataLoader for PDF document parsing before using lower-level fallback tools.

OpenDataLoader should be treated as the first-choice PDF ingestion layer because it can provide structured page, text, figure, table, caption, and layout information that is more useful for slide planning than raw text extraction alone.

## Required Decision Flow

1. Check whether OpenDataLoader is available in the current environment.
2. If available, use it to parse the PDF and obtain candidate pages, captions, figure/table regions, and layout metadata.
3. Render each candidate PDF page to an image screenshot.
4. Inspect the rendered page screenshot as visual input before deciding the crop boundary or placeholder.
5. Record the OpenDataLoader output path, rendered page screenshot path, selected figure/table/page, crop box, crop asset path, and status in the markdown plan and speaker notes.
6. If OpenDataLoader is not available, ask the user whether to install it before falling back to `pdfplumber`, PyMuPDF, manual screenshot rendering, or placeholder-only handling.

## Availability Check

Use one or more lightweight checks. Do not perform a heavyweight parse just to test availability.

```bash
python - <<'PY'
import importlib.util
names = ["opendataloader", "open_data_loader", "opendataloader_pdf"]
print({name: importlib.util.find_spec(name) is not None for name in names})
PY
```

If the project provides a CLI, also check commands such as:

```bash
opendataloader --help
opendataloader-pdf --help
```

The exact package or CLI name may vary across installations. If the module/CLI name is uncertain, inspect the project documentation or installed package metadata before claiming that parsing is available.

## Expected Use

When available, use OpenDataLoader to produce a structured PDF parse artifact, preferably under the deck working directory:

```text
<workdir>/pdf_parse/<paper_stem>/opendataloader_parse.json
<workdir>/pdf_parse/<paper_stem>/pages/page_003.png
<workdir>/figures/<paper_stem>_fig2a.png
```

The markdown plan should include a traceability row for every PDF-derived visual:

| object_id | source_pdf | page | figure/panel/table | opendataloader_artifact | rendered_page_screenshot | crop_box | final_asset | status | note |
|---|---|---:|---|---|---|---|---|---|---|

## Missing Environment Rule

If OpenDataLoader is not installed or cannot be imported/run:

1. State that OpenDataLoader is unavailable.
2. Ask the user whether to install it in the current environment.
3. Do not silently downgrade to another parser unless the user has already allowed fallback tools or installation is impossible in the current environment.
4. If the user declines installation, continue with the approved fallback path and record the blocker in the markdown plan and speaker notes.

Recommended user-facing confirmation:

```text
当前环境没有检测到 OpenDataLoader。是否需要我先安装/配置 OpenDataLoader 以解析 PDF 版面？如果不安装，我会退回到 pdfplumber/PyMuPDF 渲染页面截图 + 手动裁剪/占位流程，并在备注中记录解析限制。
```

## Fallback Rule

Fallback tools are allowed only after the missing-environment rule is satisfied.

Allowed fallbacks include:

- `pdfplumber` or PyMuPDF for page rendering and text/crop support,
- manual rendered-page screenshot inspection,
- user-provided screenshots or figure files,
- placeholder frames with source, page, expected content, and failure reason.

Fallback does not remove the screenshot inspection requirement. Even without OpenDataLoader, every PDF-derived visual must still be tied to a rendered page screenshot or an explicit rendering blocker.

## Speaker Notes Requirement

Every PDF-derived visual must include an `Image sources:` entry in speaker notes. The entry must record:

- source PDF path or paper identifier,
- page number,
- figure/panel/table label when available,
- OpenDataLoader parse artifact path or `OpenDataLoader unavailable`,
- rendered page screenshot path or rendering failure reason,
- crop box and crop asset path when available,
- PPT status: `inserted`, `placeholder`, `pending crop`, `omitted`, or `fallback`,
- remaining manual action if any.

## Hard Failures

- The agent uses a PDF-derived figure without first checking whether OpenDataLoader is available.
- The agent silently falls back to another parser when OpenDataLoader is missing without asking the user.
- The agent uses PDF text extraction alone to decide crop boundaries.
- The agent inserts or placeholders a PDF-derived visual without a rendered page screenshot path or documented rendering blocker.
- The speaker notes omit the PDF source, page, parse artifact/status, screenshot path/status, or crop/placeholder status.
