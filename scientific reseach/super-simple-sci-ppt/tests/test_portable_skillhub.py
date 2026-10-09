from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch


PUBLIC_PACKAGE = Path(__file__).resolve().parents[1]
PUBLIC_SCRIPTS = PUBLIC_PACKAGE / "scripts"


def load_module(name: str, path: Path, *, dependencies: dict[str, object] | None = None):
    """Load a public script without importing private skill modules."""

    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    previous: dict[str, object] = {}
    previous[name] = sys.modules.get(name)
    sys.modules[name] = module
    if dependencies:
        for dep_name, dep_module in dependencies.items():
            previous[dep_name] = sys.modules.get(dep_name)
            sys.modules[dep_name] = dep_module
    try:
        spec.loader.exec_module(module)
    finally:
        if dependencies:
            for dep_name, previous_module in previous.items():
                if dep_name == name:
                    continue
                if previous_module is None:
                    sys.modules.pop(dep_name, None)
                else:
                    sys.modules[dep_name] = previous_module
        if previous[name] is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = previous[name]
    return module


runtime = load_module("public_skill_runtime", PUBLIC_SCRIPTS / "skill_runtime.py")
workflow = load_module("public_select_workflow", PUBLIC_SCRIPTS / "select_workflow.py")
payload = load_module("public_visible_payload", PUBLIC_SCRIPTS / "visible_payload.py")
slide_order = load_module("public_pptx_slide_order", PUBLIC_SCRIPTS / "pptx_slide_order.py")
render = load_module(
    "public_render_and_check",
    PUBLIC_SCRIPTS / "render_and_check.py",
    dependencies={"pptx_slide_order": slide_order},
)
manifest = load_module(
    "public_project_manifest",
    PUBLIC_SCRIPTS / "project_manifest.py",
    dependencies={"skill_runtime": runtime},
)


class PortableRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.package = self.root / "copied-skill"
        shutil.copytree(PUBLIC_PACKAGE, self.package)

    def test_copied_package_runs_from_unrelated_cwd_without_global_state(self) -> None:
        unrelated = self.root / "unrelated"
        unrelated.mkdir()
        environment = os.environ.copy()
        environment["CODEX_HOME"] = ""
        completed = subprocess.run(
            [sys.executable, str(self.package / "scripts" / "skill_runtime.py")],
            cwd=unrelated,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)
        report = json.loads(completed.stdout)
        self.assertEqual(report["status"], "passed")
        self.assertIsInstance(report["project_skill_sha256"], str)
        self.assertEqual(report["project_skill_sha256"], report["skill_sha256"])
        self.assertNotIn("installed_skill_sha256", report)
        self.assertNotIn("source", report)
        self.assertNotIn("installed", report)

    def test_missing_bundle_item_and_broken_relative_link_are_invalid(self) -> None:
        required_file = self.package / "references" / "validation.md"
        required_file.unlink()
        report = runtime.preflight(self.package)
        self.assertEqual(report["status"], "invalid")
        self.assertIn("references/validation.md", report["reason"])

        shutil.copy2(PUBLIC_PACKAGE / "references" / "validation.md", required_file)
        readme = self.package / "README.md"
        readme.write_text(readme.read_text(encoding="utf-8") + "\n[broken](missing-local.md)\n", encoding="utf-8")
        report = runtime.preflight(self.package)
        self.assertEqual(report["status"], "invalid")
        self.assertIn("missing-local.md", report["reason"])

        readme.write_text(readme.read_text(encoding="utf-8") + "\n[absolute](C:/outside.md)\n", encoding="utf-8")
        report = runtime.preflight(self.package)
        self.assertEqual(report["status"], "invalid")
        self.assertIn("C:/outside.md", report["reason"])

    def test_fingerprint_changes_with_content_but_ignores_caches_and_receipt(self) -> None:
        first = runtime.preflight(self.package)
        self.assertEqual(first["status"], "passed", first)
        fingerprint = first["project_skill_sha256"]
        (self.package / "__pycache__").mkdir()
        (self.package / "__pycache__" / "ignored.pyc").write_bytes(b"cache")
        (self.package / runtime.INSTALLATION_NAME).write_text("receipt", encoding="utf-8")
        self.assertEqual(runtime.tree_sha256(self.package), fingerprint)
        readme = self.package / "README.md"
        readme.write_bytes(readme.read_bytes() + b"\ncontent changed\n")
        second = runtime.preflight(self.package)
        self.assertEqual(second["status"], "passed")
        self.assertNotEqual(second["project_skill_sha256"], fingerprint)

    def test_symlink_file_or_directory_is_rejected_when_supported(self) -> None:
        if os.name == "nt" and callable(getattr(Path, "is_junction", None)):
            junction = self.package / "linked-junction"
            completed = subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(junction), str(self.package / "assets")],
                capture_output=True,
                text=True,
                check=False,
            )
            if completed.returncode == 0:
                self.addCleanup(lambda: junction.unlink(missing_ok=True))
                report = runtime.preflight(self.package)
                self.assertEqual(report["status"], "invalid")
                self.assertIn("junction", report["reason"])
                return
        target = self.package / "linked-directory"
        try:
            target.symlink_to(self.package / "assets", target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symbolic links are unavailable on this Windows host")
        report = runtime.preflight(self.package)
        self.assertEqual(report["status"], "invalid")
        self.assertIn("symbolic link", report["reason"])

    def test_symlinked_package_root_is_rejected_when_supported(self) -> None:
        alias = self.root / "package-link"
        try:
            alias.symlink_to(self.package, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symbolic links are unavailable on this Windows host")
        report = runtime.preflight(alias)
        self.assertEqual(report["status"], "invalid")
        self.assertIn("symbolic link", report["reason"])


class PortableWorkflowTests(unittest.TestCase):
    def test_format_routing_and_source_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pptx = root / "deck.pptx"
            pptx.write_bytes(b"pptx")
            ppt = root / "legacy.ppt"
            ppt.write_bytes(b"ppt")
            beamer = root / "deck.tex"
            beamer.write_text("\\documentclass [aspectratio=169] { \n beamer }", encoding="utf-8")
            article = root / "article.tex"
            article.write_text("% \\documentclass{beamer}\n\\documentclass{article}", encoding="utf-8")
            pdf = root / "deck.pdf"
            pdf.write_bytes(b"pdf")

            self.assertEqual(workflow.select_format(existing=pptx), "pptx")
            self.assertEqual(workflow.select_format(existing=ppt), "pptx")
            self.assertEqual(workflow.select_format(existing=beamer), "beamer")
            self.assertEqual(workflow.select_format("pptx", existing=pptx), "pptx")
            self.assertEqual(workflow.select_format("beamer", existing=pptx), "beamer")
            self.assertEqual(workflow.select_format("pptx", existing=pdf), "pptx")
            with self.assertRaises(ValueError):
                workflow.select_format(existing=article)
            with self.assertRaises(ValueError):
                workflow.select_format("pptx", existing=article)
            with self.assertRaises(ValueError):
                workflow.select_format(existing=pdf)
            with self.assertRaises(ValueError):
                workflow.select_format("pptx", existing=root / "missing.pptx")

        self.assertEqual(workflow.select_format(), "pptx")


class PortableManifestTests(unittest.TestCase):
    def test_template_prefix_supports_public_runtime_alias(self) -> None:
        self.assertEqual(
            manifest.template_version_from_runtime({"project_skill_sha256": "abc"}),
            "super-simple-sci-ppt:sha256:abc",
        )
        self.assertEqual(
            manifest.template_version_from_runtime({"skill_sha256": "abc"}),
            "super-simple-sci-ppt:sha256:abc",
        )

    def test_repeated_init_preserves_lineage_and_conflicts_do_not_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "talk"
            first = manifest.init_project(
                project,
                format="beamer",
                source_entries=["entry-1"],
                template_version="super-simple-sci-ppt:sha256:old",
            )
            before = (project / "project.json").read_bytes()
            repeated = manifest.init_project(project)
            self.assertEqual(repeated, first)
            self.assertEqual((project / "project.json").read_bytes(), before)
            with self.assertRaises(manifest.ProjectManifestConflictError):
                manifest.init_project(project, format="pptx")
            self.assertEqual((project / "project.json").read_bytes(), before)

    def test_cli_existing_source_requires_real_file_and_uses_inherited_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.tex"
            source.write_text("\\documentclass{beamer}\n", encoding="utf-8")
            project = root / "project"
            with patch.object(manifest, "require_current", return_value={"project_skill_sha256": "skill"}), patch.dict(
                sys.modules, {"select_workflow": workflow}
            ):
                self.assertEqual(manifest.cli_main([str(project), "--existing", str(source)]), 0)
                missing = manifest.cli_main([str(root / "missing-project"), "--existing", str(root / "none.pptx")])
            self.assertEqual(missing, 2)
            value = json.loads((project / "project.json").read_text(encoding="utf-8"))
            self.assertEqual(value["format"], "beamer")
            self.assertTrue(value["template_version"].startswith("inherited-source:sha256:"))


class PortablePayloadAndValidationTests(unittest.TestCase):
    def test_speaker_notes_remain_opt_in_and_script_stays_separate(self) -> None:
        source = {
            "slides": [
                {
                    "visible_title": "结果",
                    "speaker_notes": "页面备注",
                    "speaker_script": "独立讲稿",
                    "internal_source": "private",
                }
            ]
        }
        default = payload.sanitize_payload(source)["slides"][0]
        self.assertNotIn("speaker_notes", default)
        self.assertEqual(default["speaker_script"], "独立讲稿")
        explicit = payload.sanitize_payload(source, include_speaker_notes=True)["slides"][0]
        self.assertEqual(explicit["speaker_notes"], "页面备注")

    def test_relationship_order_and_hash_bound_visual_review(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            deck = root / "reversed.pptx"
            _write_synthetic_pptx(deck)
            with zipfile.ZipFile(deck) as archive:
                self.assertEqual(
                    slide_order.ordered_slide_parts(archive),
                    ["ppt/slides/slide2.xml", "ppt/slides/slide1.xml"],
                )

            images = []
            for index in (1, 2):
                image = root / f"slide-{index}.png"
                image.write_bytes(f"image-{index}".encode())
                images.append(image)
            review = root / "visual-review.json"
            render.write_review_template("deck-hash", images, review)
            record = json.loads(review.read_text(encoding="utf-8"))
            incomplete = json.loads(json.dumps(record))
            for slide in incomplete["slides"]:
                slide["status"] = "passed"
                slide["checks"] = {}
                slide["notes"] = "逐页核验完成"
            review.write_text(json.dumps(incomplete, ensure_ascii=False), encoding="utf-8")
            self.assertFalse(render.validate_review(review, "deck-hash", images)[0])
            for slide in record["slides"]:
                slide["status"] = "passed"
                slide["checks"] = {key: "passed" for key in slide["checks"]}
                slide["notes"] = "逐页核验完成"
            review.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
            self.assertEqual(render.validate_review(review, "deck-hash", images), (True, []))
            self.assertFalse(render.validate_review(review, "changed-deck-hash", images)[0])
            images[0].write_bytes(b"changed-image")
            self.assertFalse(render.validate_review(review, "deck-hash", images)[0])


def _write_synthetic_pptx(path: Path) -> None:
    presentation = """<?xml version="1.0" encoding="UTF-8"?>
<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
 <p:sldSz cx="12192000" cy="6858000"/>
 <p:sldIdLst><p:sldId id="256" r:id="rId2"/><p:sldId id="257" r:id="rId1"/></p:sldIdLst>
</p:presentation>"""
    relationships = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
 <Relationship Id="rId1" Target="slides/slide1.xml"/>
 <Relationship Id="rId2" Target="slides/slide2.xml"/>
</Relationships>"""
    slide = """<?xml version="1.0" encoding="UTF-8"?>
<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
 <p:cSld><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name="Group"/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>
 <p:grpSpPr/><p:sp><p:nvSpPr><p:cNvPr id="2" name="Title"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
 <p:spPr/><p:txBody><a:bodyPr xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"/>
 <a:lstStyle xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"/>
 <a:p xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><a:r><a:rPr sz="3200"/><a:t>{title}</a:t></a:r></a:p>
 </p:txBody></p:sp></p:spTree></p:cSld></p:sld>"""
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("ppt/presentation.xml", presentation)
        archive.writestr("ppt/_rels/presentation.xml.rels", relationships)
        archive.writestr("ppt/slides/slide1.xml", slide.format(title="First"))
        archive.writestr("ppt/slides/slide2.xml", slide.format(title="Second"))


if __name__ == "__main__":
    unittest.main()
