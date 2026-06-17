#!/usr/bin/env node
const childProcess = require("child_process");
const crypto = require("crypto");
const fs = require("fs");
const path = require("path");

function parseArgs(argv) {
  const args = {
    out: path.join(process.cwd(), "simple_sci_ppt_demo.pptx"),
    assetDir: path.join(process.cwd(), ".simple_sci_ppt_assets", "formulas"),
    python: "python",
  };
  for (let i = 2; i < argv.length; i += 1) {
    if (argv[i] === "--out") args.out = path.resolve(argv[++i]);
    if (argv[i] === "--asset-dir") args.assetDir = path.resolve(argv[++i]);
    if (argv[i] === "--python") args.python = argv[++i];
  }
  return args;
}

function requireFromProject(name) {
  try {
    return require(name);
  } catch (_) {
    let dir = process.cwd();
    while (true) {
      const local = path.join(dir, "node_modules", name);
      if (fs.existsSync(local)) return require(local);
      const parent = path.dirname(dir);
      if (parent === dir) break;
      dir = parent;
    }
    throw new Error(`Cannot resolve ${name}. Run from a project directory with node_modules or install it locally.`);
  }
}

function optionalLatexHelper() {
  const candidates = [
    path.join(process.cwd(), "pptxgenjs_helpers", "latex.js"),
    path.join(process.cwd(), "scripts", "pptxgenjs_helpers", "latex.js"),
    path.join(process.cwd(), "tools", "pptxgenjs_helpers", "latex.js"),
  ];
  for (const candidate of candidates) {
    if (fs.existsSync(candidate)) {
      const imageHelper = candidate.replace("latex.js", "image.js");
      if (fs.existsSync(imageHelper)) {
        return {
          latexToSvgDataUri: require(candidate).latexToSvgDataUri,
          imageSizingContain: require(imageHelper).imageSizingContain,
        };
      }
    }
  }
  return null;
}

function optionalMathJax() {
  try {
    const { mathjax } = requireFromProject("mathjax-full/js/mathjax.js");
    const { TeX } = requireFromProject("mathjax-full/js/input/tex.js");
    const { SVG } = requireFromProject("mathjax-full/js/output/svg.js");
    const { liteAdaptor } = requireFromProject("mathjax-full/js/adaptors/liteAdaptor.js");
    const { RegisterHTMLHandler } = requireFromProject("mathjax-full/js/handlers/html.js");
    const { AllPackages } = requireFromProject("mathjax-full/js/input/tex/AllPackages.js");
    const adaptor = liteAdaptor();
    RegisterHTMLHandler(adaptor);
    const tex = new TeX({ packages: AllPackages });
    const svg = new SVG({ fontCache: "none" });
    const html = mathjax.document("", { InputJax: tex, OutputJax: svg });
    return (latex) => {
      const node = html.convert(latex, { display: true });
      let svgText = adaptor.outerHTML(node)
        .replace(/<mjx-container[^>]*>/, "")
        .replace(/<\/mjx-container>$/, "");
      svgText = svgText.replaceAll("currentColor", "#000000");
      const viewBoxMatch = svgText.match(/viewBox="([^"]+)"/);
      if (viewBoxMatch) {
        const parts = viewBoxMatch[1].trim().split(/\s+/).map(Number);
        if (parts.length === 4 && Number.isFinite(parts[2]) && Number.isFinite(parts[3])) {
          svgText = svgText
            .replace(/width="[^"]+"/, `width="${parts[2]}"`)
            .replace(/height="[^"]+"/, `height="${parts[3]}"`);
        }
      }
      return svgText.replace(/style="[^"]*vertical-align:[^"]*"/, "");
    };
  } catch (_) {
    return null;
  }
}

const PptxGenJS = requireFromProject("pptxgenjs");
const { imageSize } = requireFromProject("image-size");
const latexHelper = optionalLatexHelper();
const mathjaxToSvg = optionalMathJax();
const pptx = new PptxGenJS();
pptx.layout = "LAYOUT_WIDE";
pptx.author = "Codex";
pptx.company = "simple-sci-ppt";
pptx.subject = "Grid-card classroom presentation";
pptx.title = "simple-sci-ppt demo";
pptx.lang = "en-US";
pptx.theme = { headFontFace: "Arial", bodyFontFace: "Arial", lang: "en-US" };
pptx.defineLayout({ name: "LAYOUT_WIDE", width: 13.333, height: 7.5 });

