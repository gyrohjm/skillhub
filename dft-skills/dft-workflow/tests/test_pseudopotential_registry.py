from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import pseudopotential_registry as registry  # noqa: E402


def test_register_resolve_and_verify_private_metadata(tmp_path: Path) -> None:
    pseudo = tmp_path / "Si.upf"
    pseudo.write_text("private pseudo", encoding="utf-8")
    document = {"schema_version": 1, "datasets": []}
    record = {
        "id": "sssp-1.3-pbe-si",
        "family": "SSSP",
        "version": "1.3",
        "xc_functional": "PBE",
        "element": "Si",
        "label": "Si",
        "sha256": registry.sha256_file(pseudo),
        "license": "see upstream",
        "archive_allowed": False,
        "compatible_engines": ["quantum-espresso"],
        "local_path": str(pseudo),
    }
    registry.register_dataset(document, record)
    assert registry.validate(document) == []
    assert registry.resolve(document, element="Si", engine="quantum-espresso") == [record]
    assert registry.verify_local_files(document)[0]["status"] == "verified"
