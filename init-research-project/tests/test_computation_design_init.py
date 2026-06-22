from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_ROOT / "scripts/init_research_project.py"
EXAMPLE = SKILL_ROOT / "assets/templates/project_spec.example.json"


def test_computational_init_creates_design_contract_and_handoffs(tmp_path: Path) -> None:
    spec = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    root = tmp_path / spec["project_slug"]
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(root), "--spec", str(EXAMPLE), "--apply"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    design_path = root / "docs/plans/calculation_design.json"
    design = json.loads(design_path.read_text(encoding="utf-8"))
    assert design["project_slug"] == spec["project_slug"]
    assert design["status"] == "draft"
    assert design["calculation_matrix"]
    assert (root / "docs/records/design_reviews").is_dir()
    assert (root / "docs/records/task_logs/project_log.md").is_file()
    assert (root / "docs/records/task_logs/daily").is_dir()
    assert list((root / "docs/records/task_logs/daily").glob("*.md"))
    task_log_rules = (root / "docs/records/task_logs/README.md").read_text(encoding="utf-8")
    assert "当日收尾" in task_log_rules
    readme = (root / "README.md").read_text(encoding="utf-8")
    context = (root / "PROJECT_CONTEXT.md").read_text(encoding="utf-8")
    assert "## 项目目标" in readme
    assert "## Project Structure / 项目结构" not in readme
    assert "## 科学问题" in context
    for name in ("AGENTS.md", "CLAUDE.md"):
        text = (root / name).read_text(encoding="utf-8")
        assert "computation-design" in text
        assert "vasp-workflow" in text
        assert "vasp-analysis" in text
        assert "vasp-work-manager" in text
        assert "daily/YYYY-MM-DD.md" in text
        assert "不要逐句中英双写" in text

    design_path.write_text('{"keep":"existing"}\n', encoding="utf-8")
    again = subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(root), "--spec", str(EXAMPLE), "--apply"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert again.returncode == 0
    assert design_path.read_text(encoding="utf-8") == '{"keep":"existing"}\n'