const CJK = "SimHei";
const EN = "Arial";
const DEFAULT_FONT = EN;
const CODE = "Consolas";
const COLORS = {
  white: "FFFFFF",
  ink: "111111",
  blue: "174F8A",
  paleBlue: "E8F2FA",
  paleBlue2: "F6FBFF",
  orange: "D66A13",
  paleOrange: "FFF0DE",
  red: "E00000",
  gray: "5B6472",
  borderSoft: "BFD8ED",
};
const SLIDE = { w: 13.333, h: 7.5 };
const SAFE = {
  bodyLeft: 0.40,
  bodyTop: 0.95,
  bodyRight: 12.90,
  bodyBottom: 6.70,
  conclusionY: 6.05,
  conclusionH: 0.72,
  conclusionBottom: 6.84,
  citationY: 7.04,
};
let formulaAssetDir = null;
let pythonExec = "python";
const formulaAssetCache = new Map();

const FORMULAS = {
  expectation: {
    label: "Rewrite dx as expectation under p(x)dx",
    latex: String.raw`I=\int f(x)\,dx=\int \frac{f(x)}{p(x)}p(x)\,dx=\mathbb{E}_p\left[\frac{f(x)}{p(x)}\right]`,
    fallback: "I = ∫ f(x)dx = ∫ f(x)/p(x) p(x)dx = E_p[f(x)/p(x)]",
    card: { x: 0.40, y: 1.18, w: 6.48, h: 1.20, fill: "paleBlue", line: "blue", formulaFontSize: 20 },
  },
  weight: {
    label: "Weight",
    latex: String.raw`w(x,y)=\frac{f(x,y)}{p(x,y)}=\frac{e^{-(x^2+y^2)}}{\pi^{-1}e^{-(x^2+y^2)}}=\pi`,
    fallback: "w(x,y) = f(x,y)/p(x,y) = exp[-(x²+y²)] / [π⁻¹ exp[-(x²+y²)]] = π",
    card: { x: 0.40, y: 2.88, w: 6.48, h: 1.20, fill: "paleOrange", line: "orange", formulaFontSize: 22 },
  },
  variance: {
    label: "Variance",
    latex: String.raw`\hat I_P=\frac{1}{N}\sum_{i=1}^{N}w_i=\pi,\qquad \mathrm{Var}(\hat I_P)=0`,
    fallback: "Î_P = (1/N) Σw_i = π,    Var(Î_P) = 0",
    card: { x: 0.40, y: 4.35, w: 6.48, h: 1.14, fill: "paleBlue", line: "blue", formulaFontSize: 22 },
  },
};

function frame(slide, page, title) {
  slide.background = { color: COLORS.white };
  slide.addText(title, { x: 0.30, y: 0.12, w: 9.6, h: 0.42, fontFace: DEFAULT_FONT, fontSize: 28, bold: true, color: COLORS.ink, margin: 0, fit: "shrink" });
  slide.addShape(pptx.ShapeType.line, { x: 0, y: 0.72, w: 13.333, h: 0, line: { color: COLORS.blue, pt: 1.1 } });
  slide.addText(String(page), { x: 12.55, y: 7.05, w: 0.35, h: 0.25, fontFace: EN, fontSize: 20, color: COLORS.gray, align: "right", margin: 0 });
}

function addSlideNotes(slide, notes) {
  if (!notes || !String(notes).trim()) {
    throw new Error("Every slide must include speaker notes.");
  }
  slide.addNotes(String(notes).trim());
}

