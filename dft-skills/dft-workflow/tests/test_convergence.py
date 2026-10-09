from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import dft_convergence  # noqa: E402


def test_workflow_binds_campaign_candidate_without_approving(tmp_path: Path) -> None:
    value = {
        "candidates": [{"parameter_value": 400, "status": "planned", "observable_value": None}],
        "approval": {"status": "not_requested", "selected_value": None},
    }
    dft_convergence.bind_task(value, "400", tmp_path / "energy/scf/encut_400", "abc")
    assert value["candidates"][0]["status"] == "prepared"
    assert value["approval"]["selected_value"] is None
    assert dft_convergence.next_candidates(value) == []
