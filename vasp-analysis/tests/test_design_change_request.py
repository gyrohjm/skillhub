from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/design_change_request.py"


def test_change_request_uses_design_provenance_and_does_not_overwrite(tmp_path: Path) -> None:
    task_spec = {
        "design_provenance": {
            "scientific_design_approved": True,
            "design_id": "sic_computation",
            "design_revision": 2,
            "matrix_id": "M1",
            "design_sha256": "design-hash",
            "approval_sha256": "approval-hash",
        }
    }
    (tmp_path / "task_spec.json").write_text(json.dumps(task_spec), encoding="utf-8")
    command = [
        sys.executable,
        str(SCRIPT),
        "--case-root", str(tmp_path),
        "--verdict", "inconclusive",
        "--trigger", "decision threshold not resolved",
        "--proposed-change", "add a denser convergence point",
        "--scientific-reason", "current uncertainty overlaps the effect",
        "--evidence", str(tmp_path / "analysis/plot_data/result.dat"),
    ]
    assert subprocess.run(command, check=False).returncode == 0
    output = tmp_path / "analysis/reports/design_change_request.json"
    request = json.loads(output.read_text(encoding="utf-8"))
    assert request["source_design"]["revision"] == 2
    assert request["source_design"]["matrix_id"] == "M1"
    assert request["requested_action"] == "create_and_review_a_new_computation_design_revision"
    assert subprocess.run(command, check=False).returncode == 1


def test_change_request_rejects_unapproved_task(tmp_path: Path) -> None:
    (tmp_path / "task_spec.json").write_text(
        json.dumps({"design_provenance": {"scientific_design_approved": False}}),
        encoding="utf-8",
    )
    result = subprocess.run([
        sys.executable,
        str(SCRIPT),
        "--case-root", str(tmp_path),
        "--verdict", "falsified",
        "--trigger", "control failed",
        "--proposed-change", "replace model",
        "--scientific-reason", "baseline is invalid",
    ], check=False)
    assert result.returncode == 1
