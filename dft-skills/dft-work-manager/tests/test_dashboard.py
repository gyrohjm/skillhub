from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import vwm_dashboard  # noqa: E402
import vwm_ledger  # noqa: E402


def test_builds_dependency_free_dashboard(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.sqlite"
    vwm_ledger.init_db(ledger)
    with vwm_ledger.connect(ledger) as conn:
        vwm_ledger.register_task(
            conn, project="sic", task="bulk.scf", engine="vasp", task_type="scf"
        )
    output = tmp_path / "dashboard"
    vwm_dashboard.build_dashboard(ledger, output, project="sic")
    html = (output / "index.html").read_text(encoding="utf-8")
    data = (output / "data.js").read_text(encoding="utf-8")
    assert "<svg id=\"graph\"" in html
    assert "筛选任务" in html
    assert "https://" not in html
    assert "bulk.scf" in data
