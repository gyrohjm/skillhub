from __future__ import annotations

import json
import mimetypes
import os
import re
import stat
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from rtlib import (
    ResearchTeachError,
    atomic_write,
    config_path,
    load_config,
    now_iso,
    relative_or_absolute,
    sha256_file,
    slugify,
)


SECRET_PATTERNS = (
    (re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"), "private key"),
    (re.compile(r"\b(?:sk|rk|pk)-[A-Za-z0-9_-]{20,}\b"), "API-like key"),
    (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), "email address"),
    (re.compile(r"\b(?:\+?\d[\d -]{8,}\d)\b"), "phone-like number"),
)
SUPPORTED_EXTENSIONS = {".pdf", ".md", ".txt", ".html", ".htm"}
DEFAULT_MINERU_ENV = Path("~/.config/research-teach/mineru.env").expanduser()
MINERU_ENV_KEYS = {"MINERU_API_TOKEN", "MINERU_BASE_URL"}


class _ReadableHTML(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript"}:
            self.ignored_depth += 1
        elif not self.ignored_depth and tag in {"p", "div", "section", "article", "br", "li", "h1", "h2", "h3", "h4"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self.ignored_depth:
            self.ignored_depth -= 1
        elif not self.ignored_depth and tag in {"p", "div", "section", "article", "li", "h1", "h2", "h3", "h4"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.ignored_depth:
            self.parts.append(data)

    def markdown(self) -> str:
        text = "".join(self.parts)
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
        return text.strip()


def mineru_env_path(explicit: str | Path | None = None) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    override = os.environ.get("RESEARCH_TEACH_ENV_FILE")
    if override:
        return Path(override).expanduser().resolve()
    plugin_data = os.environ.get("PLUGIN_DATA") or os.environ.get("CLAUDE_PLUGIN_DATA")
    if plugin_data:
        return (Path(plugin_data).expanduser().resolve() / "mineru.env")
    return DEFAULT_MINERU_ENV.resolve()


def _parse_env_value(value: str) -> str:
    value = value.strip()
    if not value:
        return ""
    if value[0] in {'"', "'"}:
        if value[0] == '"':
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError as exc:
                raise ResearchTeachError(f"Invalid quoted value in MinerU environment file: {exc}") from exc
            if not isinstance(parsed, str):
                raise ResearchTeachError("MinerU environment values must be strings.")
            return parsed
        if len(value) < 2 or value[-1] != "'":
            raise ResearchTeachError("Invalid single-quoted value in MinerU environment file.")
        return value[1:-1]
    return value


def load_mineru_env(explicit: str | Path | None = None) -> dict[str, str]:
    path = mineru_env_path(explicit)
    file_values: dict[str, str] = {}
    if path.is_file():
        for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[7:].lstrip()
            if "=" not in line:
                raise ResearchTeachError(f"Invalid MinerU env line {number}: expected KEY=VALUE.")
            key, value = line.split("=", 1)
            key = key.strip()
            if key not in MINERU_ENV_KEYS:
                continue
            file_values[key] = _parse_env_value(value)
    return {
        key: os.environ.get(key, file_values.get(key, ""))
        for key in MINERU_ENV_KEYS
    }


def configure_mineru(
    token: str,
    *,
    base_url: str = "https://mineru.net/api/v4",
    env_file: str | Path | None = None,
) -> dict[str, Any]:
    token = token.strip()
    base_url = base_url.strip().rstrip("/")
    if not token:
        raise ResearchTeachError("MinerU API token cannot be empty.")
    if not re.match(r"^https://", base_url):
        raise ResearchTeachError("MinerU base URL must use HTTPS.")
    path = mineru_env_path(env_file)
    content = (
        "# Managed by research-teach. Keep this file private.\n"
        f"MINERU_API_TOKEN={json.dumps(token)}\n"
        f"MINERU_BASE_URL={json.dumps(base_url)}\n"
    )
    atomic_write(path, content)
    path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    return {
        "env_file": str(path),
        "permissions": oct(stat.S_IMODE(path.stat().st_mode)),
        "token_configured": True,
        "base_url": base_url,
    }


def mineru_config_status(env_file: str | Path | None = None) -> dict[str, Any]:
    path = mineru_env_path(env_file)
    values = load_mineru_env(path)
    token = values.get("MINERU_API_TOKEN", "")
    return {
        "env_file": str(path),
        "exists": path.is_file(),
        "permissions": oct(stat.S_IMODE(path.stat().st_mode)) if path.is_file() else None,
        "token_configured": bool(token),
        "token_preview": f"{token[:4]}…{token[-4:]}" if len(token) >= 12 else ("configured" if token else None),
        "base_url": values.get("MINERU_BASE_URL") or "https://mineru.net/api/v4",
        "environment_override": bool(os.environ.get("MINERU_API_TOKEN")),
    }


def inspect_upload(path: str | Path, project: str | Path | None = None) -> dict[str, Any]:
    root, config = load_config(project)
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise ResearchTeachError(f"Document does not exist: {source}")
    warnings: list[str] = []
    if source.suffix.casefold() in {".txt", ".md", ".html", ".htm", ".json", ".csv"}:
        sample = source.read_text(encoding="utf-8", errors="ignore")[:250_000]
        warnings = sorted({label for pattern, label in SECRET_PATTERNS if pattern.search(sample)})
    safe_dirs = [
        Path(item).expanduser().resolve()
        for item in config.get("conversion", {}).get("safe_upload_directories", [])
        if isinstance(item, str)
    ]
    covered = any(source == safe or safe in source.parents for safe in safe_dirs)
    return {
        "path": str(source),
        "relative_path": relative_or_absolute(source, root),
        "mime_type": mimetypes.guess_type(source.name)[0] or "application/octet-stream",
        "bytes": source.stat().st_size,
        "safe_directory": covered,
        "warnings": warnings,
        "remote_service": "MinerU API",
        "purpose": "Convert the document into structured Markdown and extracted assets.",
    }


def _remote_allowed(
    source: Path,
    document_type: str,
    approve_upload: bool,
    config: dict[str, Any],
) -> bool:
    if document_type == "reference":
        return True
    if document_type == "confidential":
        return False
    safe_dirs = [
        Path(item).expanduser().resolve()
        for item in config.get("conversion", {}).get("safe_upload_directories", [])
        if isinstance(item, str)
    ]
    safe = any(source == directory or directory in source.parents for directory in safe_dirs)
    return approve_upload or safe


def _json_request(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    payload: dict[str, Any] | None = None,
    timeout: int = 60,
) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(url, data=body, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, json.JSONDecodeError) as exc:
        raise ResearchTeachError(f"HTTP request failed for {url}: {exc}") from exc


def _safe_extract(archive: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as bundle:
        root = destination.resolve()
        for member in bundle.infolist():
            target = (destination / member.filename).resolve()
            if root != target and root not in target.parents:
                raise ResearchTeachError(f"Unsafe archive path: {member.filename}")
        bundle.extractall(destination)


def _download(url: str, destination: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "research-teach/0.1"})
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open("wb") as handle:
                shutil.copyfileobj(response, handle)
    except urllib.error.URLError as exc:
        raise ResearchTeachError(f"Could not download conversion result: {exc}") from exc


def _mineru_convert(
    source: Path,
    output: Path,
    *,
    base_url: str,
    token: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
    apply_payload = {
        "files": [{"name": source.name, "data_id": f"rt-{int(time.time())}", "is_ocr": True}],
        "model_version": "vlm",
        "language": "en",
        "enable_formula": True,
        "enable_table": True,
    }
    response = _json_request(
        f"{base_url.rstrip('/')}/file-urls/batch",
        method="POST",
        headers=headers,
        payload=apply_payload,
    )
    if response.get("code") != 0:
        raise ResearchTeachError(f"MinerU rejected the upload request: {response.get('msg', response)}")
    try:
        batch_id = response["data"]["batch_id"]
        upload_url = response["data"]["file_urls"][0]
    except (KeyError, IndexError, TypeError) as exc:
        raise ResearchTeachError("MinerU returned an unexpected upload response.") from exc

    upload = subprocess.run(
        ["curl", "--fail", "--silent", "--show-error", "--upload-file", str(source), upload_url],
        text=True,
        capture_output=True,
        check=False,
    )
    if upload.returncode != 0:
        raise ResearchTeachError(f"MinerU upload failed: {upload.stderr.strip()}")

    deadline = time.monotonic() + timeout_seconds
    result_info: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        status = _json_request(
            f"{base_url.rstrip('/')}/extract-results/batch/{batch_id}",
            headers=headers,
        )
        try:
            result_info = status["data"]["extract_result"][0]
        except (KeyError, IndexError, TypeError) as exc:
            raise ResearchTeachError("MinerU returned an unexpected status response.") from exc
        state = result_info.get("state")
        if state == "done":
            break
        if state == "failed":
            raise ResearchTeachError(f"MinerU conversion failed: {result_info.get('err_msg', 'unknown')}")
        time.sleep(5)
    else:
        raise ResearchTeachError(f"MinerU timed out after {timeout_seconds} seconds.")

    zip_url = (result_info or {}).get("full_zip_url")
    if not isinstance(zip_url, str) or not zip_url:
        raise ResearchTeachError("MinerU completed without a result archive.")
    archive = output.parent / "mineru-result.zip"
    _download(zip_url, archive)
    _safe_extract(archive, output)
    return {"engine": "mineru-api", "version": "v4", "batch_id": batch_id}


def _direct_convert(source: Path, output: Path) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    text = source.read_text(encoding="utf-8", errors="replace")
    if source.suffix.casefold() in {".html", ".htm"}:
        parser = _ReadableHTML()
        parser.feed(text)
        text = parser.markdown()
    if source.suffix.casefold() == ".txt":
        text = f"# {source.stem}\n\n{text}"
    atomic_write(output / "full.md", text.rstrip() + "\n")
    return {"engine": "direct-local", "version": "1"}


def _opendataloader_executable(config: dict[str, Any]) -> Path | None:
    direct = shutil.which("opendataloader-pdf")
    if direct:
        return Path(direct)
    environment = (
        Path(config["conversion"]["opendataloader_environment"]).expanduser().resolve()
    )
    candidate = environment / "bin/opendataloader-pdf"
    return candidate if candidate.is_file() else None


def _java_major() -> int | None:
    java = shutil.which("java")
    if not java:
        return None
    result = subprocess.run([java, "-version"], text=True, capture_output=True, check=False)
    text = result.stderr + result.stdout
    match = re.search(r'version "(\d+)(?:\.(\d+))?', text)
    if not match:
        return None
    major = int(match.group(1))
    return int(match.group(2)) if major == 1 and match.group(2) else major


def _install_opendataloader(config: dict[str, Any]) -> Path:
    environment = (
        Path(config["conversion"]["opendataloader_environment"]).expanduser().resolve()
    )
    subprocess.run([sys.executable, "-m", "venv", str(environment)], check=True)
    pip = environment / "bin/pip"
    subprocess.run([str(pip), "install", "-U", "opendataloader-pdf"], check=True)
    executable = environment / "bin/opendataloader-pdf"
    if not executable.is_file():
        raise ResearchTeachError("OpenDataLoader installation completed without its CLI.")
    return executable


def _opendataloader_convert(
    source: Path,
    output: Path,
    *,
    config: dict[str, Any],
    install_fallback: bool,
) -> dict[str, Any]:
    major = _java_major()
    if major is None or major < 11:
        raise ResearchTeachError("OpenDataLoader requires Java 11 or newer.")
    executable = _opendataloader_executable(config)
    if executable is None:
        if not install_fallback:
            raise ResearchTeachError(
                "OpenDataLoader is not installed. Re-run with --install-fallback after approval."
            )
        executable = _install_opendataloader(config)
    output.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [
            str(executable),
            str(source),
            "--format",
            "markdown,json",
            "--output-dir",
            str(output),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise ResearchTeachError(f"OpenDataLoader failed: {result.stderr.strip() or result.stdout.strip()}")
    version_result = subprocess.run(
        [str(executable), "--version"], text=True, capture_output=True, check=False
    )
    version = (version_result.stdout or version_result.stderr).strip() or "unknown"
    return {"engine": "opendataloader", "version": version}


def _markdown_candidate(output: Path) -> Path:
    candidates = sorted(output.rglob("*.md"), key=lambda path: (path.name != "full.md", -path.stat().st_size))
    if not candidates:
        raise ResearchTeachError("Conversion produced no Markdown.")
    return candidates[0]


def quality_report(output: Path) -> dict[str, Any]:
    markdown = _markdown_candidate(output)
    text = markdown.read_text(encoding="utf-8", errors="replace")
    visible = re.sub(r"[#>*_`\-\s]", "", text)
    missing_assets: list[str] = []
    for raw in re.findall(r"!?\[[^\]]*\]\(([^)]+)\)", text):
        link = raw.split()[0].strip("<>")
        if re.match(r"^[a-z]+://", link) or link.startswith("#") or link.startswith("data:"):
            continue
        if not (markdown.parent / link).exists():
            missing_assets.append(link)
    errors: list[str] = []
    if len(visible) < 500:
        errors.append("extracted text is shorter than 500 visible characters")
    if re.search(r"<title>\s*(?:error|access denied)", text, flags=re.IGNORECASE):
        errors.append("output appears to contain an error page")
    if missing_assets:
        errors.append(f"{len(missing_assets)} referenced assets are missing")
    return {
        "passed": not errors,
        "markdown": str(markdown),
        "visible_characters": len(visible),
        "missing_assets": missing_assets,
        "errors": errors,
    }


def _formalize(
    source: Path,
    extraction: Path,
    metadata: dict[str, Any],
    document_type: str,
    root: Path,
    config: dict[str, Any],
) -> dict[str, Any]:
    report = quality_report(extraction)
    if not report["passed"]:
        raise ResearchTeachError("Quality gate failed: " + "; ".join(report["errors"]))
    markdown = Path(report["markdown"])
    slug = slugify(source.stem, source.stem[:40] or "source")
    knowledge = config_path(root, config, "knowledge")
    note = knowledge / "Sources/Inbox" / f"{slug}.md"
    assets = knowledge / "Assets" / slug
    if assets.exists():
        shutil.rmtree(assets)
    assets.mkdir(parents=True, exist_ok=True)

    for item in extraction.rglob("*"):
        if not item.is_file() or item == markdown or item.suffix.casefold() in {".md", ".json"}:
            continue
        relative = item.relative_to(extraction)
        destination = assets / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, destination)

    body = markdown.read_text(encoding="utf-8", errors="replace")
    prefix = f"../../Assets/{slug}/"
    body = re.sub(
        r"(!?\[[^\]]*\]\()(?!(?:https?://|data:|#))([^)/][^)]*)\)",
        lambda match: match.group(1) + prefix + match.group(2) + ")",
        body,
    )
    frontmatter = {
        "node_type": "source",
        "status": "inbox",
        "title": source.stem,
        "source_file": relative_or_absolute(source, root),
        "document_use": "unspecified",
        "verification_level": "L0",
        "conversion_engine": metadata["engine"],
        "conversion_version": metadata.get("version", "unknown"),
        "converted_at": now_iso(),
        "file_sha256": sha256_file(source),
        "upload_policy": document_type,
    }
    yaml = "\n".join(f"{key}: {json.dumps(value, ensure_ascii=False)}" for key, value in frontmatter.items())
    atomic_write(note, f"---\n{yaml}\n---\n\n{body.lstrip()}")
    return {
        "note": str(note),
        "assets": str(assets),
        "quality": report,
        "engine": metadata["engine"],
        "version": metadata.get("version", "unknown"),
    }


def convert_document(
    path: str | Path,
    *,
    document_type: str,
    approve_upload: bool = False,
    install_fallback: bool = False,
    project: str | Path | None = None,
    timeout_seconds: int = 900,
) -> dict[str, Any]:
    if document_type not in {"reference", "project_document", "confidential"}:
        raise ResearchTeachError("document_type must be reference, project_document, or confidential.")
    root, config = load_config(project)
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise ResearchTeachError(f"Document does not exist: {source}")
    if source.suffix.casefold() not in SUPPORTED_EXTENSIONS:
        raise ResearchTeachError(
            "Unsupported document type. First version supports PDF, Markdown, TXT, and HTML."
        )
    source_hash = sha256_file(source)
    cache_key = hashlib_sha(f"{source_hash}|mineru-v4|opendataloader|markdown-json")
    cache = config_path(root, config, "cache") / cache_key
    manifest_path = cache / "manifest.json"
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        note = Path(manifest.get("formal", {}).get("note", ""))
        if note.is_file():
            manifest["cache_hit"] = True
            return manifest

    cache.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    metadata: dict[str, Any] | None = None
    extraction: Path | None = None
    if source.suffix.casefold() in {".md", ".txt", ".html", ".htm"}:
        direct_output = cache / "direct/extracted"
        metadata = _direct_convert(source, direct_output)
        report = quality_report(direct_output)
        atomic_write(
            cache / "direct/quality-report.json",
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        )
        if not report["passed"]:
            raise ResearchTeachError(
                "Direct local conversion quality gate failed: " + "; ".join(report["errors"])
            )
        extraction = direct_output

    mineru_env = load_mineru_env()
    token = mineru_env.get("MINERU_API_TOKEN", "")
    base_url = (
        mineru_env.get("MINERU_BASE_URL")
        or config.get("conversion", {}).get("mineru_base_url", "https://mineru.net/api/v4")
    )
    if metadata is None and token and _remote_allowed(source, document_type, approve_upload, config):
        mineru_output = cache / "mineru/extracted"
        try:
            metadata = _mineru_convert(
                source,
                mineru_output,
                base_url=base_url,
                token=token,
                timeout_seconds=timeout_seconds,
            )
            report = quality_report(mineru_output)
            atomic_write(
                cache / "mineru/quality-report.json",
                json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            )
            if not report["passed"]:
                raise ResearchTeachError("MinerU quality gate failed: " + "; ".join(report["errors"]))
            extraction = mineru_output
        except ResearchTeachError as exc:
            errors.append(str(exc))
            metadata = None

    if metadata is None:
        local_output = cache / "opendataloader/extracted"
        try:
            metadata = _opendataloader_convert(
                source,
                local_output,
                config=config,
                install_fallback=install_fallback,
            )
            report = quality_report(local_output)
            atomic_write(
                cache / "opendataloader/quality-report.json",
                json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            )
            if not report["passed"]:
                raise ResearchTeachError(
                    "OpenDataLoader quality gate failed: " + "; ".join(report["errors"])
                )
            extraction = local_output
        except ResearchTeachError as exc:
            errors.append(str(exc))
            failure = {
                "version": 1,
                "source": str(source),
                "source_sha256": source_hash,
                "status": "conversion_failed",
                "errors": errors,
                "created_at": now_iso(),
            }
            atomic_write(manifest_path, json.dumps(failure, ensure_ascii=False, indent=2) + "\n")
            raise ResearchTeachError("Conversion failed: " + " | ".join(errors)) from exc

    assert extraction is not None and metadata is not None
    formal = _formalize(source, extraction, metadata, document_type, root, config)
    manifest = {
        "version": 1,
        "source": str(source),
        "source_sha256": source_hash,
        "status": "converted",
        "document_type": document_type,
        "engine": metadata,
        "formal": formal,
        "errors_before_success": errors,
        "created_at": now_iso(),
        "cache_hit": False,
    }
    atomic_write(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    return manifest


def hashlib_sha(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]


def doctor(project: str | Path | None = None) -> dict[str, Any]:
    root, config = load_config(project)
    executable = _opendataloader_executable(config)
    mineru = mineru_config_status()
    return {
        "project": str(root),
        "mineru_token": mineru["token_configured"],
        "mineru_env_file": mineru["env_file"],
        "mineru_env_permissions": mineru["permissions"],
        "mineru_base_url": mineru["base_url"],
        "opendataloader": str(executable) if executable else None,
        "java_major": _java_major(),
        "global_link": str((root / ".research/global").resolve())
        if (root / ".research/global").is_symlink()
        else None,
    }
