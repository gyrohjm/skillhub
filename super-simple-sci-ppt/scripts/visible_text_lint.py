#!/usr/bin/env python3
"""Lint only text that is audience-visible in PPTX slide XML."""

from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable
from xml.etree import ElementTree as ET

try:
    from pptx_slide_order import ordered_slide_parts
except ModuleNotFoundError as exc:  # Support importlib loading this standalone script by path.
    if exc.name != "pptx_slide_order":
        raise
    import importlib.util

    _slide_order_spec = importlib.util.spec_from_file_location(
        "pptx_slide_order", Path(__file__).with_name("pptx_slide_order.py")
    )
    if _slide_order_spec is None or _slide_order_spec.loader is None:
        raise ImportError("cannot load PPTX slide-order helper")
    _slide_order_module = importlib.util.module_from_spec(_slide_order_spec)
    _slide_order_spec.loader.exec_module(_slide_order_module)
    ordered_slide_parts = _slide_order_module.ordered_slide_parts


NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
}

PLACEHOLDER_RE = re.compile(
    r"\{\{[^{}]+\}\}|\$\{[^{}]+\}|<(?:title|body|caption|reference|name|date)[^>]*>|"
    r"\b(?:TBD|TODO|lorem ipsum|click to add|insert title|sample text)\b|"
    r"(?:替换为|请输入|待补充|待填写|占位符)",
    re.IGNORECASE,
)
LOCAL_PATH_RE = re.compile(
    r"(?:[A-Za-z]:\\|\\\\[^\\\s]+\\|/(?:home|Users|tmp|var/tmp|mnt|workspace)/)[^\s<>\"']*"
)
INTERNAL_PATTERNS = {
    "planning-field": re.compile(
        r"(?:internal[_ -]|slide[_ -]?intent|visible_(?:title|body|caption|reference)|"
        r"evidence[ _-]*map|\bboundary\b|\broute\b|\bpriority\b)", re.IGNORECASE
    ),
    "planning-label": re.compile(
        r"(?:任务边界|实验约束|证据图谱|验证重点|来源获取|内容路线|制作过程|素材数量|文件状态|"
        r"渲染状态|下载状态|QA 报告|QA报告)"
    ),
}
FORMULAIC_PATTERNS = {
    "consulting-or-ai-phrase": re.compile(
        r"(?:结论先行|核心矛盾|关键抓手|形成闭环|实现打通|提供支撑|赋能|落地|"
        r"takeaway|insight)", re.IGNORECASE
    ),
    "overclaim": re.compile(
        r"(?:完全证明|普遍适用|显著优于|已经解决|充分覆盖|绝对可靠|无可争议)"
    ),
}
GENERIC_TITLE_RE = re.compile(
    r"^(?:背景|研究背景|方法|研究方法|结果|研究结果|总结|结论|实验|计算|"
    r"实验进展|计算进展|机器学习势进展|相关工作|未来工作|展望)$"
)
SOURCE_LABEL_RE = re.compile(r"(?im)^\s*Source\s*:")
FILENAME_RE = re.compile(r"\b[^\s<>]+\.(?:pdf|pptx?|docx?|tex|py|mjs|js|json)\b", re.IGNORECASE)


@dataclass
class ShapeText:
    name: str
    text: str
    x: int | None
    y: int | None
    placeholder: str | None


@dataclass
class Finding:
    severity: str
    code: str
    slide: int
    text: str
    shape: str | None = None


def _visible_shapes(root: ET.Element) -> list[ShapeText]:
    shapes: list[ShapeText] = []
    for element in root.findall(".//p:sp", NS) + root.findall(".//p:graphicFrame", NS):
        c_nv_pr = element.find(".//p:cNvPr", NS)
        if c_nv_pr is not None and c_nv_pr.get("hidden") in {"1", "true", "True"}:
            continue
        texts = [node.text or "" for node in element.findall(".//a:t", NS)]
        text = "".join(texts).strip()
        if not text:
            continue
        name = c_nv_pr.get("name", "") if c_nv_pr is not None else ""
        ph = element.find(".//p:nvPr/p:ph", NS)
        placeholder = ph.get("type", "body") if ph is not None else None
        off = element.find(".//a:xfrm/a:off", NS)
        if off is None:
            off = element.find(".//p:xfrm/p:off", NS)
        x = int(off.get("x")) if off is not None and off.get("x") else None
        y = int(off.get("y")) if off is not None and off.get("y") else None
        shapes.append(ShapeText(name=name, text=text, x=x, y=y, placeholder=placeholder))
    return shapes


def _choose_title(shapes: Iterable[ShapeText]) -> ShapeText | None:
    items = list(shapes)
    placeholders = [s for s in items if s.placeholder in {"title", "ctrTitle"}]
    if placeholders:
        return min(placeholders, key=lambda s: s.y or 0)
    named = [s for s in items if "title" in s.name.lower()]
    if named:
        return min(named, key=lambda s: s.y or 0)
    return min(items, key=lambda s: (s.y if s.y is not None else 10**18)) if items else None


