#!/usr/bin/env node
import fs from "node:fs";
import { createRequire } from "node:module";
import path from "node:path";

const require = createRequire(import.meta.url);

function requireFromProject(name) {
  try {
    return require(name);
  } catch {
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

function parseArgs(argv) {
  const args = { latex: "", out: "" };
  for (let i = 2; i < argv.length; i += 1) {
    if (argv[i] === "--latex") args.latex = argv[++i];
    if (argv[i] === "--out") args.out = path.resolve(argv[++i]);
  }
  if (!args.latex || !args.out) {
    throw new Error("Usage: node render_mathjax_svg.mjs --latex \"...\" --out formula.svg");
  }
  return args;
}

function normalizeMathJaxSvg(svgText) {
  let normalized = svgText.replaceAll("currentColor", "#000000");
  const viewBoxMatch = normalized.match(/viewBox="([^"]+)"/);
  if (viewBoxMatch) {
    const parts = viewBoxMatch[1].trim().split(/\s+/).map(Number);
    if (parts.length === 4 && Number.isFinite(parts[2]) && Number.isFinite(parts[3])) {
      normalized = normalized
        .replace(/width="[^"]+"/, `width="${parts[2]}"`)
        .replace(/height="[^"]+"/, `height="${parts[3]}"`);
    }
  }
  normalized = normalized.replace(/style="[^"]*vertical-align:[^"]*"/, "");
  return normalized;
}

async function main() {
  const args = parseArgs(process.argv);
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

  const node = html.convert(args.latex, { display: true });
  const svgText = normalizeMathJaxSvg(adaptor.outerHTML(node)
    .replace(/<mjx-container[^>]*>/, "")
    .replace(/<\/mjx-container>$/, ""));

  fs.mkdirSync(path.dirname(args.out), { recursive: true });
  fs.writeFileSync(args.out, svgText, "utf8");
  process.stdout.write(args.out);
}

main().catch((err) => {
  console.error(err.stack || err.message);
  process.exit(1);
});
