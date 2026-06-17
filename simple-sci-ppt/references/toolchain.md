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
| `pdfplumber` | Render PDF pages for paper-figure crops. | `python -m pip install pdfplumber` |
| `Pillow` | Crop and save image assets. | `python -m pip install pillow` |
| `matplotlib` | Render formula PNG fallback assets. | `python -m pip install matplotlib` |
| Microsoft PowerPoint on Windows | Open/export PPTX previews with COM. | Install Microsoft Office. |

Project-local setup:

```powershell
npm install pptxgenjs mathjax-full image-size
python -m pip install pdfplumber pillow matplotlib
```

Conda setup:

```powershell
conda activate <env-name>
python -m pip install pdfplumber pillow matplotlib
npm install pptxgenjs mathjax-full image-size
```

## Core Commands

| Tool | Purpose | Typical command |
|---|---|---|
| `scripts/inventory_refs.py` | Inventory papers, images, notes, data, or prior slides. | `python scripts/inventory_refs.py refs --out output/refs_inventory.md` |
| `scripts/crop_pdf_figure.py` | Render a PDF page and crop a paper figure or panel group. | `python scripts/crop_pdf_figure.py paper.pdf --page 2 --box "220,120,1035,815" --out figures/fig1.png --dpi 150` |
| `pptxgenjs` | Build editable PPTX slides. | `node generate_deck.js` |
| `scripts/render_mathjax_svg.mjs` | Render LaTeX formulas to SVG. | `node scripts/render_mathjax_svg.mjs --latex "..." --out formula.svg` |
| `scripts/render_latex_png.py` | Produce transparent PNG formula assets. | `python scripts/render_latex_png.py --latex "..." --out formula.png --dpi 320` |
| `scripts/verify_pptx.ps1` | Open PPTX, verify media, export previews. | `powershell -ExecutionPolicy Bypass -File scripts/verify_pptx.ps1 -Pptx deck.pptx -ExpectedSlides 4` |

## Minimum Sequence

```powershell
python scripts/inventory_refs.py refs --out output/refs_inventory.md
python scripts/crop_pdf_figure.py refs/paper.pdf --page 2 --box "220,120,1035,815" --out output/figures/fig1.png --dpi 150
node generate_deck.js
powershell -ExecutionPolicy Bypass -File scripts/verify_pptx.ps1 -Pptx output/deck.pptx -ExpectedSlides 4
```