function coverSlide({ topic, date = "<date>", presenter = "<name>", subtitle = "" }) {
  const slide = pptx.addSlide();
  slide.background = { color: COLORS.white };
  slide.addShape(pptx.ShapeType.rect, { x: 0.58, y: 1.12, w: 0.16, h: 0.82, fill: { color: COLORS.orange }, line: { color: COLORS.orange, pt: 0 } });
  slide.addText(topic, {
    x: 0.92,
    y: 1.02,
    w: 10.8,
    h: 0.92,
    fontFace: DEFAULT_FONT,
    fontSize: 38,
    bold: true,
    color: COLORS.ink,
    margin: 0,
    fit: "shrink",
  });
  slide.addShape(pptx.ShapeType.line, { x: 0.58, y: 2.18, w: 11.2, h: 0, line: { color: COLORS.blue, pt: 1.2 } });
  if (subtitle) {
    roundedBox(slide, 0.92, 2.70, 8.80, 0.78, { fill: COLORS.paleBlue, line: COLORS.blue, transparency: 12 });
    slide.addText(subtitle, { x: 1.18, y: 2.91, w: 8.25, h: 0.32, fontFace: DEFAULT_FONT, fontSize: 21, color: COLORS.ink, margin: 0, fit: "shrink" });
  }
  slide.addText(`Presenter: ${presenter}\nDate: ${date}`, {
    x: 0.92,
    y: 5.62,
    w: 5.0,
    h: 0.70,
    fontFace: DEFAULT_FONT,
    fontSize: 22,
    color: COLORS.ink,
    margin: 0,
    breakLine: false,
  });
  slide.addShape(pptx.ShapeType.line, { x: 0.92, y: 6.64, w: 2.40, h: 0, line: { color: COLORS.orange, pt: 2.0 } });
  addSlideNotes(slide, `Introduce the report topic, presenter, date, and source scope. State the central question before moving to the outline.`);
  return slide;
}

function roundedBox(slide, x, y, w, h, opts = {}) {
  assertOnSlide(opts.name || "roundedBox", x, y, w, h);
  slide.addShape(pptx.ShapeType.roundRect, {
    x, y, w, h,
    rectRadius: 0.045,
    fill: { color: opts.fill || COLORS.paleBlue, transparency: opts.transparency ?? 18 },
    line: { color: opts.line || COLORS.blue, pt: opts.pt || 1.1, transparency: opts.lineTransparency ?? 0 },
  });
}

function assertOnSlide(name, x, y, w, h) {
  if (x < 0 || y < 0 || x + w > SLIDE.w + 0.001 || y + h > SLIDE.h + 0.001) {
    throw new Error(`${name} outside slide bounds: x=${x}, y=${y}, w=${w}, h=${h}`);
  }
}

function assertInBodySafeArea(name, x, y, w, h) {
  if (x < SAFE.bodyLeft || y < SAFE.bodyTop || x + w > SAFE.bodyRight || y + h > SAFE.bodyBottom) {
    throw new Error(`${name} outside body safe area. Split the slide or reduce content.`);
  }
}

function label(slide, text, x, y, w, color = COLORS.blue) {
  slide.addText(text, { x, y, w, h: 0.25, fontFace: DEFAULT_FONT, fontSize: 22, bold: true, color, margin: 0, fit: "shrink" });
}

function containImage(pathOrBuffer, x, y, w, h, pad = 0.02) {
  const dims = typeof pathOrBuffer === "string" ? imageSize(pathOrBuffer) : imageSize(pathOrBuffer);
  const innerW = Math.max(w - 2 * pad, 0.01);
  const innerH = Math.max(h - 2 * pad, 0.01);
  const imgAspect = dims.width / dims.height;
  const boxAspect = innerW / innerH;
  let drawW;
  let drawH;

  if (imgAspect >= boxAspect) {
    drawW = innerW;
    drawH = innerW / imgAspect;
  } else {
    drawH = innerH;
    drawW = innerH * imgAspect;
  }

  return {
    x: x + (w - drawW) / 2,
    y: y + (h - drawH) / 2,
    w: drawW,
    h: drawH,
  };
}

function formulaAssetPath(latex) {
  if (!formulaAssetDir) return null;
  const key = crypto.createHash("sha1").update(latex).digest("hex").slice(0, 12);
  return {
    key,
    svg: path.join(formulaAssetDir, `${key}.svg`),
    png: path.join(formulaAssetDir, `${key}.png`),
  };
}

function ensureFormulaAssets(latex, fontSize = 22) {
  const cached = formulaAssetCache.get(latex);
  if (cached) return cached;

  const assetPaths = formulaAssetPath(latex);
  if (!assetPaths) return null;
  fs.mkdirSync(path.dirname(assetPaths.svg), { recursive: true });

  if (mathjaxToSvg && !fs.existsSync(assetPaths.svg)) {
    fs.writeFileSync(assetPaths.svg, mathjaxToSvg(latex), "utf8");
  }

  if (!fs.existsSync(assetPaths.png)) {
    const scriptPath = path.join(__dirname, "render_latex_png.py");
    childProcess.execFileSync(
      pythonExec,
      [
        scriptPath,
        "--latex", latex,
        "--out", assetPaths.png,
        "--fontsize", String(Math.max(fontSize + 10, 32)),
        "--dpi", "320",
        "--pad", "0.03",
      ],
      { stdio: "pipe" },
    );
  }

  formulaAssetCache.set(latex, assetPaths);
  return assetPaths;
}

