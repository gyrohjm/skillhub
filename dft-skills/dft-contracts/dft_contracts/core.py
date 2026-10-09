from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


CONTRACT_VERSION = "2026.08"
ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / "schemas"
SCHEMA_FILES = {
    "calculation-design-v2": "calculation-design-v2.json",
    "task-spec-v2": "task-spec-v2.json",
    "workflow-v1": "workflow-v1.json",
    "workflow-v2": "workflow-v2.json",
    "resource-profile-v1": "resource-profile-v1.json",
    "result-v1": "result-v1.json",
    "archive-manifest-v3": "archive-manifest-v3.json",
    "design-change-request-v1": "design-change-request-v1.json",
    "pseudopotential-registry-v1": "pseudopotential-registry-v1.json",
    "research-idea-v1": "research-idea-v1.json",
}


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def contract_path(name: str) -> Path:
    try:
        filename = SCHEMA_FILES[name]
    except KeyError as exc:
        raise KeyError(f"unknown DFT contract: {name}") from exc
    return SCHEMAS / filename


def validate_document(name: str, document: dict[str, Any]) -> list[str]:
    schema = json.loads(contract_path(name).read_text(encoding="utf-8"))
    try:
        import jsonschema
    except ImportError:
        return _minimal_validate(schema, document)
    validator = jsonschema.Draft202012Validator(schema)
    return [
        f"{'/'.join(str(part) for part in error.absolute_path) or '<root>'}: {error.message}"
        for error in sorted(validator.iter_errors(document), key=lambda item: list(item.absolute_path))
    ]


def _minimal_validate(schema: dict[str, Any], document: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for key in schema.get("required", []):
        if key not in document:
            errors.append(f"<root>: {key!r} is required")
    properties = schema.get("properties", {})
    for key, rules in properties.items():
        if key not in document or "const" not in rules:
            continue
        if document[key] != rules["const"]:
            errors.append(f"{key}: must equal {rules['const']!r}")
    return errors


def capability_registry() -> dict[str, Any]:
    return json.loads((ROOT / "capabilities.json").read_text(encoding="utf-8"))
