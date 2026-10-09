from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import init_coding_project as initializer  # noqa: E402
import inspect_coding_project as inspector  # noqa: E402


def valid_spec() -> dict:
    return {
        "schema_version": 1,
        "project_name": "示例项目",
        "project_slug": "example-project",
        "summary": "提供一个可验证的示例服务",
        "documentation_language": "zh-CN",
        "project_types": ["service", "cli"],
        "problem": "当前流程缺少稳定接口",
        "target_users": ["内部开发者"],
        "goals": [
            {
                "id": "G1",
                "description": "交付端到端接口",
                "success_criteria": ["接口测试通过"],
            }
        ],
        "scope": {"in": ["健康检查"], "out": ["公网部署"]},
        "stack": {
            "languages": ["Python"],
            "runtimes": ["Python 3.12"],
            "frameworks": [],
            "package_manager": "uv",
            "evidence": ["用户确认"],
        },
        "architecture": {
            "style": "modular service",
            "modules": ["application core"],
            "external_dependencies": [],
            "pending_decisions": [],
        },
        "quality": {
            "commands": {
                "setup": "uv sync",
                "dev": None,
                "test": "uv run pytest",
                "lint": "uv run ruff check .",
                "typecheck": None,
                "build": None,
            },
            "testing_strategy": "通过外部接口验证行为",
            "test_seams": ["CLI interface"],
            "ci_required": ["test", "lint"],
            "non_functional_requirements": [],
            "definition_of_done": ["验收标准通过"],
        },
        "deliverables": ["可运行服务"],
        "constraints": [],
        "milestones": [],
        "risks": [],
        "documentation": {
            "reports": True,
            "presentations": True,
            "assets": True,
            "deliverables": True,
        },
        "agent_instructions": {"create_agents_md": True},
        "scaffold": {
            "directories": ["src/example", "tests"],
            "planned_commands": [
                {
                    "command": "touch should-not-exist",
                    "purpose": "证明命令只被记录",
                    "status": "proposed",
                }
            ],
        },
        "external_operations": {
            "web_research_approved": False,
            "issue_tracker_sync": "disabled",
            "remote_repository": "disabled",
        },
        "assumptions": [],
        "open_questions": [],
    }


class InitializerTests(unittest.TestCase):
    def write_spec(self, directory: Path, spec: dict | None = None) -> Path:
        path = directory / "spec.json"
        path.write_text(json.dumps(spec or valid_spec(), ensure_ascii=False), encoding="utf-8")
        return path

    def test_load_spec_rejects_path_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            spec = valid_spec()
            spec["scaffold"]["directories"] = ["../escape"]
            path = self.write_spec(directory, spec)
            with self.assertRaisesRegex(ValueError, "unsafe path segment"):
                initializer.load_spec(path)

    def test_load_spec_rejects_non_string_project_type(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            spec = valid_spec()
            spec["project_types"] = [{"type": "service"}]
            path = self.write_spec(directory, spec)
            with self.assertRaisesRegex(ValueError, "entries must be strings"):
                initializer.load_spec(path)

    def test_user_content_that_looks_like_a_placeholder_is_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            spec = valid_spec()
            spec["problem"] = "需要保留配置示例 {{TOKEN}}"
            loaded = initializer.load_spec(self.write_spec(directory, spec))
            context_file = next(
                item for item in initializer.build_files(loaded) if item.relative_path == "PROJECT_CONTEXT.md"
            )
            self.assertIn("{{TOKEN}}", context_file.content)

    def test_dry_run_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            spec_path = self.write_spec(directory)
            root = directory / "new-project"
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "init_coding_project.py"),
                    "--root",
                    str(root),
                    "--spec",
                    str(spec_path),
                    "--dry-run",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(root.exists())
            self.assertIn("overwrite=0", result.stdout)
            self.assertIn("Dry run complete", result.stdout)

    def test_apply_preserves_existing_files_and_never_executes_commands(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            spec_path = self.write_spec(directory)
            spec = initializer.load_spec(spec_path)
            root = directory / "project"
            root.mkdir()
            readme = root / "README.md"
            readme.write_bytes(b"user-owned\n")

            directories = initializer.build_directories(spec)
            files = initializer.build_files(spec)
            initializer.apply_plan(root, directories, files)

            self.assertEqual(readme.read_bytes(), b"user-owned\n")
            self.assertTrue((root / "PROJECT_CONTEXT.md").is_file())
            self.assertTrue((root / "AGENTS.md").is_file())
            self.assertTrue((root / "docs/reports").is_dir())
            self.assertTrue((root / "docs/presentations").is_dir())
            self.assertTrue((root / "assets").is_dir())
            self.assertTrue((root / "deliverables").is_dir())
            self.assertTrue((root / "src/example").is_dir())
            self.assertFalse((root / "should-not-exist").exists())
            plan = (root / "docs/plans/implementation_plan.md").read_text(encoding="utf-8")
            self.assertIn("touch should-not-exist", plan)

    def test_agents_file_can_be_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            spec = valid_spec()
            spec["agent_instructions"]["create_agents_md"] = False
            loaded = initializer.load_spec(self.write_spec(directory, spec))
            file_names = {item.relative_path for item in initializer.build_files(loaded)}
            self.assertNotIn("AGENTS.md", file_names)

    def test_git_init_is_rejected_during_dry_run(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "init_coding_project.py"),
                    "--root",
                    str(directory / "project"),
                    "--spec",
                    str(self.write_spec(directory)),
                    "--dry-run",
                    "--git-init",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("--git-init requires --apply", result.stderr)

    def test_existing_symlink_directory_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            outside = directory / "outside"
            outside.mkdir()
            root = directory / "project"
            root.mkdir()
            (root / "src").symlink_to(outside, target_is_directory=True)
            spec = initializer.load_spec(self.write_spec(directory))
            with self.assertRaisesRegex(ValueError, "symlink"):
                initializer.check_conflicts(
                    root,
                    initializer.build_directories(spec),
                    initializer.build_files(spec),
                )


class InspectorTests(unittest.TestCase):
    def test_detects_stack_monorepo_ci_and_commands_without_writing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "package.json").write_text(
                json.dumps(
                    {
                        "workspaces": ["packages/*"],
                        "scripts": {"test": "vitest", "lint": "eslint ."},
                    }
                ),
                encoding="utf-8",
            )
            (root / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
            (root / "src").mkdir()
            workflows = root / ".github" / "workflows"
            workflows.mkdir(parents=True)
            (workflows / "ci.yml").write_text("name: CI\n", encoding="utf-8")

            result = inspector.inspect(root)

            self.assertEqual(result["detected_ecosystems"], ["node"])
            self.assertEqual(result["detected_package_managers"], ["pnpm"])
            self.assertIn("package.json#workspaces", result["monorepo_markers"])
            self.assertIn(".github/workflows/ci.yml", result["ci_files"])
            self.assertEqual(result["quality_command_evidence"]["package_scripts"]["test"], "vitest")
            self.assertFalse(result["write_performed"])


if __name__ == "__main__":
    unittest.main()
