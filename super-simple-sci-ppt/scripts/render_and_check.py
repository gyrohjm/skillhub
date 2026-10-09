#!/usr/bin/env python3
"""Export a PPTX to PDF, render every page, run mechanical checks, and bind visual review to hashes."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
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

TITLE_TARGET_PT = 32.0
BODY_TARGET_PT = 24.0
FOOTER_TARGET_PT = 16.0
FONT_SIZE_TOLERANCE_PT = 0.05
SUBSUPER_MIN_RATIO = 0.65
SUBSUPER_MAX_RATIO = 0.75
NESTED_SUBSUPER_RATIO = 0.49
NESTED_SUBSUPER_TOLERANCE = 0.015
FIRST_LEVEL_SUBSCRIPT_BASELINE = -25000
FIRST_LEVEL_SUPERSCRIPT_BASELINE = 35000
SECOND_LEVEL_SUB_AFTER_SUB_BASELINE = -60714
SECOND_LEVEL_SUB_AFTER_SUPER_BASELINE = 25000
FOOTER_NAME_RE = re.compile(r"(?:reference|citation|footer|(?:^|[-_\s])page(?:[ _-]?number)?(?:$|[-_\s]))", re.IGNORECASE)
TITLE_NAME_RE = re.compile(r"(?:^|[-_\s])title(?:$|[-_\s])", re.IGNORECASE)


@dataclass
class Issue:
    severity: str
    code: str
    message: str
    slide: int | None = None
    shape: str | None = None


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _shape_bounds(element: ET.Element) -> tuple[int, int, int, int] | None:
    off = element.find(".//a:xfrm/a:off", NS)
    ext = element.find(".//a:xfrm/a:ext", NS)
    if off is None or ext is None:
        off = element.find(".//p:xfrm/p:off", NS)
        ext = element.find(".//p:xfrm/p:ext", NS)
    if off is None or ext is None:
        return None
    return (
        int(off.get("x", "0")),
        int(off.get("y", "0")),
        int(ext.get("cx", "0")),
        int(ext.get("cy", "0")),
    )


def _shape_role(element: ET.Element, shape_name: str, y: int | None, slide_height: int) -> str:
    placeholder = element.find(".//p:nvPr/p:ph", NS)
    placeholder_type = placeholder.get("type") if placeholder is not None else ""
    if placeholder_type in {"title", "ctrTitle"} or TITLE_NAME_RE.search(shape_name):
        return "title"
    if placeholder_type in {"sldNum", "dt", "ftr"} or FOOTER_NAME_RE.search(shape_name):
        return "footer"
    return "body"


def _target_pt(role: str) -> float:
    if role == "title":
        return TITLE_TARGET_PT
    if role == "footer":
        return FOOTER_TARGET_PT
    return BODY_TARGET_PT


def _is_normal_nested_subscript(paragraph: list[dict[str, object]], index: int, target_pt: float) -> bool:
    """Allow only the explicit recursive 70% motif/formula form.

    The child is 70% of a first-level 70% run (49% of its title/body/footer
    baseline). It must immediately follow that parent and use the baseline
    offsets emitted for a subscript nested under either a subscript or a
    superscript. This deliberately does not permit a standalone 49% text run.
    """
    if index == 0:
        return False
    child = paragraph[index]
    parent = paragraph[index - 1]
    child_size = child["size"]
    parent_size = parent["size"]
    child_baseline = child["baseline"]
    parent_baseline = parent["baseline"]
    if not isinstance(child_size, float) or not isinstance(parent_size, float):
        return False
    if not isinstance(child_baseline, int) or not isinstance(parent_baseline, int):
        return False
    if abs(child_size / target_pt - NESTED_SUBSUPER_RATIO) > NESTED_SUBSUPER_TOLERANCE:
        return False
    if not SUBSUPER_MIN_RATIO <= parent_size / target_pt <= SUBSUPER_MAX_RATIO:
        return False
    return (
        parent_baseline == FIRST_LEVEL_SUBSCRIPT_BASELINE
        and child_baseline == SECOND_LEVEL_SUB_AFTER_SUB_BASELINE
    ) or (
        parent_baseline == FIRST_LEVEL_SUPERSCRIPT_BASELINE
        and child_baseline == SECOND_LEVEL_SUB_AFTER_SUPER_BASELINE
    )


def _paragraph_font_records(element: ET.Element) -> list[list[dict[str, object]]]:
    paragraphs: list[list[dict[str, object]]] = []
    for paragraph in element.findall(".//a:p", NS):
        default = paragraph.find("./a:pPr/a:defRPr", NS)
        records: list[dict[str, object]] = []
        for run in list(paragraph.findall("./a:r", NS)) + list(paragraph.findall("./a:fld", NS)):
            text = "".join(node.text or "" for node in run.findall(".//a:t", NS))
            if not text:
                continue
            properties = run.find("./a:rPr", NS)
            if properties is None:
                properties = default
            size = None
            baseline = 0
            spacing = None
            color = None
            if properties is not None:
                value = properties.get("sz")
                if value:
                    size = int(value) / 100.0
                baseline = int(properties.get("baseline", "0"))
                spacing = int(properties.get("spc", "0"))
                rgb = properties.find("./a:solidFill/a:srgbClr", NS)
                if rgb is not None:
                    color = rgb.get("val", "").upper()
            records.append(
                {"text": text, "size": size, "baseline": baseline, "spacing": spacing, "color": color}
            )
        if records:
            paragraphs.append(records)
    return paragraphs


def _check_scaled_text_groups(root: ET.Element, slide: int, issues: list[Issue]) -> None:
    for group in root.findall(".//p:grpSp", NS):
        if not any((node.text or "").strip() for node in group.findall(".//a:t", NS)):
            continue
        name_node = group.find("./p:nvGrpSpPr/p:cNvPr", NS)
        shape_name = name_node.get("name", "") if name_node is not None else ""
        transform = group.find("./p:grpSpPr/a:xfrm", NS)
        if transform is None:
            continue
        ext = transform.find("./a:ext", NS)
        child_ext = transform.find("./a:chExt", NS)
        if ext is None or child_ext is None:
            continue
        width = int(ext.get("cx", "0"))
        height = int(ext.get("cy", "0"))
        child_width = int(child_ext.get("cx", "0"))
        child_height = int(child_ext.get("cy", "0"))
        if child_width and child_height and (width != child_width or height != child_height):
            issues.append(
                Issue("error", "scaled-text-group", "text-bearing group applies a scale transform", slide, shape_name)
            )


def _find_font_files() -> set[str]:
    roots: list[Path] = []
    if os.name == "nt":
        windir = Path(os.environ.get("WINDIR", r"C:\Windows"))
        roots.append(windir / "Fonts")
        local = os.environ.get("LOCALAPPDATA")
        if local:
            roots.append(Path(local) / "Microsoft" / "Windows" / "Fonts")
    elif platform.system() == "Darwin":
        roots.extend([Path("/System/Library/Fonts"), Path("/Library/Fonts"), Path.home() / "Library" / "Fonts"])
    else:
        roots.extend([Path("/usr/share/fonts"), Path("/usr/local/share/fonts"), Path.home() / ".fonts"])

    names: set[str] = set()
    for root in roots:
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if path.suffix.lower() in {".ttf", ".otf", ".ttc"}:
                names.add(re.sub(r"[^a-z0-9]", "", path.stem.lower()))
                names.add(re.sub(r"[^a-z0-9]", "", path.name.lower()))
    return names


def _font_available(font: str, files: set[str]) -> bool:
    aliases = {
        "simhei": {"simhei", "simheittf"},
        "arial": {"arial", "arialttf", "arialbd", "arialn"},
        "timesnewroman": {"times", "timesnewroman", "timesnewromanttf", "timesnewromanpsmt"},
    }
    normalized = re.sub(r"[^a-z0-9]", "", font.lower())
    candidates = aliases.get(normalized, {normalized})
    return any(any(item.startswith(candidate) for item in files) for candidate in candidates)


def _export_pdf_powerpoint(pptx: Path, pdf: Path) -> str | None:
    if os.name != "nt":
        return None
    errors: list[str] = []
    try:
        import win32com.client  # type: ignore

        app = win32com.client.DispatchEx("PowerPoint.Application")
        app.Visible = 0
        presentation = None
        try:
            presentation = app.Presentations.Open(str(pptx), WithWindow=False)
            presentation.SaveAs(str(pdf), 32)
        finally:
            if presentation is not None:
                presentation.Close()
            # PowerPoint can be a shared single-process application. Close only
            # the presentation opened for this export; never quit the app.
        if pdf.is_file():
            return "Microsoft PowerPoint (win32com)"
    except Exception as exc:  # pragma: no cover - machine dependent
        errors.append(str(exc))

    try:
        import comtypes.client  # type: ignore

        app = comtypes.client.CreateObject("PowerPoint.Application")
        presentation = None
        try:
            presentation = app.Presentations.Open(str(pptx), WithWindow=False)
            presentation.SaveAs(str(pdf), 32)
        finally:
            if presentation is not None:
                presentation.Close()
            # See the win32com path: leaving the application running protects
            # presentations that a user may have open in the same process.
        if pdf.is_file():
            return "Microsoft PowerPoint (comtypes)"
    except Exception as exc:  # pragma: no cover - machine dependent
        errors.append(str(exc))

    powershell = shutil.which("pwsh") or shutil.which("powershell")
    if powershell:
        script = (
            "$ErrorActionPreference='Stop'; "
            "$pptx=$env:SUPER_SIMPLE_SCI_PPT_PPTX; $pdf=$env:SUPER_SIMPLE_SCI_PPT_PDF; "
            "$app=New-Object -ComObject PowerPoint.Application; $deck=$null; "
            "try { $deck=$app.Presentations.Open($pptx,$true,$false,$false); "
            "$deck.SaveAs($pdf,32) } finally { "
            "if($null -ne $deck){$deck.Close()} }"
        )
        try:
            env = os.environ.copy()
            env["SUPER_SIMPLE_SCI_PPT_PPTX"] = str(pptx)
            env["SUPER_SIMPLE_SCI_PPT_PDF"] = str(pdf)
            completed = subprocess.run(
                [powershell, "-NoProfile", "-NonInteractive", "-Command", script],
                capture_output=True,
                text=True,
                timeout=180,
                env=env,
            )
            if completed.returncode == 0 and pdf.is_file():
                return f"Microsoft PowerPoint ({Path(powershell).name} COM)"
            errors.append((completed.stderr or completed.stdout or "PowerShell COM export failed").strip())
        except Exception as exc:  # pragma: no cover - machine dependent
            errors.append(str(exc))
    return None


def _export_pdf_libreoffice(pptx: Path, pdf: Path) -> str | None:
    binary = shutil.which("soffice") or shutil.which("libreoffice")
    if not binary:
        return None
    with tempfile.TemporaryDirectory(prefix="super-simple-sci-ppt-") as tmp:
        temp_dir = Path(tmp)
        command = [
            binary,
            "--headless",
            "--convert-to",
            "pdf",
            "--outdir",
            str(temp_dir),
            str(pptx),
        ]
        completed = subprocess.run(command, capture_output=True, text=True, timeout=180)
        produced = temp_dir / f"{pptx.stem}.pdf"
        if completed.returncode != 0 or not produced.is_file():
            raise RuntimeError(
                "LibreOffice PDF export failed: " + (completed.stderr or completed.stdout or "unknown error").strip()
            )
        shutil.copy2(produced, pdf)
    return f"LibreOffice ({Path(binary).name})"


def export_pdf(pptx: Path, pdf: Path) -> str:
    pdf.parent.mkdir(parents=True, exist_ok=True)
    if pdf.exists():
        pdf.unlink()
    tool = _export_pdf_powerpoint(pptx, pdf)
    if tool:
        return tool
    tool = _export_pdf_libreoffice(pptx, pdf)
    if tool:
        return tool
    raise RuntimeError(
        "No supported PPTX-to-PDF exporter is available. Install Microsoft PowerPoint on Windows or LibreOffice."
    )


def _executable_candidates(name: str) -> list[str]:
    candidates: list[Path] = []
    suffixes = [".exe", "", ".cmd", ".bat"] if os.name == "nt" else [""]
    for directory in os.environ.get("PATH", "").split(os.pathsep):
        if not directory:
            continue
        root = Path(directory.strip('"'))
        for suffix in suffixes:
            candidate = root / f"{name}{suffix}"
            if candidate.is_file():
                candidates.append(candidate)
    resolved = shutil.which(name)
    if resolved:
        candidates.append(Path(resolved))
    unique: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate.resolve()).casefold()
        if key not in seen:
            seen.add(key)
            unique.append(str(candidate.resolve()))
    return unique


def render_pdf(pdf: Path, slides_dir: Path, dpi: int = 144) -> list[Path]:
    slides_dir.mkdir(parents=True, exist_ok=True)
    for existing in slides_dir.glob("slide-*.png"):
        existing.unlink()
    try:
        import fitz  # type: ignore

        document = fitz.open(pdf)
        matrix = fitz.Matrix(dpi / 72.0, dpi / 72.0)
        paths: list[Path] = []
        for index, page in enumerate(document, start=1):
            output = slides_dir / f"slide-{index:02d}.png"
            page.get_pixmap(matrix=matrix, alpha=False).save(output)
            paths.append(output)
        document.close()
        return paths
    except ImportError:
        pass

    binaries = _executable_candidates("pdftoppm")
    if not binaries:
        raise RuntimeError("Rendering requires PyMuPDF or pdftoppm; neither is available")
    prefix = slides_dir / "slide"
    errors: list[str] = []
    for binary in binaries:
        completed = subprocess.run(
            [binary, "-png", "-r", str(dpi), str(pdf), str(prefix)],
            capture_output=True,
            text=True,
            timeout=180,
        )
        if completed.returncode == 0 and list(slides_dir.glob("slide-*.png")):
            break
        errors.append(f"{binary}: {(completed.stderr or completed.stdout or 'failed').strip()}")
    else:
        raise RuntimeError("pdftoppm failed for every discovered executable: " + " | ".join(errors))
    produced = sorted(
        slides_dir.glob("slide-*.png"),
        key=lambda item: int(re.search(r"(\d+)$", item.stem).group(1)),
    )
    renamed: list[Path] = []
    for index, item in enumerate(produced, start=1):
        target = slides_dir / f"slide-{index:02d}.png"
        if item != target:
            item.replace(target)
        renamed.append(target)
    return renamed


def create_montage(images: list[Path], output: Path) -> None:
    from PIL import Image, ImageOps

    opened = [Image.open(path).convert("RGB") for path in images]
    thumb_width = 640
    thumbs = []
    for image in opened:
        ratio = thumb_width / image.width
        thumb = image.resize((thumb_width, round(image.height * ratio)))
        thumbs.append(ImageOps.expand(thumb, border=2, fill="#C8C8C8"))
    columns = 2 if len(thumbs) > 1 else 1
    rows = (len(thumbs) + columns - 1) // columns
    cell_w = max(image.width for image in thumbs)
    cell_h = max(image.height for image in thumbs)
    canvas = Image.new("RGB", (columns * cell_w, rows * cell_h), "white")
    for index, image in enumerate(thumbs):
        canvas.paste(image, ((index % columns) * cell_w, (index // columns) * cell_h))
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output)
    for image in opened:
        image.close()


def mechanical_check(pptx: Path) -> tuple[int, list[Issue], dict[str, Any]]:
    issues: list[Issue] = []
    slide_summaries: list[dict[str, Any]] = []
    with zipfile.ZipFile(pptx) as archive:
        presentation = ET.fromstring(archive.read("ppt/presentation.xml"))
        size = presentation.find("p:sldSz", NS)
        if size is None:
            raise ValueError("presentation slide size is missing")
        width = int(size.get("cx", "0"))
        height = int(size.get("cy", "0"))
        names = ordered_slide_parts(archive)
        tolerance = 1000
        for slide_index, name in enumerate(names, start=1):
            root = ET.fromstring(archive.read(name))
            _check_scaled_text_groups(root, slide_index, issues)
            boxes: list[tuple[int, int, int, int, str, str]] = []
            minimum_pt: float | None = None
            unknown_font_size = False
            empty_textboxes = 0
            for element in root.findall(".//p:sp", NS) + root.findall(".//p:graphicFrame", NS) + root.findall(".//p:pic", NS):
                c_nv_pr = element.find(".//p:cNvPr", NS)
                shape_name = c_nv_pr.get("name", "") if c_nv_pr is not None else ""
                text = "".join(node.text or "" for node in element.findall(".//a:t", NS)).strip()
                bounds = _shape_bounds(element)
                x = y = cx = cy = None
                if bounds is not None:
                    x, y, cx, cy = bounds
                    if x < -tolerance or y < -tolerance or x + cx > width + tolerance or y + cy > height + tolerance:
                        issues.append(Issue("error", "out-of-slide", "object extends beyond the slide canvas", slide_index, shape_name))
                    boxes.append((x, y, cx, cy, shape_name, text))

                tx_body = element.find("p:txBody", NS)
                if tx_body is not None and not text:
                    empty_textboxes += 1
                if not text:
                    continue

                role = _shape_role(element, shape_name, y, height)
                target_pt = _target_pt(role)
                paragraphs = _paragraph_font_records(element)
                if not paragraphs:
                    unknown_font_size = True
                    continue
                for paragraph in paragraphs:
                    for record_index, record in enumerate(paragraph):
                        size = record["size"]
                        baseline = record["baseline"]
                        if not isinstance(size, float):
                            unknown_font_size = True
                            continue
                        minimum_pt = size if minimum_pt is None else min(minimum_pt, size)
                        if baseline == 0 and abs(size - target_pt) - FONT_SIZE_TOLERANCE_PT > 1e-9:
                            code = f"{role}-font-size-mismatch"
                            issues.append(
                                Issue(
                                    "error",
                                    code,
                                    f"{role} text is {size:g} pt; required fixed size is {target_pt:g} pt "
                                    f"(tolerance {FONT_SIZE_TOLERANCE_PT:g} pt)",
                                    slide_index,
                                    shape_name,
                                )
                            )
                        if baseline != 0:
                            ratio = size / target_pt
                            first_level_normal = SUBSUPER_MIN_RATIO <= ratio <= SUBSUPER_MAX_RATIO
                            nested_normal = _is_normal_nested_subscript(paragraph, record_index, target_pt)
                            if not first_level_normal and not nested_normal:
                                issues.append(
                                    Issue(
                                        "error",
                                        "subsuper-not-normal-scale",
                                        f"subscript/superscript is {ratio:.2f}× the {role} baseline of {target_pt:g} pt; "
                                        "a 49% run is allowed only as a verified nested 70% subscript",
                                        slide_index,
                                        shape_name,
                                    )
                                )
                        spacing = record["spacing"]
                        if isinstance(spacing, int) and spacing < 0:
                            issues.append(
                                Issue("error", "negative-letter-spacing", "text uses negative character spacing", slide_index, shape_name)
                            )
                        color = record["color"]
                        if isinstance(color, str) and color and color != "000000":
                            issues.append(
                                Issue("error", "non-black-text", f"explicit text color is #{color}", slide_index, shape_name)
                            )

                if tx_body is not None:
                    body_properties = tx_body.find("./a:bodyPr", NS)
                    if body_properties is not None and body_properties.find("./a:normAutofit", NS) is not None:
                        issues.append(
                            Issue("error", "auto-fit-shrink", "text body uses normal auto-fit shrinking", slide_index, shape_name)
                        )

            seen: dict[tuple[int, int, int, int, str], str] = {}
            for x, y, cx, cy, shape_name, text in boxes:
                key = (x, y, cx, cy, re.sub(r"\s+", " ", text))
                if text and key in seen:
                    issues.append(Issue("warning", "duplicate-object", f"duplicates {seen[key]}", slide_index, shape_name))
                else:
                    seen[key] = shape_name
            if empty_textboxes:
                issues.append(Issue("warning", "empty-textbox", f"{empty_textboxes} empty text object(s)", slide_index))
            if unknown_font_size:
                issues.append(Issue("error", "font-size-inherited", "some visible text has no explicit run size", slide_index))
            slide_summaries.append(
                {
                    "slide": slide_index,
                    "slide_part": name,
                    "objects_with_bounds": len(boxes),
                    "empty_textboxes": empty_textboxes,
                    "minimum_explicit_font_pt": minimum_pt,
                }
            )
    return len(names), issues, {"slide_width_emu": width, "slide_height_emu": height, "slides": slide_summaries}


REVIEW_CHECKS = (
    "text_and_fonts", "images_and_crops", "alignment_and_whitespace",
    "formulae_and_symbols", "scientific_match",
)


def write_review_template(pptx_hash: str, images: list[Path], path: Path) -> None:
    payload = {
        "pptx_sha256": pptx_hash,
        "instructions": "Inspect the montage and every full-size PNG. Set every slide status to passed only after all listed checks are satisfactory.",
        "slides": [
            {
                "slide": index,
                "image": image.name,
                "image_sha256": sha256_file(image),
                "status": "pending",
                "checks": {name: "pending" for name in REVIEW_CHECKS},
                "notes": "",
            }
            for index, image in enumerate(images, start=1)
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def validate_review(path: Path, pptx_hash: str, images: list[Path]) -> tuple[bool, list[str]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    failures: list[str] = []
    if not isinstance(data, dict):
        return False, ["review must be a JSON object"]
    if data.get("pptx_sha256") != pptx_hash:
        failures.append("PPTX hash does not match the reviewed deck")
    slides = data.get("slides")
    if not isinstance(slides, list) or len(slides) != len(images):
        failures.append("review slide count does not match rendered slide count")
        return False, failures
    for index, (record, image) in enumerate(zip(slides, images), start=1):
        if not isinstance(record, dict):
            failures.append(f"slide {index}: review record must be an object")
            continue
        if record.get("slide") != index:
            failures.append(f"slide {index}: review order mismatch")
        if record.get("image_sha256") != sha256_file(image):
            failures.append(f"slide {index}: rendered image hash mismatch")
        if record.get("status") != "passed":
            failures.append(f"slide {index}: status is not passed")
        checks = record.get("checks", {})
        if (not isinstance(checks, dict)
                or any(checks.get(name) != "passed" for name in REVIEW_CHECKS)
                or any(value != "passed" for value in checks.values())):
            failures.append(f"slide {index}: one or more visual checks are not passed")
        if not str(record.get("notes", "")).strip():
            failures.append(f"slide {index}: review notes are empty")
    return not failures, failures


def write_markdown(report: dict[str, Any], path: Path) -> None:
    lines = [
        "# Render And Check",
        "",
        f"- status: {report['status']}",
        f"- slides: {report['slide_count']}",
        f"- PDF exporter: {report['pdf_exporter']}",
        f"- errors: {report['errors']}",
        f"- warnings: {report['warnings']}",
        f"- visual review: {report['visual_review_status']}",
        "",
        "## Issues",
        "",
    ]
    if not report["issues"]:
        lines.append("No deterministic mechanical issues.")
    else:
        for item in report["issues"]:
            where = f" slide {item['slide']}" if item.get("slide") else ""
            shape = f"; shape={item['shape']}" if item.get("shape") else ""
            lines.append(f"- [{item['severity']}]`{item['code']}`{where}{shape}: {item['message']}")
    if report.get("review_failures"):
        lines.extend(["", "## Review failures", ""])
        lines.extend(f"- {message}" for message in report["review_failures"])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Render every PPTX slide and validate mechanical plus hash-bound visual QA.")
    parser.add_argument("pptx", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--review", type=Path, help="completed visual-review.json bound to current render hashes")
    parser.add_argument(
        "--required-font",
        action="append",
        default=None,
        help="required installed font; repeat as needed (default: SimHei, Arial, Times New Roman)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    pptx = args.pptx.resolve()
    output = args.output_dir.resolve()
    if not pptx.is_file() or pptx.suffix.lower() != ".pptx":
        print(f"ERROR: PPTX not found: {pptx}", file=sys.stderr)
        return 1
    output.mkdir(parents=True, exist_ok=True)
    issues: list[Issue] = []
    review_failures: list[str] = []
    required_fonts = args.required_font or ["SimHei", "Arial", "Times New Roman"]

    try:
        font_files = _find_font_files()
        for font in required_fonts:
            if not _font_available(font, font_files):
                issues.append(Issue("error", "missing-font", f"required font is not installed: {font}"))

        slide_count, mechanical_issues, mechanical = mechanical_check(pptx)
        issues.extend(mechanical_issues)
        pdf = output / f"{pptx.stem}.pdf"
        exporter = export_pdf(pptx, pdf)
        images = render_pdf(pdf, output / "slides")
        if len(images) != slide_count:
            issues.append(
                Issue("error", "slide-count-mismatch", f"PPTX has {slide_count} slides but PDF render has {len(images)} pages")
            )
        create_montage(images, output / "montage.png")

        pptx_hash = sha256_file(pptx)
        review_template = output / "visual-review.json"
        if args.review:
            review_ok, review_failures = validate_review(args.review.resolve(), pptx_hash, images)
            visual_status = "passed" if review_ok else "failed"
        else:
            write_review_template(pptx_hash, images, review_template)
            review_ok = False
            visual_status = "pending"

        errors = sum(item.severity == "error" for item in issues)
        warnings = sum(item.severity == "warning" for item in issues)
        status = "passed" if errors == 0 and (not args.review or review_ok) else "failed"
        if not args.review and errors == 0:
            status = "rendered-pending-review"
        report = {
            "status": status,
            "pptx": str(pptx),
            "pptx_sha256": pptx_hash,
            "pdf": str(pdf),
            "pdf_sha256": sha256_file(pdf),
            "pdf_exporter": exporter,
            "slide_count": slide_count,
            "rendered_images": [str(path) for path in images],
            "rendered_image_sha256": {path.name: sha256_file(path) for path in images},
            "montage": str(output / "montage.png"),
            "visual_review_status": visual_status,
            "review_file": str((args.review or review_template).resolve()),
            "review_failures": review_failures,
            "errors": errors,
            "warnings": warnings,
            "issues": [asdict(item) for item in issues],
            "mechanical": mechanical,
            "required_fonts": required_fonts,
        }
        (output / "render-check.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        write_markdown(report, output / "render-check.md")
    except (OSError, RuntimeError, ValueError, zipfile.BadZipFile, ET.ParseError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"Render check: {report['status']}")
    print(f"Slides: {report['slide_count']}  Errors: {report['errors']}  Warnings: {report['warnings']}")
    print(f"Montage: {report['montage']}")
    if not args.review and report["errors"] == 0:
        print(f"Complete and validate: {review_template}")
    return 0 if report["status"] != "failed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