function formula(slide, latex, fallback, x, y, w, h, fontSize = 22) {
  try {
    const assets = ensureFormulaAssets(latex, fontSize);
    if (assets?.png && fs.existsSync(assets.png)) {
      slide.addImage({ path: assets.png, ...containImage(assets.png, x, y, w, h, 0.01) });
      return;
    }
    if (assets?.svg && fs.existsSync(assets.svg)) {
      slide.addImage({ path: assets.svg, ...containImage(assets.svg, x, y, w, h, 0.01) });
      return;
    }
  } catch (_) {}
  if (mathjaxToSvg) {
    try {
      const svgBuffer = Buffer.from(mathjaxToSvg(latex));
      slide.addImage({ data: `data:image/svg+xml;base64,${svgBuffer.toString("base64")}`, ...containImage(svgBuffer, x, y, w, h, 0.01) });
      return;
    } catch (_) {}
  }
  if (latexHelper) {
    try {
      const svg = latexHelper.latexToSvgDataUri(latex, true);
      slide.addImage({ data: svg, ...latexHelper.imageSizingContain(svg, x, y, w, h) });
      return;
    } catch (_) {}
  }
  slide.addText(fallback || latex, { x, y, w, h, fontFace: EN, fontSize, color: COLORS.ink, margin: 0.03, fit: "shrink", valign: "mid", align: "center" });
}

function formulaCard(slide, labelText, latex, fallback, x, y, w, h, opts = {}) {
  roundedBox(slide, x, y, w, h, { fill: opts.fill || COLORS.paleBlue, line: opts.line || COLORS.blue, transparency: opts.transparency ?? 12 });
  label(slide, labelText, x + 0.16, y + 0.14, w - 0.32, opts.labelColor || COLORS.blue);
  formula(slide, latex, fallback, x + 0.34, y + 0.43, w - 0.68, h - 0.57, opts.formulaFontSize || 22);
}

function codeCard(slide, labelText, lines, x, y, w, h) {
  slide.addShape(pptx.ShapeType.roundRect, { x: x + 0.08, y: y - 0.42, w: 1.65, h: 0.33, rectRadius: 0.04, fill: { color: COLORS.orange }, line: { color: COLORS.orange, pt: 0 } });
  slide.addText(labelText, { x: x + 0.18, y: y - 0.35, w: 1.35, h: 0.20, fontFace: DEFAULT_FONT, fontSize: 20, bold: true, color: COLORS.white, margin: 0, align: "center", fit: "shrink" });
  roundedBox(slide, x, y, w, h, { fill: COLORS.paleBlue2, line: COLORS.borderSoft, transparency: 10, pt: 0.8 });
  const rich = [];
  for (const item of lines) {
    rich.push({ text: item.text + "\n", options: { breakLine: false, fontFace: CODE, fontSize: item.fontSize || 20, color: item.red ? COLORS.red : COLORS.ink } });
  }
  slide.addText(rich, { x: x + 0.16, y: y + 0.20, w: w - 0.26, h: h - 0.32, margin: 0, breakLine: false, fit: "shrink", valign: "top" });
}

function bulletCallout(slide, bullets, x, y, w, h) {
  roundedBox(slide, x, y, w, h, { fill: COLORS.paleOrange, line: "2F6FD6", transparency: 10, pt: 1.0 });
  const runs = [];
  for (const b of bullets) runs.push({ text: `• ${b}\n`, options: { fontFace: DEFAULT_FONT, fontSize: 22, color: COLORS.ink } });
  slide.addText(runs, { x: x + 0.45, y: y + 0.18, w: w - 0.65, h: h - 0.28, margin: 0, fit: "shrink" });
}

function conclusionBox(slide, text, x = 3.02, y = SAFE.conclusionY, w = 8.15, h = SAFE.conclusionH) {
  if (y + h > SAFE.conclusionBottom) throw new Error("conclusionBox is too close to the slide bottom; keep it above citations and page number.");
  roundedBox(slide, x, y, w, h, { fill: COLORS.paleOrange, line: "2F6FD6", transparency: 10, pt: 1.0 });
  slide.addText(text, { x: x + 0.35, y: y + 0.17, w: w - 0.70, h: h - 0.25, fontFace: DEFAULT_FONT, fontSize: 22, color: COLORS.ink, margin: 0, fit: "shrink", valign: "mid" });
}