def _context_warnings(text: str) -> list[tuple[str, str]]:
    warnings: list[tuple[str, str]] = []
    if "约束" in text and not re.search(
        r"(?:数学|优化|几何|动力学|物理|边界|守恒|拉格朗日|线性|非线性)约束|约束(?:条件|方程|优化)", text
    ):
        warnings.append(("abstract-constraint", "“约束”未处于明确的数学、边界或优化语境"))
    if "路径" in text and not re.search(r"(?:反应|迁移|传播|光|积分|最小能量|合成)路径", text):
        warnings.append(("abstract-path", "“路径”未指明具体的反应、迁移、传播或计算对象"))
    for word in ("框架", "维度", "对齐", "聚焦", "主线", "闭环", "抓手", "打通"):
        if word in text:
            warnings.append(("abstract-packaging", f"检查“{word}”是否是严格术语；否则改写为具体事实"))
    return warnings


def lint_pptx(path: Path) -> dict[str, object]:
    findings: list[Finding] = []
    slides_summary: list[dict[str, object]] = []
    titles: list[str] = []

    with zipfile.ZipFile(path) as archive:
        slide_names = ordered_slide_parts(archive)
        if not slide_names:
            raise ValueError("PPTX contains no slide XML parts")

        for index, slide_name in enumerate(slide_names, start=1):
            root = ET.fromstring(archive.read(slide_name))
            shapes = _visible_shapes(root)
            title_shape = _choose_title(shapes)
            title = title_shape.text.strip() if title_shape else ""
            titles.append(title)
            slide_text = "\n".join(shape.text for shape in shapes)

            if not title:
                findings.append(Finding("error", "missing-title", index, "未识别到可见标题"))
            elif index > 1 and GENERIC_TITLE_RE.fullmatch(re.sub(r"[：:]$", "", title)):
                findings.append(Finding("warning", "generic-title", index, f"标题过于空泛：{title}", title_shape.name))

            for shape in shapes:
                for match in PLACEHOLDER_RE.finditer(shape.text):
                    findings.append(Finding("error", "placeholder", index, match.group(0), shape.name))
                for match in LOCAL_PATH_RE.finditer(shape.text):
                    findings.append(Finding("error", "local-path", index, match.group(0), shape.name))
                for match in FILENAME_RE.finditer(shape.text):
                    findings.append(Finding("error", "visible-filename", index, match.group(0), shape.name))
                if SOURCE_LABEL_RE.search(shape.text):
                    findings.append(Finding("error", "source-label", index, "可见文本包含 Source: 制作标签", shape.name))
                for code, pattern in INTERNAL_PATTERNS.items():
                    match = pattern.search(shape.text)
                    if match:
                        findings.append(Finding("error", code, index, match.group(0), shape.name))
                for code, pattern in FORMULAIC_PATTERNS.items():
                    match = pattern.search(shape.text)
                    if match:
                        findings.append(Finding("warning", code, index, match.group(0), shape.name))
                for code, message in _context_warnings(shape.text):
                    findings.append(Finding("warning", code, index, message, shape.name))

            slides_summary.append(
                {
                    "slide": index,
                    "slide_part": slide_name,
                    "title": title,
                    "visible_text_objects": len(shapes),
                    "visible_characters": len(slide_text),
                }
            )

    errors = sum(item.severity == "error" for item in findings)
    warnings = sum(item.severity == "warning" for item in findings)
    return {
        "pptx": str(path.resolve()),
        "slide_count": len(slides_summary),
        "title_chain": titles,
        "slides": slides_summary,
        "errors": errors,
        "warnings": warnings,
        "passed": errors == 0,
        "findings": [asdict(item) for item in findings],
    }


def _write_markdown(report: dict[str, object], path: Path) -> None:
    lines = [
        "# Visible Text Lint",
        "",
        f"- status: {'passed' if report['passed'] else 'failed'}",
        f"- slides: {report['slide_count']}",
        f"- errors: {report['errors']}",
        f"- warnings: {report['warnings']}",
        "",
        "## Title chain",
        "",
    ]
    lines.extend(f"{i}. {title}" for i, title in enumerate(report["title_chain"], start=1))
    lines.extend(["", "## Findings", ""])
    findings = report["findings"]
    if not findings:
        lines.append("No deterministic visible-text findings.")
    else:
        for item in findings:
            shape = f"; shape={item['shape']}" if item.get("shape") else ""
            lines.append(
                f"- [{item['severity']}] slide {item['slide']} `{item['code']}`{shape}: {item['text']}"
            )
    lines.extend(
        [
            "",
            "Warnings require contextual review. A deterministic pass does not replace slide-by-slide semantic review.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Lint audience-visible PPTX slide text; notes are intentionally excluded.")
    parser.add_argument("pptx", type=Path)
    parser.add_argument("--json", type=Path, help="machine-readable report")
    parser.add_argument("--report", type=Path, help="Markdown report")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.pptx.is_file() or args.pptx.suffix.lower() != ".pptx":
        print(f"ERROR: PPTX not found: {args.pptx}", file=sys.stderr)
        return 1
    try:
        report = lint_pptx(args.pptx)
        if args.json:
            args.json.parent.mkdir(parents=True, exist_ok=True)
            args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if args.report:
            _write_markdown(report, args.report)
    except (OSError, zipfile.BadZipFile, ET.ParseError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"Visible text lint: {'PASSED' if report['passed'] else 'FAILED'}")
    print(f"Slides: {report['slide_count']}  Errors: {report['errors']}  Warnings: {report['warnings']}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
