// Layout archetype constants and collision audit helpers for simple-sci-ppt.
// This file is intentionally dependency-light. Import or copy these constants
// into a pptxgenjs generator before placing slide objects.

const SPACING = 0.06;

const LAYOUTS = {
  twoFiguresSummary: {
    fig_left: { role: 'figure', x: 0.55, y: 1.05, w: 5.95, h: 4.85 },
    fig_right: { role: 'figure', x: 6.82, y: 1.05, w: 5.95, h: 4.85 },
    summary: { role: 'summary', x: 2.20, y: 6.12, w: 8.95, h: 0.52 },
    reference: { role: 'reference', x: 0.45, y: 7.05, w: 8.50, h: 0.24 },
  },

  figureBulletsSummary: {
    figure: { role: 'figure', x: 0.55, y: 1.05, w: 6.10, h: 4.85 },
    bullets: { role: 'callout', x: 6.95, y: 1.05, w: 5.75, h: 4.85 },
    summary: { role: 'summary', x: 2.20, y: 6.12, w: 8.95, h: 0.52 },
    reference: { role: 'reference', x: 0.45, y: 7.05, w: 8.50, h: 0.24 },
  },

  formulaTableExplainSummary: {
    formula: { role: 'formula', x: 0.55, y: 1.05, w: 5.95, h: 1.45 },
    table: { role: 'table', x: 6.82, y: 1.05, w: 5.95, h: 2.20 },
    explanation: { role: 'callout', x: 0.55, y: 3.55, w: 12.22, h: 1.85 },
    summary: { role: 'summary', x: 2.20, y: 6.12, w: 8.95, h: 0.52 },
    reference: { role: 'reference', x: 0.45, y: 7.05, w: 8.50, h: 0.24 },
  },

  threeCardsSummary: {
    card_1: { role: 'card', x: 0.55, y: 1.15, w: 3.85, h: 4.75 },
    card_2: { role: 'card', x: 4.75, y: 1.15, w: 3.85, h: 4.75 },
    card_3: { role: 'card', x: 8.95, y: 1.15, w: 3.85, h: 4.75 },
    summary: { role: 'summary', x: 2.20, y: 6.12, w: 8.95, h: 0.52 },
    reference: { role: 'reference', x: 0.45, y: 7.05, w: 8.50, h: 0.24 },
  },

  fourPanelSummary: {
    fig_1: { role: 'figure', x: 0.55, y: 1.05, w: 5.95, h: 2.25 },
    fig_2: { role: 'figure', x: 6.82, y: 1.05, w: 5.95, h: 2.25 },
    fig_3: { role: 'figure', x: 0.55, y: 3.55, w: 5.95, h: 2.25 },
    fig_4: { role: 'figure', x: 6.82, y: 3.55, w: 5.95, h: 2.25 },
    summary: { role: 'summary', x: 2.20, y: 6.12, w: 8.95, h: 0.52 },
    reference: { role: 'reference', x: 0.45, y: 7.05, w: 8.50, h: 0.24 },
  },

  largeFigureSummary: {
    figure: { role: 'figure', x: 0.65, y: 1.00, w: 12.00, h: 5.35 },
    summary: { role: 'summary', x: 2.20, y: 6.18, w: 8.95, h: 0.48 },
    reference: { role: 'reference', x: 0.45, y: 7.05, w: 8.50, h: 0.24 },
  },
};

function asBox(id, box) {
  return { id, role: box.role || 'object', x: box.x, y: box.y, w: box.w, h: box.h };
}

function intersects(a, b, pad = SPACING) {
  return !(
    a.x + a.w + pad <= b.x ||
    b.x + b.w + pad <= a.x ||
    a.y + a.h + pad <= b.y ||
    b.y + b.h + pad <= a.y
  );
}

function violatesRoleRule(a, b) {
  const pair = new Set([a.role, b.role]);
  if (pair.has('callout') && (pair.has('figure') || pair.has('table') || pair.has('formula') || pair.has('reference') || pair.has('summary') || pair.has('pageNumber'))) return true;
  if (pair.has('summary') && (pair.has('reference') || pair.has('pageNumber'))) return true;
  if (pair.has('reference') && pair.has('pageNumber')) return true;
  if ((pair.has('table') && pair.has('figure')) || (pair.has('table') && pair.has('formula')) || (pair.has('figure') && pair.has('formula'))) return true;
  return false;
}

function assertOnSlide(box, width = 13.333, height = 7.5) {
  if (box.x < 0 || box.y < 0 || box.x + box.w > width || box.y + box.h > height) {
    throw new Error(`L001 outside slide: ${box.id} (${box.x}, ${box.y}, ${box.w}, ${box.h})`);
  }
}

function auditLayout(layout, options = {}) {
  const boxes = Object.entries(layout).map(([id, box]) => asBox(id, box));
  const errors = [];

  for (const box of boxes) {
    try {
      assertOnSlide(box, options.width || 13.333, options.height || 7.5);
    } catch (err) {
      errors.push(String(err.message || err));
    }
  }

  for (let i = 0; i < boxes.length; i += 1) {
    for (let j = i + 1; j < boxes.length; j += 1) {
      const a = boxes[i];
      const b = boxes[j];
      if (!intersects(a, b, options.spacing || SPACING)) continue;
      const code = violatesRoleRule(a, b) ? 'L004' : 'L003';
      errors.push(`${code} layout collision: ${a.id} (${a.role}) overlaps ${b.id} (${b.role})`);
    }
  }

  return { ok: errors.length === 0, errors, boxes };
}

function requireLayout(name) {
  const layout = LAYOUTS[name];
  if (!layout) {
    throw new Error(`Unknown layout archetype: ${name}. Available: ${Object.keys(LAYOUTS).join(', ')}`);
  }
  const result = auditLayout(layout);
  if (!result.ok) {
    throw new Error(`Layout archetype ${name} failed audit:\n${result.errors.join('\n')}`);
  }
  return layout;
}

function layoutBoxTableMarkdown(slideNumber, archetypeName, content = {}) {
  const layout = requireLayout(archetypeName);
  const rows = [
    '| slide | archetype | object_id | role | x | y | w | h | expected_content |',
    '|---:|---|---|---|---:|---:|---:|---:|---|',
  ];
  for (const [id, box] of Object.entries(layout)) {
    rows.push(`| ${slideNumber} | ${archetypeName} | ${id} | ${box.role} | ${box.x.toFixed(2)} | ${box.y.toFixed(2)} | ${box.w.toFixed(2)} | ${box.h.toFixed(2)} | ${content[id] || ''} |`);
  }
  return rows.join('\n');
}

module.exports = {
  SPACING,
  LAYOUTS,
  auditLayout,
  requireLayout,
  layoutBoxTableMarkdown,
};