function figurePlaceholder(slide, labelText, target, expected, x, y, w, h, opts = {}) {
  assertInBodySafeArea(opts.name || "figurePlaceholder", x, y, w, h);
  roundedBox(slide, x, y, w, h, {
    fill: opts.fill || COLORS.paleBlue2,
    line: opts.line || COLORS.borderSoft,
    transparency: opts.transparency ?? 8,
    pt: opts.pt || 1.0,
  });
  label(slide, labelText || "Figure placeholder", x + 0.18, y + 0.14, w - 0.36, opts.labelColor || COLORS.blue);
  const status = opts.status || "pending crop / manual insertion required";
  slide.addText(`To insert: ${target}\nExpected content: ${expected}\nStatus: ${status}`, {
    x: x + 0.32,
    y: y + 0.64,
    w: w - 0.64,
    h: h - 0.86,
    fontFace: DEFAULT_FONT,
    fontSize: opts.fontSize || 20,
    color: COLORS.gray,
    margin: 0,
    fit: "shrink",
    valign: "mid",
  });
}

function simpleTable(slide, rows, x, y, w, h, colRatios, opts = {}) {
  assertInBodySafeArea(opts.name || "simpleTable", x, y, w, h);
  const cols = Math.max(...rows.map((row) => row.length));
  const ratios = colRatios || Array(cols).fill(1);
  const ratioSum = ratios.reduce((sum, value) => sum + value, 0);
  const colWidths = ratios.map((value) => (w * value) / ratioSum);
  const rowH = h / rows.length;

  rows.forEach((row, r) => {
    let cx = x;
    for (let c = 0; c < cols; c += 1) {
      const cw = colWidths[c];
      const isHeader = r === 0;
      slide.addShape(pptx.ShapeType.rect, {
        x: cx,
        y: y + r * rowH,
        w: cw,
        h: rowH,
        fill: { color: isHeader ? COLORS.blue : (r % 2 === 0 ? COLORS.paleBlue2 : COLORS.white), transparency: isHeader ? 0 : 8 },
        line: { color: COLORS.blue, pt: 0.75 },
      });
      slide.addText(row[c] || "", {
        x: cx + 0.06,
        y: y + r * rowH + 0.05,
        w: cw - 0.12,
        h: rowH - 0.10,
        fontFace: DEFAULT_FONT,
        fontSize: opts.fontSize || 20,
        bold: isHeader,
        color: isHeader ? COLORS.white : COLORS.ink,
        align: "center",
        valign: "mid",
        margin: 0,
        fit: "shrink",
      });
      cx += cw;
    }
  });
}

function outlineSlide(page, title, items, notes) {
  const s = pptx.addSlide();
  frame(s, page, title);
  const startY = 1.18;
  const cardH = 1.05;
  items.forEach((item, idx) => {
    const y = startY + idx * 1.30;
    roundedBox(s, 0.72, y, 11.90, cardH, { fill: idx % 2 === 0 ? COLORS.paleBlue : COLORS.paleOrange, line: idx % 2 === 0 ? COLORS.blue : COLORS.orange, transparency: 12 });
    s.addText(String(idx + 1), { x: 0.98, y: y + 0.21, w: 0.48, h: 0.42, fontFace: EN, fontSize: 24, bold: true, color: idx % 2 === 0 ? COLORS.blue : COLORS.orange, margin: 0, align: "center" });
    s.addText(item.label, { x: 1.62, y: y + 0.18, w: 2.65, h: 0.30, fontFace: DEFAULT_FONT, fontSize: 23, bold: true, color: COLORS.ink, margin: 0, fit: "shrink" });
    s.addText(item.text, { x: 4.25, y: y + 0.18, w: 7.85, h: 0.48, fontFace: DEFAULT_FONT, fontSize: 21, color: COLORS.ink, margin: 0, fit: "shrink", valign: "mid" });
  });
  addSlideNotes(s, notes || "Use this slide to explain the deck structure and how the sections build toward the conclusion. Do not add a bottom conclusion box to the outline slide.");
  return s;
}

