from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PLUGIN = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN / "skills/research-teach/scripts"
HOOKS = PLUGIN / "hooks"
sys.path.insert(0, str(SCRIPTS))

from converter import (  # noqa: E402
    _formalize,
    configure_mineru,
    convert_document,
    load_mineru_env,
    quality_report,
)
from rtlib import (  # noqa: E402
    accept_proposal,
    build_graph,
    clean_cache,
    create_proposal,
    init_global,
    init_project,
    load_config,
    preview_proposal,
)


class ResearchTeachTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.context = self.base / "Global Vault/AgentContext"
        self.project = self.base / "project"
        init_global(self.context)
        init_project(self.project, self.context, topic="test topic")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def hook(
        self, name: str, payload: dict, env: dict[str, str] | None = None
    ) -> subprocess.CompletedProcess[str]:
        hook_env = os.environ.copy()
        if env:
            hook_env.update(env)
        return subprocess.run(
            [sys.executable, str(HOOKS / name)],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            check=False,
            env=hook_env,
        )

    def test_init_creates_private_project_link(self) -> None:
        root, config = load_config(self.project)
        self.assertEqual(root, self.project.resolve())
        self.assertEqual(config["topic"], "test topic")
        self.assertTrue((self.project / ".research/global").is_symlink())
        self.assertEqual((self.project / ".research/global").resolve(), self.context.resolve())
        gitignore = (self.project / ".gitignore").read_text(encoding="utf-8")
        self.assertIn(".research/global", gitignore)
        self.assertIn("papers/", gitignore)
        self.assertIn("knowledge/Learning/", gitignore)

    def test_proposal_requires_explicit_acceptance(self) -> None:
        proposal = create_proposal(
            "preferences.md",
            "Worked examples",
            "Use a worked example before abstraction.",
            "Confirmed in dialogue.",
            self.project,
        )
        before = (self.context / "preferences.md").read_text(encoding="utf-8")
        diff = preview_proposal(proposal, self.project)
        self.assertIn("+## Worked examples", diff)
        self.assertEqual((self.context / "preferences.md").read_text(encoding="utf-8"), before)
        result = accept_proposal(proposal, self.project)
        self.assertEqual(result["status"], "accepted")
        self.assertIn(
            "Use a worked example before abstraction.",
            (self.context / "preferences.md").read_text(encoding="utf-8"),
        )

    def test_graph_contains_explicit_relation(self) -> None:
        concepts = self.project / "knowledge/Concepts"
        (concepts / "Foundation.md").write_text(
            "---\nnode_type: concept\nstatus: verified\ntitle: Foundation\n---\n# Foundation\n",
            encoding="utf-8",
        )
        (concepts / "Advanced.md").write_text(
            "---\nnode_type: concept\nstatus: proposed\ntitle: Advanced\n---\n"
            "# Advanced\n\n## Relations\n"
            "- prerequisite -> [[Foundation]] | status: verified | evidence: [[Paper#p. 2]]\n",
            encoding="utf-8",
        )
        result = build_graph(self.project)
        self.assertGreaterEqual(result["nodes"], 2)
        data = json.loads((self.project / "dashboard/data.json").read_text(encoding="utf-8"))
        relation = next(edge for edge in data["edges"] if edge["relation"] == "prerequisite")
        self.assertEqual(relation["status"], "verified")
        self.assertTrue((self.project / "dashboard/index.html").is_file())

    def test_context_hook_only_loads_profile_for_research_intent(self) -> None:
        env = {
            "RESEARCH_TEACH_ENV_FILE": str(self.base / "missing-mineru.env"),
            "PLUGIN_DATA": str(self.base / "plugin-data"),
            "MINERU_API_TOKEN": "",
        }
        ordinary = self.hook(
            "research_context.py",
            {
                "hook_event_name": "UserPromptSubmit",
                "cwd": str(self.project),
                "prompt": "Fix this Python test.",
            },
            env,
        )
        self.assertEqual(ordinary.returncode, 0)
        self.assertEqual(ordinary.stdout, "")

        research = self.hook(
            "research_context.py",
            {
                "hook_event_name": "UserPromptSubmit",
                "cwd": str(self.project),
                "prompt": "帮我检索文献并构建知识图谱",
            },
            env,
        )
        payload = json.loads(research.stdout)
        context = payload["hookSpecificOutput"]["additionalContext"]
        self.assertIn("Use $research-teach", context)
        self.assertIn("Confirmed Learner Profile", context)
        self.assertIn("configure-mineru", context)

        dft = self.hook(
            "research_context.py",
            {
                "hook_event_name": "UserPromptSubmit",
                "cwd": str(self.project),
                "prompt": "检查这个 VASP SCF 任务的收敛性并教我怎么看",
            },
            env,
        )
        dft_payload = json.loads(dft.stdout)
        self.assertIn("Use $dote-tutor", dft_payload["hookSpecificOutput"]["additionalContext"])

    def test_first_start_reminds_once_when_mineru_is_missing(self) -> None:
        env = {
            "RESEARCH_TEACH_ENV_FILE": str(self.base / "missing-mineru.env"),
            "PLUGIN_DATA": str(self.base / "plugin-data"),
            "MINERU_API_TOKEN": "",
        }
        payload = {
            "hook_event_name": "SessionStart",
            "cwd": str(self.base),
            "source": "startup",
        }
        first = self.hook("research_context.py", payload, env)
        self.assertIn("configure-mineru", first.stdout)
        second = self.hook("research_context.py", payload, env)
        self.assertEqual(second.stdout, "")

    def test_configure_mineru_writes_private_env_file(self) -> None:
        env_file = self.base / "config/mineru.env"
        old_token = os.environ.pop("MINERU_API_TOKEN", None)
        old_file = os.environ.get("RESEARCH_TEACH_ENV_FILE")
        try:
            result = configure_mineru("test-token-123456", env_file=env_file)
            os.environ["RESEARCH_TEACH_ENV_FILE"] = str(env_file)
            values = load_mineru_env()
        finally:
            if old_token is not None:
                os.environ["MINERU_API_TOKEN"] = old_token
            if old_file is None:
                os.environ.pop("RESEARCH_TEACH_ENV_FILE", None)
            else:
                os.environ["RESEARCH_TEACH_ENV_FILE"] = old_file
        self.assertEqual(result["permissions"], "0o600")
        self.assertEqual(values["MINERU_API_TOKEN"], "test-token-123456")
        self.assertNotIn("test-token-123456", json.dumps(result))

    def test_guard_blocks_direct_global_write(self) -> None:
        blocked = self.hook(
            "global_guard.py",
            {
                "hook_event_name": "PreToolUse",
                "cwd": str(self.project),
                "tool_name": "apply_patch",
                "tool_input": {"command": "*** Update File: .research/global/profile.md"},
            },
        )
        decision = json.loads(blocked.stdout)["hookSpecificOutput"]
        self.assertEqual(decision["permissionDecision"], "deny")

        allowed = self.hook(
            "global_guard.py",
            {
                "hook_event_name": "PreToolUse",
                "cwd": str(self.project),
                "tool_name": "Bash",
                "tool_input": {
                    "command": "python3 research_teach.py accept-proposal .research/proposals/x.json"
                },
            },
        )
        self.assertEqual(allowed.stdout, "")

    def test_formal_conversion_separates_assets_and_cache(self) -> None:
        extraction = self.base / "extracted"
        extraction.mkdir()
        (extraction / "images").mkdir()
        (extraction / "images/figure.png").write_bytes(b"\x89PNG\r\n\x1a\n")
        (extraction / "full.md").write_text(
            "# Example\n\n" + ("Substantive scientific text. " * 35) + "\n\n![](images/figure.png)\n",
            encoding="utf-8",
        )
        report = quality_report(extraction)
        self.assertTrue(report["passed"])
        source = self.project / "papers/example.pdf"
        source.write_bytes(b"%PDF-1.4 test")
        root, config = load_config(self.project)
        formal = _formalize(
            source,
            extraction,
            {"engine": "test-engine", "version": "1"},
            "reference",
            root,
            config,
        )
        note = Path(formal["note"])
        self.assertTrue(note.is_file())
        self.assertIn("../../Assets/example/images/figure.png", note.read_text(encoding="utf-8"))
        self.assertTrue((self.project / "knowledge/Assets/example/images/figure.png").is_file())

    def test_markdown_ingestion_uses_local_direct_converter(self) -> None:
        source = self.project / "notes.md"
        source.write_text("# Notes\n\n" + ("Evidence-backed project text. " * 30), encoding="utf-8")
        result = convert_document(
            source,
            document_type="project_document",
            project=self.project,
        )
        self.assertEqual(result["engine"]["engine"], "direct-local")
        self.assertTrue(Path(result["formal"]["note"]).is_file())

    def test_cache_clean_preserves_formal_outputs(self) -> None:
        cache_file = self.project / ".research/cache/key/raw.bin"
        cache_file.parent.mkdir(parents=True)
        cache_file.write_bytes(b"cache")
        formal = self.project / "knowledge/Concepts/keep.md"
        formal.write_text("# Keep\n", encoding="utf-8")
        result = clean_cache(self.project)
        self.assertEqual(result["removed"], 1)
        self.assertFalse(cache_file.exists())
        self.assertTrue(formal.exists())


if __name__ == "__main__":
    unittest.main()
