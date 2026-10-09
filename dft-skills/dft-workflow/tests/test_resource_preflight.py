from __future__ import annotations

import sys
from pathlib import Path
import json
import re

import pytest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import resource_preflight as rp  # noqa: E402


class Result:
    def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def fake_runner(argv: list[str], *, cwd: str | None = None, env: dict[str, str] | None = None) -> Result:
    del cwd, env
    command = tuple(argv)
    if command == ("hostname", "-f"):
        return Result(0, "phoenix-login\n")
    if command == ("whoami",):
        return Result(0, "researcher\n")
    if command[:3] == ("sinfo", "-h", "-o"):
        return Result(0, "ExampleCPU|up|8|64000|2|(null)|example[1-2]|idle\n")
    if command[:3] == ("squeue", "-h", "-u"):
        return Result(0, "\n")
    if command[:3] == ("scontrol", "show", "partition"):
        return Result(0, "PartitionName=ExampleCPU\n")
    if command[:3] == ("scontrol", "show", "node"):
        return Result(0, "NodeName=example1 CPUs=8 RealMemory=64000 Gres=(null)\n")
    if command[:2] == ("bash", "-lc") and "module" in command[2]:
        return Result(0, "example_vasp\nquantum-espresso\n")
    if command[:2] == ("bash", "-lc") and "vasp_std" in command[2]:
        return Result(0, "/opt/vasp/vasp_std\n")
    if command[:2] == ("bash", "-lc") and "pw.x" in command[2]:
        return Result(0, "/opt/qe/bin/pw.x\n")
    if command[:2] == ("df", "-P"):
        return Result(0, "Filesystem 1024-blocks Used Available Capacity Mounted on\n/dev/mock 100 20 80 20% /home\n")
    return Result(127, "", "command not found\n")


def test_probe_is_read_only_and_reports_scheduler_resources() -> None:
    report = rp.probe_resources(runner=fake_runner, profile="phoenix", refresh_discovery=True)

    assert report["status"] == "ready"
    assert report["identity"]["hostname"] == "phoenix-login"
    assert report["scheduler"]["slurm_available"] is True
    assert report["scheduler"]["partitions"][0]["name"] == "ExampleCPU"
    assert report["scheduler"]["partitions"][0]["cpus_per_node"] == 8
    assert report["environment"]["executables"]["vasp_std"]["available"] is True
    assert report["environment"]["executables"]["pw.x"]["available"] is True
    assert report["requested_profile"] == "phoenix"


def test_probe_blocks_without_slurm_and_never_creates_an_environment() -> None:
    def missing_runner(argv: list[str], *, cwd: str | None = None, env: dict[str, str] | None = None) -> Result:
        del argv, cwd, env
        return Result(127, "", "missing\n")

    report = rp.probe_resources(runner=missing_runner, refresh_discovery=True)

    assert report["status"] == "blocked"
    assert report["scheduler"]["slurm_available"] is False
    assert report["blockers"]
    assert report["environment_creation"] == "forbidden_by_default"