function conclusionSlide(page, title, takeaways, notes) {
  const s = pptx.addSlide();
  frame(s, page, title);
  simpleTable(s, [
    ["Takeaway", "Meaning"],
    ...takeaways.map((item) => [item.label, item.text]),
  ], 0.72, 1.25, 11.85, 3.85, [1.15, 3.1], { name: "conclusionTable" });
  roundedBox(s, 1.42, 5.55, 10.20, 0.72, { fill: COLORS.paleOrange, line: "2F6FD6", transparency: 10, pt: 1.0 });
  s.addText("Close by restating the main implication and the next decision or calculation.", {
    x: 1.78,
    y: 5.77,
    w: 9.5,
    h: 0.30,
    fontFace: DEFAULT_FONT,
    fontSize: 22,
    color: COLORS.ink,
    margin: 0,
    fit: "shrink",
  });
  addSlideNotes(s, notes || "Synthesize the main technical takeaways rather than listing slide titles. State the final implication and any evidence boundary.");
  return s;
}

function demoSlide() {
  const s = pptx.addSlide();
  frame(s, 2, "Exercise 10.19: Importance sampling makes weights constant");
  for (const key of ["expectation", "weight", "variance"]) {
    const item = FORMULAS[key];
    const fill = COLORS[item.card.fill];
    const line = COLORS[item.card.line];
    formulaCard(s, item.label, item.latex, item.fallback, item.card.x, item.card.y, item.card.w, item.card.h, { fill, line, formulaFontSize: item.card.formulaFontSize });
  }
  codeCard(s, "Key code", [
    { text: "def estimate_importance_gaussian(N, rng):" },
    { text: "    sigma = 1.0 / np.sqrt(2.0)" },
    { text: "    x = rng.normal(0.0, sigma, size=N)", red: true },
    { text: "    y = rng.normal(0.0, sigma, size=N)", red: true },
    { text: "    f = np.exp(-(x*x + y*y))" },
    { text: "    p = (1.0 / np.pi) * f" },
    { text: "    return np.mean(f / p)" },
  ], 7.05, 1.42, 5.90, 3.88);
  conclusionBox(s, "Matching the sampling density to the integrand makes the estimator variance vanish.");
  addSlideNotes(s, [
    "Explain the slide from left to right: first rewrite the integral as an expectation, then derive the constant weight, then connect the variance formula to the highlighted Gaussian sampling lines.",
    "",
    "LaTeX source:",
    `expectation: ${FORMULAS.expectation.latex}`,
    `weight: ${FORMULAS.weight.latex}`,
    `variance: ${FORMULAS.variance.latex}`,
  ].join("\n"));
}

async function main() {
  // New generators should reuse these template helpers instead of scattering
  // unconstrained addText/addShape coordinates. If content does not fit the
  // safe area, split the slide rather than shrinking teaching text. When a
  // required paper figure cannot be cropped, use figurePlaceholder().
  const args = parseArgs(process.argv);
  formulaAssetDir = args.assetDir;
  pythonExec = args.python;
  coverSlide({
    topic: "Variance Control in Importance Sampling",
    date: "<date>",
    presenter: "<name>",
    subtitle: "Explaining Monte Carlo integration error through sampling density selection",
  });
  outlineSlide(1, "Outline: Sampling density controls estimator variance", [
    { label: "Transform", text: "Rewrite the integral as an expectation and identify the sample weight." },
    { label: "Choose density", text: "Match the sampling density to the integrand so that weights become constant." },
    { label: "Map to code", text: "Use Gaussian sampling lines to connect the formula to implementation." },
  ]);
  demoSlide();
  conclusionSlide(3, "Conclusion: Distribution choice determines variance", [
    { label: "Estimator", text: "Importance sampling changes the estimator by changing the probability measure." },
    { label: "Variance", text: "A density proportional to the integrand can collapse the weight variance." },
    { label: "Implementation", text: "The code should make the sampling density explicit and verifiable." },
  ]);
  fs.mkdirSync(path.dirname(args.out), { recursive: true });
  fs.mkdirSync(formulaAssetDir, { recursive: true });
  if (fs.existsSync(args.out)) fs.unlinkSync(args.out);
  await pptx.writeFile({ fileName: args.out });
  console.log(`Wrote ${args.out}`);
}

main().catch((err) => {
  console.error(err.stack || err.message);
  process.exit(1);
});

