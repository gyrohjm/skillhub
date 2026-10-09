from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dft_contracts.local_config import config_dir, load_profile, preserve_private_files, read_private_json
from dft_contracts.privacy import findings, scan_index


def test_private_copy_permissions_conflict_and_repeat(tmp_path, monkeypatch):
    root = tmp_path / "private"
    monkeypatch.setenv("DFT_SKILLS_CONFIG_DIR", str(root))
    files = {"notes/cluster.md": b"private environment", "profiles.json": b'{"profiles": {}}'}
    assert preserve_private_files(files) == root
    assert preserve_private_files(files) == root
    assert root.stat().st_mode & 0o777 == 0o700
    assert (root / "notes").stat().st_mode & 0o777 == 0o700
    assert (root / "notes/cluster.md").stat().st_mode & 0o777 == 0o600
    with pytest.raises(ValueError, match="conflict"):
        preserve_private_files({"new.md": b"new", "profiles.json": b"conflict"})
    assert not (root / "new.md").exists()
    assert (root / "profiles.json").read_bytes() == files["profiles.json"]
    with pytest.raises(ValueError):
        preserve_private_files({"../escape": b"private"})


def test_private_dir_rejects_git_worktrees_and_symlink_escape(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").write_text("gitdir: elsewhere")
    monkeypatch.setenv("DFT_SKILLS_CONFIG_DIR", str(repo / "private"))
    with pytest.raises(ValueError, match="Git"):
        config_dir()
    root = tmp_path / "private"
    monkeypatch.setenv("DFT_SKILLS_CONFIG_DIR", str(root))
    preserve_private_files({"profiles.json": b'{"profiles": {}}'})
    (root / "escape").symlink_to(repo, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        preserve_private_files({"escape/private.json": b"secret"})
    with pytest.raises(ValueError):
        read_private_json("../outside.json")


def test_profile_validation_and_missing_dependency(tmp_path, monkeypatch):
    monkeypatch.setenv("DFT_SKILLS_CONFIG_DIR", str(tmp_path / "private"))
    assert load_profile("generic") == {}
    with pytest.raises(ValueError, match="Unknown"):
        load_profile("missing")
    path = preserve_private_files({"profiles.json": b"not JSON"}) / "profiles.json"
    with pytest.raises(ValueError, match="Invalid"):
        load_profile("generic")
    for resources in ({"nodes": True}, {"nodes": 0}, {"partition": 3}, {"unknown": 1}):
        path.write_text(json.dumps({"profiles": {"example": {"resources": resources}}}))
        with pytest.raises(ValueError):
            load_profile("example")
    path.chmod(0o644)
    with pytest.raises(ValueError, match="permissions"):
        load_profile("example")


def test_cli_profile_precedence_and_no_unknown_fallback(tmp_path, monkeypatch):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "dft-workflow/scripts"))
    from vwf.cli import resource_envelope, default_potcar_root, resolve_case_root
    monkeypatch.setenv("DFT_SKILLS_CONFIG_DIR", str(tmp_path / "private"))
    preserve_private_files({"profiles.json": json.dumps({"profiles": {"example": {
        "resources": {"nodes": 2, "partition": "example"},
        "potcar_root": "/opt/example/potentials", "project_root": str(tmp_path)
    }}}).encode()})
    args = argparse.Namespace(profile="example", nodes=3)
    resources = resource_envelope(args)
    assert resources["nodes"] == 3 and resources["partition"] == "example"
    assert resources["cpus_per_task"] == 1
    assert default_potcar_root("example") == Path("/opt/example/potentials")
    args.profile = "missing"
    with pytest.raises(ValueError, match="Unknown"):
        resource_envelope(args)
    explicit = argparse.Namespace(case_root=tmp_path, cluster="missing")
    assert resolve_case_root(explicit)[0] == tmp_path


def test_guard_reads_staged_bytes_and_redacts_matches(tmp_path):
    def git(*args):
        return subprocess.check_output(["git", "-C", str(tmp_path), *args])
    git("init", "-q")
    path = tmp_path / "dft-skills/notes.md"
    path.parent.mkdir()
    private_value = "fictional_identity_42"
    path.write_text(private_value)
    git("add", "dft-skills")
    path.write_text("safe working tree")
    results = scan_index(tmp_path, [private_value])
    assert results == [("dft-skills/notes.md", 1, "private environment value")]
    assert private_value not in str(results)
    git("add", "dft-skills")
    assert scan_index(tmp_path, [private_value]) == []
    path.write_text("/home/" + "fictional_person/run")
    git("add", "dft-skills")
    assert scan_index(tmp_path, [])[0][2] == "personal home path"
    git("rm", "--cached", "dft-skills/notes.md")
    assert scan_index(tmp_path, []) == []
    assert findings(("-----BEGIN " + "PRIVATE KEY-----").encode(), [])
    assert findings(json.dumps({"pass" + "word": "fictional_value_42"}).encode(), [])


def test_loopback_and_hostname_variable_are_not_private_endpoints():
    assert findings(b'url = "http://127.0.0.1:8765/ui"\n', []) == []
    assert findings(b'if parsed.hostname not in {"127.0.0.1", "localhost"}:\n', []) == []
    assert findings(b'HostName internal.cluster.invalid\n', []) == [(1, "SSH connection information")]
    private_endpoint = b'url = "http://' + b'10.10.' + b'10.10:8080"\n'
    assert findings(private_endpoint, []) == [(1, "network endpoint")]
    assert findings(b'localhost: "127.0.0.1:8765" ' + private_endpoint, []) == [(1, "network endpoint")]


def test_real_hook_blocks_staged_secret_even_after_working_tree_cleanup(tmp_path, monkeypatch):
    import shutil
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    package = Path(__file__).resolve().parents[1]
    destination = repo / "dft-skills/dft-contracts/dft_contracts"
    shutil.copytree(package / "dft_contracts", destination, ignore=shutil.ignore_patterns("__pycache__"))
    monkeypatch.setenv("DFT_SKILLS_CONFIG_DIR", str(tmp_path / "private"))
    hook = repo / ".git/hooks/pre-commit"
    shutil.copy2(package / "hooks/pre-commit", hook)
    hook.chmod(0o755)
    path = repo / "dft-skills/notes.md"
    path.write_text("/home/" + "fictional_person/work")
    subprocess.run(["git", "-C", str(repo), "add", "dft-skills"], check=True)
    path.write_text("safe working tree")
    result = subprocess.run([str(hook)], cwd=repo, capture_output=True, text=True)
    assert result.returncode == 1 and "personal home path" in result.stderr
    assert "fictional_person" not in result.stderr
    subprocess.run(["git", "-C", str(repo), "add", "dft-skills"], check=True)
    assert subprocess.run([str(hook)], cwd=repo, capture_output=True).returncode == 0