def test_project_initialization_records_resource_doc_and_agents_pointer(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("# Project rules\n", encoding="utf-8")
    report = rp.probe_resources(
        runner=fake_runner, profile="phoenix", engine="vasp", refresh_discovery=True
    )

    result = rp.record_project_resources(tmp_path, report, apply=True)

    resource_doc = tmp_path / "docs/project-resources.md"
    agents = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert result["resource_document"] == str(resource_doc)
    assert resource_doc.is_file()
    assert "ExampleCPU" in resource_doc.read_text(encoding="utf-8")
    assert "docs/project-resources.md" in agents
    assert agents.count("dft-workflow:project-resources:start") == 1


def test_project_resource_doc_contains_one_structured_profile_contract() -> None:
    report = rp.probe_resources(
        runner=fake_runner, profile="phoenix", engine="vasp", refresh_discovery=True
    )

    text = rp.render_project_resource_doc(report)

    assert text.count("<!-- dft-workflow:profiles:start -->") == 1
    assert text.count("<!-- dft-workflow:profiles:end -->") == 1
    match = re.search(
        r"<!-- dft-workflow:profiles:start -->\s*```json\s*(\{.*?\})\s*```\s*<!-- dft-workflow:profiles:end -->",
        text,
        flags=re.DOTALL,
    )
    assert match is not None
    payload = json.loads(match.group(1))
    assert payload == {
        "schema": "dft.project-resources.v1",
        "cluster": "phoenix-login",
        "scheduler": "slurm",
        "profiles": {},
    }


def test_default_runner_decodes_cluster_output_as_utf8_with_replacement(monkeypatch) -> None:
    captured: dict = {}

    def fake_subprocess_run(*args, **kwargs):
        captured.update(kwargs)
        return Result(0, "ok\n", "")

    monkeypatch.setattr(rp.subprocess, "run", fake_subprocess_run)
    result = rp._run_command(["hostname", "-f"])

    assert result.returncode == 0
    assert captured["encoding"] == "utf-8"
    assert captured["errors"] == "replace"


def test_source_script_profile_is_probed_after_activation_not_as_a_module() -> None:
    profile = {
        "executable": "pw.x",
        "environment": {
            "method": "source-script",
            "availability_probe": "test -r /opt/qe/env.sh",
            "source_command": "source /opt/qe/env.sh",
            "verify_command": "command -v pw.x",
            "documentation_url": "https://cluster.example/qe",
        },
    }

    shell_commands: list[str] = []

    def source_runner(argv: list[str], *, cwd=None, env=None) -> Result:
        command = tuple(argv)
        if command[:2] == ("bash", "-lc"):
            shell = command[2]
            shell_commands.append(shell)
            if "source /opt/qe/env.sh" in shell and "command -v pw.x" in shell:
                return Result(0, "/opt/qe/bin/pw.x\n")
            return Result(127, "", "not available before source\n")
        return fake_runner(argv, cwd=cwd, env=env)

    report = rp.probe_resources(
        runner=source_runner,
        profile="source_qe",
        engine="quantum-espresso",
        activation_profile=profile,
        refresh_discovery=True,
    )

    assert report["status"] == "ready"
    assert report["environment"]["activation"]["method"] == "source-script"
    assert report["environment"]["activation"]["available"] is True
    assert report["environment"]["executables"]["pw.x"]["available"] is True
    assert report["environment"]["executables"]["pw.x"]["path"] == "/opt/qe/bin/pw.x"
    assert "required executable is unavailable: pw.x" not in report["blockers"]
    assert not any("module " in command for command in shell_commands)
    assert not any(command == "command -v pw.x" for command in shell_commands)


def test_module_init_script_precedes_module_probe_load_and_verification() -> None:
    profile = {
        "executable": "vasp_std",
        "environment": {
            "method": "modules",
            "module_init": "source /opt/example/modules/module.sh",
            "purge": False,
            "modules": ["vasp/6.4.2"],
            "availability_probe": "module avail vasp",
            "verify_command": "command -v vasp_std",
            "documentation_url": "https://example.org/software",
        },
    }
    activation_commands: list[str] = []

    def module_init_runner(argv: list[str], *, cwd=None, env=None) -> Result:
        command = tuple(argv)
        if command[:2] == ("bash", "-lc"):
            shell = command[2]
            if "source /opt/example/modules/module.sh" in shell:
                activation_commands.append(shell)
                return Result(0, "/opt/example/vasp_std\n")
            if "module" in shell or "vasp_std" in shell:
                return Result(127, "", "requires module init\n")
        return fake_runner(argv, cwd=cwd, env=env)

    report = rp.probe_resources(
        runner=module_init_runner,
        profile="paratera_vasp",
        engine="vasp",
        activation_profile=profile,
        refresh_discovery=True,
    )

    assert report["status"] == "ready"
    command = activation_commands[0]
    assert command.index("source /opt/example/modules/module.sh") < command.index(
        "module avail vasp"
    )
    assert command.index("module avail vasp") < command.index("module load vasp/6.4.2")
    assert command.index("module load vasp/6.4.2") < command.index("command -v vasp_std")


def test_cli_loads_approved_activation_profile(monkeypatch, tmp_path: Path) -> None:
    captured: dict = {}
    approved = {"engine": "quantum-espresso", "environment": {"method": "modules"}}

    def fake_load(project_root, resource_document, profile_id, engine):
        captured["load"] = (project_root, resource_document, profile_id, engine)
        return approved, {}, tmp_path / "docs/project-resources.md"

    def fake_probe_resources(**kwargs):
        captured["probe"] = kwargs
        return {"status": "ready", "blockers": [], "warnings": []}

    monkeypatch.setattr(rp, "load_resource_profile", fake_load)
    monkeypatch.setattr(rp, "probe_resources", fake_probe_resources)

    rc = rp.main(
        [
            "--project-root",
            str(tmp_path),
            "--profile",
            "nebula_qe",
            "--engine",
            "quantum-espresso",
            "--json",
        ]
    )

    assert rc == 0
    assert captured["load"][2:] == ("nebula_qe", "quantum-espresso")
    assert str(captured["load"][1]).replace("\\", "/") == "docs/project-resources.md"
    assert captured["probe"]["activation_profile"] is approved


def test_silent_executable_verification_blocks_without_crashing() -> None:
    profile = {
        "executable": "pw.x",
        "environment": {
            "method": "source-script",
            "availability_probe": "test -r /opt/qe/env.sh",
            "source_command": "source /opt/qe/env.sh",
            "verify_command": "command -v pw.x",
            "documentation_url": "https://cluster.example/qe",
        },
    }

    def silent_runner(argv: list[str], *, cwd=None, env=None) -> Result:
        if tuple(argv)[:2] == ("bash", "-lc"):
            return Result(0, "")
        return fake_runner(argv, cwd=cwd, env=env)

    report = rp.probe_resources(
        runner=silent_runner,
        profile="silent_qe",
        engine="quantum-espresso",
        activation_profile=profile,
        refresh_discovery=True,
    )

    assert report["status"] == "blocked"
    assert "approved environment activation failed: source-script" in report["blockers"]


def test_targeted_profile_blocks_on_partition_or_cpu_drift() -> None:
    profile = {
        "executable": "vasp_std",
        "partition": "MissingPartition",
        "nodes": 1,
        "ntasks_per_node": 120,
        "cpus_per_task": 1,
        "environment": {
            "method": "modules",
            "purge": False,
            "modules": ["vasp/6.4.2"],
            "availability_probe": "module avail vasp",
            "verify_command": "command -v vasp_std",
        },
    }

    report = rp.probe_resources(
        runner=fake_runner,
        profile="drifted_vasp",
        engine="vasp",
        activation_profile=profile,
        refresh_discovery=True,
    )

    assert report["status"] == "blocked"
    assert "approved partition is unavailable: MissingPartition" in report["blockers"]


def test_lightweight_preflight_runs_only_the_four_approved_checks() -> None:
    profile = {
        "partition": "compute",
        "executable": "vasp_std",
        "activation_command": "source /opt/vasp/env.sh",
    }
    calls: list[tuple[str, ...]] = []

    def runner(argv: list[str], *, cwd=None, env=None) -> Result:
        del cwd, env
        command = tuple(argv)
        calls.append(command)
        if command[:2] == ("bash", "-lc") and "DFT_PREFLIGHT_V1" in command[2]:
            return Result(
                0,
                rp.format_batched_probe_output(
                    {
                        "scheduler_command": {"status": "passed", "returncode": 0, "detail": "/usr/bin/sbatch"},
                        "target_partition": {"status": "passed", "returncode": 0, "detail": "compute|up"},
                        "approved_activation": {"status": "passed", "returncode": 0, "detail": ""},
                        "approved_executable": {"status": "passed", "returncode": 0, "detail": "/opt/vasp/bin/vasp_std"},
                    }
                ),
            )
        return Result(127, "", "unexpected command")

    report = rp.lightweight_preflight(
        profile,
        runner,
        checked_at="2026-08-31T00:00:00+00:00",
    )

    assert report["cache_status"] == "ready"
    assert report["checked_at"] == "2026-08-31T00:00:00+00:00"
    assert all(status["status"] == "passed" for status in report["checks"].values())
    assert len(calls) == 1
    assert calls[0][:2] == ("bash", "-lc")
    assert calls[0][2].count("source /opt/vasp/env.sh") == 1
    assert calls[0][2].count("command -v vasp_std") == 1


def test_lightweight_preflight_checks_executable_inside_activated_shell() -> None:
    profile = {
        "partition": "compute",
        "executable": "vasp_std",
        "activation_command": "source /opt/vasp/env.sh",
    }
    calls: list[tuple[str, ...]] = []

    def runner(argv: list[str], *, cwd=None, env=None) -> Result:
        del cwd, env
        command = tuple(argv)
        calls.append(command)
        if command[:2] == ("bash", "-lc") and "DFT_PREFLIGHT_V1" in command[2]:
            return Result(
                0,
                rp.format_batched_probe_output(
                    {
                        "scheduler_command": {"status": "passed", "returncode": 0, "detail": "/usr/bin/sbatch"},
                        "target_partition": {"status": "passed", "returncode": 0, "detail": "compute|up"},
                        "approved_activation": {"status": "passed", "returncode": 0, "detail": "activated"},
                        "approved_executable": {"status": "passed", "returncode": 0, "detail": "/opt/vasp/bin/vasp_std"},
                    }
                ),
            )
        return Result(127, "", "executable is only available after activation")

    report = rp.lightweight_preflight(profile, runner)

    assert report["cache_status"] == "ready"
    assert len(calls) == 1
    assert calls[0][:2] == ("bash", "-lc")
    assert calls[0][2].index("source /opt/vasp/env.sh") < calls[0][2].index(
        "command -v vasp_std"
    )


@pytest.mark.parametrize("executable", ["vasp_std; touch /tmp/pwned", "vasp std", "../vasp_std"])
def test_lightweight_preflight_rejects_unsafe_executable(executable: str) -> None:
    profile = {
        "partition": "compute",
        "executable": executable,
        "activation_command": "source /opt/vasp/env.sh",
    }

    with pytest.raises(rp.WorkflowError, match="executable"):
        rp.lightweight_preflight(profile, lambda *args, **kwargs: Result(0))


def test_probe_resources_uses_lightweight_path_without_refresh_discovery() -> None:
    profile = {
        "partition": "compute",
        "executable": "vasp_std",
        "activation_command": "source /opt/vasp/env.sh",
    }
    calls: list[tuple[str, ...]] = []

    def runner(argv: list[str], *, cwd=None, env=None) -> Result:
        del cwd, env
        command = tuple(argv)
        calls.append(command)
        if command[:2] == ("bash", "-lc") and "DFT_PREFLIGHT_V1" in command[2]:
            return Result(
                0,
                rp.format_batched_probe_output(
                    {
                        "scheduler_command": {"status": "passed", "returncode": 0, "detail": "/usr/bin/sbatch"},
                        "target_partition": {"status": "passed", "returncode": 0, "detail": "compute|up"},
                        "approved_activation": {"status": "passed", "returncode": 0, "detail": ""},
                        "approved_executable": {"status": "passed", "returncode": 0, "detail": "/opt/vasp/bin/vasp_std"},
                    }
                ),
            )
        return Result(127, "", "broad discovery is not allowed")

    report = rp.probe_resources(
        runner=runner,
        profile="compute_vasp",
        engine="vasp",
        activation_profile=profile,
    )

    assert report["status"] == "ready"
    assert len(calls) == 1
    assert calls[0][:2] == ("bash", "-lc")


def test_ready_preflight_cache_is_loaded_from_project_dft_directory(tmp_path: Path) -> None:
    profile = {
        "partition": "compute",
        "executable": "vasp_std",
        "activation_command": "source /opt/vasp/env.sh",
    }
    record = rp.lightweight_preflight(
        profile,
        lambda argv, **kwargs: Result(0, rp.format_batched_probe_output({name: {"returncode": 0, "detail": "compute|up" if name == "target_partition" else "/ok"} for name in rp._BATCH_NAMES})),
        checked_at="2026-08-31T00:00:00+00:00",
    )
    cache_path = tmp_path / ".dft/resource-profile.json"
    cache_path.parent.mkdir()
    cache_path.write_text(json.dumps(record), encoding="utf-8")

    assert rp.load_cached_preflight(tmp_path) == record


def test_preflight_invalidation_rejects_unapproved_reason(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="invalidation reason"):
        rp.invalidate_preflight(tmp_path, "manual_refresh")


@pytest.mark.parametrize(
    "reason",
    [
        "scheduler_rejection",
        "partition_missing",
        "activation_failure",
        "executable_failure",
        "repeated_environment_failure",
        "agent_detected_cluster_drift",
    ],
)
def test_preflight_invalidation_persists_each_allowed_reason(
    tmp_path: Path, reason: str
) -> None:
    profile = {
        "partition": "compute",
        "executable": "vasp_std",
        "activation_command": "source /opt/vasp/env.sh",
    }
    record = rp.lightweight_preflight(
        profile,
        lambda argv, **kwargs: Result(0, rp.format_batched_probe_output({name: {"returncode": 0, "detail": "compute|up" if name == "target_partition" else "/ok"} for name in rp._BATCH_NAMES})),
        checked_at="2026-08-31T00:00:00+00:00",
    )
    cache_path = tmp_path / ".dft/resource-profile.json"
    cache_path.parent.mkdir()
    cache_path.write_text(json.dumps(record), encoding="utf-8")

    invalidated = rp.invalidate_preflight(tmp_path, reason)

    assert invalidated["cache_status"] == "invalidated"
    assert invalidated["invalidation_reason"] == reason
    assert rp.load_cached_preflight(tmp_path) == invalidated
