"""Read-only cluster and execution-environment preflight for dft-workflow.

The command deliberately detects resources; it never creates environments,
loads modules permanently, edits task files, or submits a scheduler job.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from canonical_workflow import WorkflowError, load_resource_profile, normalize_environment


Runner = Callable[..., object]


def _run_command(
    argv: Sequence[str], *, cwd: str | None = None, env: Mapping[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            list(argv),
            cwd=cwd,
            env=dict(env) if env is not None else None,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=15,
        )
    except (FileNotFoundError, OSError) as exc:
        return subprocess.CompletedProcess(list(argv), 127, "", str(exc))
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else "timeout"
        return subprocess.CompletedProcess(list(argv), 124, stdout, stderr)


def _result(result: object) -> tuple[int, str, str]:
    return (
        int(getattr(result, "returncode", 1)),
        str(getattr(result, "stdout", "") or ""),
        str(getattr(result, "stderr", "") or ""),
    )


def _probe(runner: Runner, argv: Sequence[str], *, cwd: str | None, env: Mapping[str, str]) -> dict:
    try:
        result = runner(list(argv), cwd=cwd, env=dict(env))
    except Exception as exc:  # pragma: no cover - defensive boundary for a probe
        return {"ok": False, "returncode": 1, "stdout": "", "stderr": str(exc)}
    returncode, stdout, stderr = _result(result)
    return {"ok": returncode == 0, "returncode": returncode, "stdout": stdout, "stderr": stderr}


def _integer(value: str) -> int | None:
    try:
        return int(value.strip())
    except (TypeError, ValueError):
        return None


def parse_sinfo(output: str) -> list[dict]:
    """Parse the stable pipe-delimited format used by the preflight probe."""

    partitions: list[dict] = []
    for line in output.splitlines():
        fields = line.strip().split("|")
        if len(fields) != 8:
            continue
        name, availability, cpus, memory_mb, nodes, gres, node_list, state = fields
        partitions.append(
            {
                "name": name.rstrip("*"),
                "availability": availability,
                "cpus_per_node": _integer(cpus),
                "memory_mb": _integer(memory_mb),
                "node_count": _integer(nodes),
                "gres": gres,
                "node_list": node_list,
                "state": state,
            }
        )
    return partitions


def _command_map(user: str, *, include_generic_environment: bool = True) -> dict[str, list[str]]:
    commands = {
        "hostname": ["hostname", "-f"],
        "user": ["whoami"],
        "sinfo": ["sinfo", "-h", "-o", "%P|%a|%c|%m|%D|%G|%N|%t"],
        "scontrol_partition": ["scontrol", "show", "partition"],
        "scontrol_node": ["scontrol", "show", "node"],
        "squeue": ["squeue", "-h", "-u", user],
        "storage": ["df", "-P", "-h", "/home"],
    }
    if include_generic_environment:
        commands.update(
            {
                "modules": ["bash", "-lc", "module -t avail vasp quantum-espresso 2>&1"],
                "vasp_std": ["bash", "-lc", "command -v vasp_std"],
                "pw.x": ["bash", "-lc", "command -v pw.x"],
            }
        )
    return commands


def _configure_text_output() -> None:
    """Keep probe reports printable on Windows consoles with a legacy code page."""

    stream = getattr(sys, "stdout", None)
    reconfigure = getattr(stream, "reconfigure", None)
    if reconfigure is not None:
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            pass


def _activation_probe(
    runner: Runner,
    profile: Mapping[str, Any],
    *,
    cwd: str | None,
    env: Mapping[str, str],
) -> dict:
    """Verify one approved activation profile in an isolated login shell."""

    try:
        activation = normalize_environment(profile)
    except WorkflowError as exc:
        return {
            "method": "invalid",
            "available": False,
            "command": None,
            "stdout": "",
            "stderr": str(exc),
        }

    commands: list[str] = []
    if activation["method"] == "modules":
        if activation.get("module_init"):
            commands.append(str(activation["module_init"]))
        if activation.get("availability_probe"):
            commands.append(str(activation["availability_probe"]))
        if activation.get("purge"):
            commands.append("module purge")
        commands.extend(f"module load {module}" for module in activation["modules"])
    else:
        commands.append(str(activation["availability_probe"]))
        commands.append(str(activation["source_command"]))
    commands.append(str(activation["verify_command"]))
    shell_command = " && ".join(commands)
    result = _probe(runner, ["bash", "-lc", shell_command], cwd=cwd, env=env)
    return {
        "method": activation["method"],
        "available": result["ok"] and bool(result["stdout"].strip()),
        "command": shell_command,
        "stdout": result["stdout"].strip(),
        "stderr": result["stderr"].strip(),
        "documentation_url": activation.get("documentation_url"),
    }


def probe_resources(
    *,
    runner: Runner | None = None,
    profile: str | None = None,
    engine: str | None = None,
    cwd: str | None = None,
    env: Mapping[str, str] | None = None,
    activation_profile: Mapping[str, Any] | None = None,
    refresh_discovery: bool = False,
) -> dict:
    """Run only read-only probes and return an auditable resource report."""

    probe_runner = runner or _run_command
    if not refresh_discovery:
        if activation_profile is None:
            raise WorkflowError(
                "ordinary resource checks require an approved profile; use --refresh-discovery "
                "for broad discovery"
            )
        lightweight = lightweight_preflight(activation_profile, probe_runner)
        return _lightweight_report_view(lightweight, profile=profile, engine=engine)
    effective_env = dict(os.environ)
    if env:
        effective_env.update(env)
    user = effective_env.get("USER") or effective_env.get("USERNAME") or "unknown"
    commands = _command_map(
        user, include_generic_environment=activation_profile is None
    )
    results = {
        name: _probe(probe_runner, argv, cwd=cwd, env=effective_env)
        for name, argv in commands.items()
    }

    partitions = parse_sinfo(results["sinfo"]["stdout"])
    slurm_available = results["sinfo"]["ok"] and results["scontrol_partition"]["ok"]
    not_probed = {
        "ok": False,
        "returncode": None,
        "stdout": "",
        "stderr": "not probed before approved activation",
    }
    executable_specs = {
        "vasp_std": results.get("vasp_std", not_probed),
        "pw.x": results.get("pw.x", not_probed),
    }
    executables = {
        name: {
            "available": result["ok"] and bool(result["stdout"].strip()),
            "path": result["stdout"].strip() if result["ok"] else None,
            "stderr": result["stderr"].strip(),
        }
        for name, result in executable_specs.items()
    }
    activation = (
        _activation_probe(
            probe_runner,
            activation_profile,
            cwd=cwd,
            env=effective_env,
        )
        if activation_profile is not None
        else None
    )
    if activation is not None and activation["available"]:
        approved_executable = str(activation_profile.get("executable") or "")
        if approved_executable:
            resolved_path = activation["stdout"].splitlines()[-1].strip()
            executables[approved_executable] = {
                "available": True,
                "path": resolved_path or None,
                "stderr": activation["stderr"],
            }

    blockers: list[str] = []
    warnings: list[str] = []
    if not slurm_available:
        blockers.append("Slurm sinfo/scontrol preflight is unavailable or failed")
    elif not partitions:
        blockers.append("sinfo returned no parseable partitions")
    if activation is None and not results["modules"]["ok"]:
        warnings.append("module availability could not be verified in a login shell")
    required_executable = {"vasp": "vasp_std", "quantum-espresso": "pw.x", "qe": "pw.x"}.get(engine or "")
    if activation is not None and not activation["available"]:
        blockers.append(
            f"approved environment activation failed: {activation['method']}"
        )
    elif (
        activation is None
        and required_executable
        and not executables[required_executable]["available"]
    ):
        blockers.append(f"required executable is unavailable: {required_executable}")
    if activation_profile is not None:
        requested_partition = activation_profile.get("partition")
        matching_partition = next(
            (item for item in partitions if item["name"] == requested_partition), None
        )
        if requested_partition and matching_partition is None:
            blockers.append(
                f"approved partition is unavailable: {requested_partition}"
            )
        if matching_partition is not None:
            requested_nodes = activation_profile.get("nodes")
            available_nodes = matching_partition.get("node_count")
            if (
                isinstance(requested_nodes, int)
                and isinstance(available_nodes, int)
                and requested_nodes > available_nodes
            ):
                blockers.append(
                    f"approved node count exceeds live partition inventory: {requested_nodes}>{available_nodes}"
                )
            tasks_per_node = activation_profile.get("ntasks_per_node")
            cpus_per_task = activation_profile.get("cpus_per_task", 1)
            live_cpus = matching_partition.get("cpus_per_node")
            if (
                isinstance(tasks_per_node, int)
                and isinstance(cpus_per_task, int)
                and isinstance(live_cpus, int)
                and tasks_per_node * cpus_per_task > live_cpus
            ):
                blockers.append(
                    "approved CPU request exceeds live CPUs per node: "
                    f"{tasks_per_node * cpus_per_task}>{live_cpus}"
                )

    status = "ready" if not blockers else "blocked"
    return {
        "schema_version": 1,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "requested_profile": profile,
        "requested_engine": engine,
        "identity": {
            "hostname": results["hostname"]["stdout"].strip() or None,
            "user": results["user"]["stdout"].strip() or user,
            "cwd": str(Path(cwd or os.getcwd()).resolve()),
            "python": sys.executable,
            "python_version": sys.version.split()[0],
        },
        "scheduler": {
            "name": "slurm",
            "slurm_available": slurm_available,
            "partitions": partitions,
            "queue_check": results["squeue"]["stdout"].strip(),
            "node_check_ok": results["scontrol_node"]["ok"],
        },
        "environment": {
            "module_system": {
                "available": (
                    activation["available"]
                    if activation is not None and activation["method"] == "modules"
                    else results.get("modules", not_probed)["ok"]
                ),
                "inventory": (
                    activation["stdout"]
                    if activation is not None and activation["method"] == "modules"
                    else (
                        results.get("modules", not_probed)["stdout"].strip()
                        if results.get("modules", not_probed)["ok"]
                        else ""
                    )
                ),
            },
            "executables": executables,
            "activation": activation,
        },
        "storage": {
            "home_check_ok": results["storage"]["ok"],
            "df": results["storage"]["stdout"].strip(),
        },
        "environment_creation": "forbidden_by_default",
        "blockers": blockers,
        "warnings": warnings,
        "probe_commands": commands,
    }


_PREFLIGHT_INVALIDATION_REASONS = frozenset(
    {
        "scheduler_rejection",
        "partition_missing",
        "activation_failure",
        "executable_failure",
        "repeated_environment_failure",
        "agent_detected_cluster_drift",
    }
)


def _profile_activation_command(profile: Mapping[str, Any]) -> str:
    """Return the one activation command approved for a resource profile."""

    for key in ("activation_command", "approved_activation"):
        value = profile.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    environment = profile.get("environment")
    if isinstance(environment, Mapping):
        value = environment.get("activation_command")
        if isinstance(value, str) and value.strip():
            return value.strip()
        method = environment.get("method")
        if method == "source-script":
            value = environment.get("source_command")
            if isinstance(value, str) and value.strip():
                return value.strip()
        if method == "modules":
            commands: list[str] = []
            module_init = environment.get("module_init")
            if isinstance(module_init, str) and module_init.strip():
                commands.append(module_init.strip())
            modules = environment.get("modules", [])
            if isinstance(modules, list):
                commands.extend(f"module load {module}" for module in modules)
            if commands:
                return " && ".join(commands)

    raise WorkflowError("resource profile requires one approved activation command")


def profiles_equivalent(left: Any, right: Any) -> bool:
    """Compare technical identity; scientific input/evidence metadata is not an environment."""

    if not isinstance(left, Mapping) or not isinstance(right, Mapping):
        return False
    try:
        left_payload = json.dumps(
            _technical_profile(left), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        )
        right_payload = json.dumps(
            _technical_profile(right), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        )
    except (TypeError, ValueError):
        return False
    return left_payload == right_payload


def _technical_profile(profile):
    ignored = {"engine_parameters", "input_hashes", "scientific_parameters", "profile_id",
        "document", "document_sha256", "checked_at", "status", "documentation_url", "evidence"}
    return {key: value for key, value in profile.items() if key not in ignored}


def _profile_key(profile):
    payload = json.dumps(_technical_profile(profile), sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


_SAFE_EXECUTABLE_COMPONENT = re.compile(r"[A-Za-z0-9_+@.-]+")


def _safe_executable(value: Any) -> str:
    """Validate one shell-safe executable identifier or POSIX path."""

    if not isinstance(value, str) or not value.strip():
        raise WorkflowError("resource profile executable must be a non-empty string")
    executable = value.strip()
    parts = executable.split("/")
    if any(part == "" for part in parts[1:] if parts):
        raise WorkflowError(
            f"resource profile executable is unsafe: {executable!r}"
        )
    if executable.startswith("/"):
        components = parts[1:]
    elif executable.startswith("./"):
        components = parts[1:]
    elif "/" not in executable:
        components = parts
    else:
        raise WorkflowError(
            f"resource profile executable is unsafe: relative path must start with './': {executable!r}"
        )
    if not components or any(component in {".", ".."} for component in components):
        raise WorkflowError(f"resource profile executable is unsafe: {executable!r}")
    if any(not _SAFE_EXECUTABLE_COMPONENT.fullmatch(component) for component in components):
        raise WorkflowError(f"resource profile executable is unsafe: {executable!r}")
    return executable


def _partition_is_available(output: str, partition: str) -> bool:
    unavailable = {"down", "drain", "drained", "inactive", "inact", "unknown", "no"}
    for line in output.splitlines():
        name, separator, availability = line.strip().partition("|")
        if not separator:
            continue
        if name.rstrip("*").strip() != partition:
            continue
        return availability.strip().casefold() not in unavailable
    return False


def _lightweight_check(
    result: Mapping[str, Any], argv: Sequence[str], *, passed: bool | None = None
) -> dict[str, Any]:
    ok = bool(result.get("ok")) if passed is None else passed
    detail = str(result.get("stdout", "") or "").strip()
    stderr = str(result.get("stderr", "") or "").strip()
    if stderr:
        detail = f"{detail}\n{stderr}".strip()
    return {
        "status": "passed" if ok else "failed",
        "detail": detail,
        "command": " ".join(str(item) for item in argv),
        "returncode": result.get("returncode"),
    }


_BATCH_NAMES = ("scheduler_command", "target_partition", "approved_activation", "approved_executable")


def format_batched_probe_output(checks: Mapping[str, Mapping[str, Any]]) -> str:
    """Serialize captured check evidence in the same framing as the target shell."""
    frames = []
    for name in _BATCH_NAMES:
        item = checks[name]
        frames.append(f"DFT_PREFLIGHT_V1 BEGIN {name}\n{item.get('detail', '')}\n"
            f"DFT_PREFLIGHT_V1 END {name} {int(item.get('returncode', 0))}\n")
    return "".join(frames)


def _batched_script(partition: str, activation: str, executable: str) -> str:
    commands = (
        ("scheduler_command", "command -v sbatch"),
        ("target_partition", f"sinfo -h -p {shlex.quote(partition)} -o '%P|%a'"),
        ("approved_activation", activation),
        ("approved_executable", f"if [ \"$dft_activation_rc\" -eq 0 ]; then command -v {shlex.quote(executable)}; else false; fi"),
    )
    lines = ["# DFT_PREFLIGHT_V1", "set +e"]
    for name, command in commands:
        lines.extend([f"printf 'DFT_PREFLIGHT_V1 BEGIN {name}\\n'", command, "dft_check_rc=$?"])
        if name == "approved_activation":
            lines.append("dft_activation_rc=$dft_check_rc")
        lines.append(f"printf '\\nDFT_PREFLIGHT_V1 END {name} %s\\n' \"$dft_check_rc\"")
    return "\n".join(lines) + "\n"


def lightweight_preflight(
    profile: Mapping[str, Any], runner: Runner, *, checked_at: str | None = None,
) -> dict[str, Any]:
    """One target-shell call, with activation and executable checks in that same shell."""
    if not isinstance(profile, Mapping):
        raise WorkflowError("resource profile must be an object")
    partition = profile.get("partition")
    if not isinstance(partition, str) or not partition.strip():
        raise WorkflowError("resource profile partition must be a non-empty string")
    executable = _safe_executable(profile.get("executable"))
    partition = partition.strip()
    script = _batched_script(partition, _profile_activation_command(profile), executable)
    argv = ["bash", "-lc", script]
    result = _probe(runner, argv, cwd=None, env=dict(os.environ))
    output = result["stdout"]
    pattern = r"^DFT_PREFLIGHT_V1 BEGIN (\w+)\n(.*?)\nDFT_PREFLIGHT_V1 END \1 ([0-9]+)\r?$"
    frames = re.findall(pattern, output.replace("\r\n", "\n"), flags=re.M | re.S)
    valid_frames = (len(frames) == 4 and [f[0] for f in frames] == list(_BATCH_NAMES)
        and len(re.findall(r"^DFT_PREFLIGHT_V1 (?:BEGIN|END) ", output, re.M)) == 8)
    checks = {}
    for name in _BATCH_NAMES:
        frame = next((f for f in frames if f[0] == name), None) if valid_frames else None
        rc = int(frame[2]) if frame else 1
        detail = frame[1].strip() if frame else "missing or malformed target-shell check evidence"
        passed = bool(result["ok"] and frame and rc == 0)
        if name == "target_partition":
            passed = passed and _partition_is_available(detail, partition)
        if name in {"scheduler_command", "approved_executable"}:
            passed = passed and bool(detail)
        checks[name] = {"status": "passed" if passed else "failed", "detail": detail,
            "command": "batched target-shell: " + name, "returncode": rc}
        if not passed and result.get("stderr"):
            checks[name]["detail"] += "\n" + result["stderr"]
    reasons = ("scheduler_rejection", "partition_missing", "activation_failure", "executable_failure")
    failed_reason = next((reason for name, reason in zip(_BATCH_NAMES, reasons)
        if checks[name]["status"] != "passed"), None)
    return {"schema_version": 1, "contract": "dft.resource-profile.v1",
        "cache_status": "ready" if failed_reason is None else "stale",
        "checked_at": checked_at or datetime.now(timezone.utc).isoformat(), "checks": checks,
        "invalidation_reason": failed_reason, "approved_profile": copy.deepcopy(dict(profile))}


def _resource_cache_path(project_root: str | Path) -> Path:
    root = Path(project_root).expanduser().resolve()
    if not root.is_dir():
        raise WorkflowError(f"project root does not exist: {root}")
    dft_root = root / ".dft"
    if dft_root.is_symlink():
        raise WorkflowError(f"unsafe resource cache directory: symlink is not allowed: {dft_root}")
    return dft_root / "resource-profile.json"


def load_cached_preflight(project_root: str | Path, *, profile=None) -> dict[str, Any] | None:
    """Load a schema-valid project resource cache, if one exists."""

    cache_path = _resource_cache_path(project_root)
    if cache_path.is_symlink() or not cache_path.is_file():
        return None
    try:
        value = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(value, dict):
        return None
    if profile is not None:
        if profiles_equivalent(value.get("approved_profile"), profile):
            value = {key: item for key, item in value.items() if key != "entries"}
        else:
            entries = value.get("entries", {})
            value = entries.get(_profile_key(profile)) if isinstance(entries, dict) else None
            if not isinstance(value, dict) or not profiles_equivalent(value.get("approved_profile"), profile):
                return None
    try:
        from dft_contracts import validate_document

        if validate_document("resource-profile-v1", value):
            return None
        if value.get("cache_status") == "ready" and (value.get("invalidation_reason") is not None
                or any(value["checks"][name].get("status") != "passed" for name in _BATCH_NAMES)):
            return None
    except (ImportError, KeyError, OSError):
        return None
    return value


def _atomic_write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def invalidate_preflight(project_root: str | Path, reason: str, *, profile=None) -> dict[str, Any]:
    """Mark the project cache invalidated for one approved technical reason."""

    if reason not in _PREFLIGHT_INVALIDATION_REASONS:
        allowed = ", ".join(sorted(_PREFLIGHT_INVALIDATION_REASONS))
        raise ValueError(f"invalidation reason must be one of: {allowed}")
    cache_path = _resource_cache_path(project_root)
    cached = load_cached_preflight(project_root, profile=profile)
    if cached is None:
        now = datetime.now(timezone.utc).isoformat()
        cached = {
            "schema_version": 1,
            "contract": "dft.resource-profile.v1",
            "cache_status": "invalidated",
            "checked_at": now,
            "checks": {
                name: {"status": "unknown", "detail": "", "command": ""}
                for name in (
                    "scheduler_command",
                    "target_partition",
                    "approved_activation",
                    "approved_executable",
                )
            },
            "invalidation_reason": reason,
            "approved_profile": copy.deepcopy(dict(profile or {})),
        }
    else:
        cached = copy.deepcopy(cached)
        cached["cache_status"] = "invalidated"
        cached["invalidation_reason"] = reason
        cached["invalidated_at"] = datetime.now(timezone.utc).isoformat()
    return _store_cached_preflight(project_root, cached)


def _store_cached_preflight(
    project_root: str | Path, record: Mapping[str, Any]
) -> dict[str, Any]:
    """Persist one ready record after validating the Task 1 cache contract."""

    value = copy.deepcopy(dict(record))
    value.pop("entries", None)
    if value.get("cache_status") == "ready" and (value.get("invalidation_reason") is not None
            or any(value.get("checks", {}).get(name, {}).get("status") != "passed" for name in _BATCH_NAMES)):
        raise WorkflowError("ready preflight requires passed evidence for every check")
    from dft_contracts import validate_document

    errors = validate_document("resource-profile-v1", value)
    if errors:
        raise WorkflowError("resource profile cache is invalid: " + "; ".join(errors))
    previous = load_cached_preflight(project_root)
    entries = copy.deepcopy(previous.get("entries", {})) if previous else {}
    if previous:
        old_entry = {key: item for key, item in previous.items() if key != "entries"}
        entries[_profile_key(old_entry["approved_profile"])] = old_entry
    entries[_profile_key(value["approved_profile"])] = copy.deepcopy(value)
    value["entries"] = entries
    _atomic_write_json(_resource_cache_path(project_root), value)
    return value


def _lightweight_report_view(
    report: Mapping[str, Any], *, profile: str | None, engine: str | None
) -> dict[str, Any]:
    """Expose the legacy report fields without adding broad probes."""

    checks = report.get("checks", {})
    partition_check = checks.get("target_partition", {}) if isinstance(checks, Mapping) else {}
    partition_lines = str(partition_check.get("detail", "") or "").splitlines()
    partitions: list[dict[str, Any]] = []
    for line in partition_lines:
        name, separator, availability = line.partition("|")
        if separator:
            partitions.append(
                {
                    "name": name.rstrip("*"),
                    "availability": availability.strip(),
                    "cpus_per_node": None,
                    "memory_mb": None,
                    "node_count": None,
                    "gres": "",
                    "node_list": "",
                    "state": "",
                }
            )
    executable_check = checks.get("approved_executable", {}) if isinstance(checks, Mapping) else {}
    executable_output = str(executable_check.get("detail", "") or "").splitlines()
    executable = (
        report.get("approved_profile", {}).get("executable")
        if isinstance(report.get("approved_profile"), Mapping)
        else None
    )
    activation_check = checks.get("approved_activation", {}) if isinstance(checks, Mapping) else {}
    lightweight_checks = checks if isinstance(checks, Mapping) else {}
    blockers = [
        f"{name}: {check.get('detail', '')}".strip()
        for name, check in lightweight_checks.items()
        if isinstance(check, Mapping) and check.get("status") != "passed"
    ]
    return {
        **dict(report),
        "status": "ready" if report.get("cache_status") == "ready" else "blocked",
        "requested_profile": profile,
        "requested_engine": engine,
        "identity": {
            "hostname": None,
            "user": None,
            "cwd": str(Path.cwd()),
            "python": sys.executable,
            "python_version": sys.version.split()[0],
        },
        "scheduler": {
            "name": "slurm",
            "slurm_available": checks.get("scheduler_command", {}).get("status") == "passed"
            if isinstance(checks, Mapping)
            else False,
            "partitions": partitions,
            "queue_check": "",
            "node_check_ok": False,
        },
        "environment": {
            "module_system": {"available": False, "inventory": ""},
            "executables": {
                str(executable): {
                    "available": executable_check.get("status") == "passed",
                    "path": executable_output[-1].strip() if executable_output else None,
                    "stderr": "",
                }
            }
            if executable
            else {},
            "activation": {
                "available": activation_check.get("status") == "passed",
                "command": activation_check.get("command"),
                "stderr": "",
            },
        },
        "storage": {"home_check_ok": False, "df": ""},
        "environment_creation": "forbidden_by_default",
        "blockers": blockers,
        "warnings": [],
        "probe_commands": {
            name: str(check.get("command", "")).split()
            for name, check in lightweight_checks.items()
            if isinstance(check, Mapping)
        },
    }


_RESOURCE_MARKER_START = "<!-- dft-workflow:project-resources:start -->"
_RESOURCE_MARKER_END = "<!-- dft-workflow:project-resources:end -->"
_PROFILE_MARKER_START = "<!-- dft-workflow:profiles:start -->"
_PROFILE_MARKER_END = "<!-- dft-workflow:profiles:end -->"


def render_project_resource_doc(report: dict) -> str:
    """Render the one project-level resource baseline document."""

    identity = report.get("identity", {})
    scheduler = report.get("scheduler", {})
    environment = report.get("environment", {})
    modules = environment.get("module_system", {})
    executables = environment.get("executables", {})
    storage = report.get("storage", {})
    lines = [
        "# Project Resource Baseline",
        "",
        "> This document is generated during project initialization by",
        "> `dft-workflow/scripts/resource_preflight.py`. It is a project-level",
        "> baseline, not permission to submit. Before a real submission, perform",
        "> the targeted live drift checks described in the workflow skill.",
        "",
        f"- Status: `{report.get('status', 'unknown')}`",
        f"- Checked at (UTC): `{report.get('checked_at', 'unknown')}`",
        f"- Requested profile: `{report.get('requested_profile') or 'not specified'}`",
        f"- Requested engine: `{report.get('requested_engine') or 'not specified'}`",
        f"- Host: `{identity.get('hostname') or 'unknown'}`",
        f"- User: `{identity.get('user') or 'unknown'}`",
        f"- Scheduler: `{scheduler.get('name') or 'unknown'}`",
        f"- Python runtime: `{identity.get('python') or 'unknown'}` ({identity.get('python_version') or 'unknown'})",
        "",
        "## Detected partitions and node resources",
        "",
        "| Partition | Availability | CPUs/node | Memory (MB) | Nodes | GRES | Node list | State |",
        "|---|---|---:|---:|---:|---|---|---|",
    ]
    partitions = scheduler.get("partitions", [])
    if partitions:
        for item in partitions:
            lines.append(
                "| {name} | {availability} | {cpus} | {memory} | {nodes} | {gres} | {node_list} | {state} |".format(
                    name=item.get("name", ""),
                    availability=item.get("availability", ""),
                    cpus=item.get("cpus_per_node", ""),
                    memory=item.get("memory_mb", ""),
                    nodes=item.get("node_count", ""),
                    gres=item.get("gres", ""),
                    node_list=item.get("node_list", ""),
                    state=item.get("state", ""),
                )
            )
    else:
        lines.append("| _none detected_ | | | | | | | |")

    lines.extend(
        [
            "",
            "## Module and executable baseline",
            "",
            f"- Module probe available: `{modules.get('available', False)}`",
            "- Module inventory:",
            "",
            "```text",
            modules.get("inventory", "(not available)"),
            "```",
            "",
            "| Executable | Available | Resolved path |",
            "|---|---|---|",
        ]
    )
    for name, item in executables.items():
        lines.append(f"| `{name}` | `{item.get('available', False)}` | `{item.get('path') or ''}` |")

    lines.extend(
        [
            "",
            "## Storage and scheduler checks",
            "",
            f"- Slurm available: `{scheduler.get('slurm_available', False)}`",
            f"- Node check passed: `{scheduler.get('node_check_ok', False)}`",
            f"- Home storage check passed: `{storage.get('home_check_ok', False)}`",
            "",
            "```text",
            storage.get("df", "(not available)"),
            "```",
            "",
            "## Persistent workflow rules",
            "",
            "- Reuse the approved module/runtime identity for ordinary tasks.",
            "- Do not create a per-task conda/venv/container or install packages during workflow preparation.",
            "- A live mismatch blocks submission and requires a deliberate resource refresh; do not silently substitute a node, module, engine, or environment.",
            "- Resource facts belong in this document and task-specific resource identity belongs in the leaf `workflow.json`.",
            "",
            "## Approved job profiles",
            "",
            "The initialization probe records detected facts but does not approve a node count,",
            "software build, or launch command. Add a profile only after those fields have been",
            "reviewed for a concrete task scale. `canonical_workflow.py prepare` reads only this",
            "marked block and refuses missing, candidate, or engine-mismatched profiles.",
            "",
            _PROFILE_MARKER_START,
            "```json",
            json.dumps(
                {
                    "schema": "dft.project-resources.v1",
                    "cluster": identity.get("hostname") or "unknown",
                    "scheduler": scheduler.get("name") or "unknown",
                    "profiles": {},
                },
                ensure_ascii=False,
                indent=2,
            ),
            "```",
            _PROFILE_MARKER_END,
            "",
            "## Probe evidence",
            "",
            "```text",
        ]
    )
    for name, argv in report.get("probe_commands", {}).items():
        lines.append(f"{name}: {' '.join(argv)}")
    lines.extend(["```", ""])
    return "\n".join(lines)


def _agents_pointer_block() -> str:
    return "\n".join(
        [
            _RESOURCE_MARKER_START,
            "## DFT Project Resource Baseline",
            "",
            "Before using `dft-workflow`, read `docs/project-resources.md`. It is the",
            "project-initialization record of the approved cluster, node, module,",
            "executable, runtime, and storage baseline. Do not invent resources or",
            "create a per-task environment. Refresh the document only through an",
            "explicit project resource initialization/refresh operation when live",
            "facts have changed.",
            _RESOURCE_MARKER_END,
        ]
    )


def record_project_resources(
    project_root: str | Path,
    report: dict,
    *,
    apply: bool = False,
    overwrite: bool = False,
) -> dict[str, str]:
    """Record a ready initialization report and point AGENTS.md at it."""

    if report.get("status") != "ready":
        raise ValueError("project resource document requires a ready preflight report")
    root = Path(project_root).resolve()
    agents = root / "AGENTS.md"
    resource_document = root / "docs" / "project-resources.md"
    if not agents.is_file():
        raise FileNotFoundError(f"project AGENTS.md is required: {agents}")
    if resource_document.exists() and not overwrite:
        raise FileExistsError(f"resource document already exists: {resource_document}")
    result = {"resource_document": str(resource_document), "agents": str(agents)}
    if not apply:
        return result

    from dft_contracts.project import init_project
    init_project(root)  # Record initialization also establishes memory and private ignores.
    resource_document.parent.mkdir(parents=True, exist_ok=True)
    resource_document.write_text(render_project_resource_doc(report), encoding="utf-8")
    agents_text = agents.read_text(encoding="utf-8")
    if _RESOURCE_MARKER_START not in agents_text:
        separator = "\n" if agents_text.endswith("\n") else "\n\n"
        agents.write_text(agents_text + separator + _agents_pointer_block() + "\n", encoding="utf-8")
    return result


def main(argv: Sequence[str] | None = None) -> int:
    _configure_text_output()
    parser = argparse.ArgumentParser(description="Run read-only DFT cluster resource preflight")
    parser.add_argument(
        "--profile",
        help="approved profile id; targeted checks resolve it from the project resource document",
    )
    parser.add_argument("--engine", choices=["vasp", "quantum-espresso", "qe"], help="required executable")
    parser.add_argument("--cwd", help="remote project working directory to inspect")
    parser.add_argument("--record-project", action="store_true", help="prepare a project-level resource baseline")
    parser.add_argument("--project-root", help="workspace root for --record-project")
    parser.add_argument(
        "--resource-document",
        help="project resource document containing the approved profile for a targeted live check",
    )
    parser.add_argument("--apply", action="store_true", help="write the baseline and AGENTS.md pointer")
    parser.add_argument("--overwrite", action="store_true", help="allow replacing an existing baseline document")
    parser.add_argument(
        "--refresh-discovery",
        action="store_true",
        help="explicitly enable the legacy broad resource discovery probes",
    )
    parser.add_argument("--json", action="store_true", help="print the complete JSON report")
    args = parser.parse_args(argv)
    if args.record_project and (not args.project_root or not args.engine):
        parser.error("--record-project requires --project-root and --engine")
    if args.record_project and args.resource_document:
        parser.error("--resource-document is for targeted checks, not --record-project")
    if args.record_project and not args.refresh_discovery:
        parser.error("--record-project requires --refresh-discovery for broad discovery")
    activation_profile = None
    selected_resource_document = args.resource_document
    if not args.record_project and args.profile:
        if not args.project_root or not args.engine:
            parser.error(
                "targeted --profile checks require --project-root and --engine"
            )
        selected_resource_document = (
            selected_resource_document or "docs/project-resources.md"
        )
    if selected_resource_document:
        if not args.project_root or not args.profile or not args.engine:
            parser.error(
                "--resource-document requires --project-root, --profile, and --engine"
            )
        normalized_engine = (
            "quantum-espresso" if args.engine == "qe" else args.engine
        )
        try:
            activation_profile, _, _ = load_resource_profile(
                args.project_root,
                selected_resource_document,
                args.profile,
                normalized_engine,
            )
        except WorkflowError as exc:
            print(f"BLOCKER: {exc}")
            return 1
    report = probe_resources(
        profile=args.profile,
        engine=args.engine,
        cwd=args.cwd,
        activation_profile=activation_profile,
        refresh_discovery=args.refresh_discovery,
    )
    if args.record_project:
        if report["status"] != "ready":
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 1
        if not args.apply:
            print(render_project_resource_doc(report))
            return 0
        try:
            result = record_project_resources(
                args.project_root,
                report,
                apply=True,
                overwrite=args.overwrite,
            )
        except (FileExistsError, FileNotFoundError, ValueError) as exc:
            print(f"BLOCKER: {exc}")
            return 1
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"status: {report['status']}")
        print(f"host: {report['identity']['hostname'] or 'unknown'}")
        print(f"profile: {report['requested_profile'] or 'not specified'}")
        print(f"partitions: {len(report['scheduler']['partitions'])}")
        for item in report["blockers"]:
            print(f"BLOCKER: {item}")
        for item in report["warnings"]:
            print(f"WARNING: {item}")
    return 0 if report["status"] == "ready" else 1


if __name__ == "__main__":  # pragma: no cover - CLI boundary
    raise SystemExit(main())
