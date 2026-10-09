# Toolchain

Use these tools for deck generation. State the concrete tools and commands in the markdown plan and final response.

## Install Dependencies

| Dependency | Purpose | Install / download |
|---|---|---|
| Node.js 18+ | Run `pptxgenjs` and MathJax scripts. | Download from `https://nodejs.org/`; verify with `node -v` and `npm -v`. |
| `pptxgenjs` | Generate editable `.pptx` slides. | `npm install pptxgenjs` |
| `mathjax-full` | Render LaTeX formulas to SVG. | `npm install mathjax-full` |
| `image-size` | Preserve image aspect ratio. | `npm install image-size` |
| Python 3.9+ | Run inventory, PDF crop, and formula helpers. | Download from `https://www.python.org/downloads/`, Anaconda, or project Python. |
| MinerU (`scripts/mineru_extract.py`) | Preferred PDF layout parsing layer for paper figures, captions, tables, and regions. | `python -m pip install requests` (script dependency); token in `scripts/mineru_config.json` (copy from `mineru_config.example.json`). |
| `pdfplumber` | Fallback PDF page rendering/crop support after MinerU fails and fallback is approved. | `python -m pip install pdfplumber` |
| `Pillow` | Crop and save image assets. | `python -m pip install pillow` |
| `matplotlib` | Render formula PNG fallback assets. | `python -m pip install matplotlib` |
| Microsoft PowerPoint on Windows | Open/export PPTX previews with COM. | Install Microsoft Office. |

Project-local setup:

```powershell
npm install pptxgenjs mathjax-full image-size
python -m pip install requests pdfplumber pillow matplotlib
```

Conda setup:

```powershell
conda activate <env-name>
python -m pip install pdfplumber pillow matplotlib
npm install pptxgenjs mathjax-full image-size
```

## MinerU PDF Parse

Before extracting PDF-derived figures, tables, formulas, captions, or diagrams, run MinerU to obtain a structured Markdown parse and extracted images.

### Single-file parse

```powershell
python scripts/mineru_extract.py -f refs/paper.pdf
```

### Batch parse

```powershell
python scripts/mineru_extract.py -d refs/ --limit 20
```

The script uploads the PDF to the MinerU API (`https://mineru.net/api/v4`), polls until parsing completes, then downloads and extracts the result into `<output_root>/<pdf_stem>/full.md` and `<output_root>/<pdf_stem>/images/`. The API token is read from the `MINERU_API_TOKEN` environment variable, or from `scripts/mineru_config.json` (copy `mineru_config.example.json` and fill in your token). The config file is git-ignored.

If MinerU fails, ask the user whether to retry before using fallback tools. Do not silently fall back.

## Core Commands

| Tool | Purpose | Typical command |
|---|---|---|
| `scripts/inventory_refs.py` | Inventory papers, images, notes, data, or prior slides. | `python scripts/inventory_refs.py refs --out output/refs_inventory.md` |
| `scripts/mineru_extract.py` | Preferred structured PDF parsing before crop planning. | `python scripts/mineru_extract.py -f refs/paper.pdf` (output: `full.md` + `images/`) |
| `scripts/crop_pdf_figure.py` | Render a PDF page and crop a paper figure or panel group. | `python scripts/crop_pdf_figure.py paper.pdf --page 2 --box "220,120,1035,815" --out figures/fig1.png --dpi 150` |
| `pptxgenjs` | Build editable PPTX slides. | `node generate_deck.js` |
| `scripts/render_mathjax_svg.mjs` | Render LaTeX formulas to SVG. | `node scripts/render_mathjax_svg.mjs --latex "..." --out formula.svg` |
| `scripts/render_latex_png.py` | Produce transparent PNG formula assets. | `python scripts/render_latex_png.py --latex "..." --out formula.png --dpi 320` |
| `scripts/verify_pptx.ps1` | Open PPTX, verify media, export previews. | `powershell -ExecutionPolicy Bypass -File scripts/verify_pptx.ps1 -Pptx deck.pptx -ExpectedSlides 4` |

## Minimum Sequence

```powershell
python scripts/inventory_refs.py refs --out output/refs_inventory.md
# Run MinerU before PDF crop planning when PDF-derived visuals are needed.
python scripts/mineru_extract.py -f refs/paper.pdf
python scripts/crop_pdf_figure.py refs/paper.pdf --page 2 --box "220,120,1035,815" --out output/figures/fig1.png --dpi 150
node generate_deck.js
powershell -ExecutionPolicy Bypass -File scripts/verify_pptx.ps1 -Pptx output/deck.pptx -ExpectedSlides 4
```
