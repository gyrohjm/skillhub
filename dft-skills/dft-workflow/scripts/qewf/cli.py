#!/usr/bin/env python3
"""Register, review, submit, and inspect prebuilt QE tasks safely."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable


CONTRACTS_ROOT = Path(__file__).resolve().parents[3] / "dft-contracts"
if str(CONTRACTS_ROOT) not in sys.path:
    sys.path.insert(0, str(CONTRACTS_ROOT))
from dft_contracts import validate_document


SPEC_NAME = "task_spec.json"
STATE_NAME = "state.json"
REVIEW_NAME = "submission_review.dat"
APPROVAL_NAME = "submission_approval.json"
JOB_ID_RE = re.compile(r"Submitted batch job\s+(\d+)")
QE_EXECUTABLE_RE = re.compile(r"\b(pw|ph|q2r|matdyn|dynmat|projwfc|bands|dos|pp)\.x\b")
FATAL_RE = re.compile(
    r"(?im)(%+\s*Error in routine|convergence NOT achieved|MPI_ABORT|out of memory|"
    r"DUE TO TIME LIMIT|CANCELLED AT|Maximum CPU time exceeded)"
)


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def verify_design_approval(approval_path: Path, matrix_id: str, stage: str) -> dict[str, Any]:
    approval = read_json(approval_path)
    required = {
        "schema_version", "approval_type", "status", "design_id", "revision", "scope",
        "design_file", "design_sha256", "computation_plan_file", "computation_plan_sha256",
    }
    missing = sorted(required - set(approval))
    if missing:
        raise RuntimeError(f"design approval is missing fields: {missing}")
    if approval["schema_version"] != 1 or approval["approval_type"] != "scientific_design" or approval["status"] != "approved":
        raise RuntimeError("design approval header is invalid")
    if matrix_id not in approval["scope"]:
        raise RuntimeError(f"matrix {matrix_id} is outside the approved scope")
    design_name = Path(str(approval["design_file"]))
    plan_name = Path(str(approval["computation_plan_file"]))
    if design_name.name != str(design_name) or plan_name.name != str(plan_name):
        raise RuntimeError("design snapshot file names must not contain directories")
    design_path = approval_path.parent / design_name
    plan_path = approval_path.parent / plan_name
    if sha256_file(design_path) != approval["design_sha256"]:
        raise RuntimeError("calculation design hash does not match approval")
    if sha256_file(plan_path) != approval["computation_plan_sha256"]:
        raise RuntimeError("computation plan hash does not match approval")
    design = read_json(design_path)
    if design.get("schema_version") != 2 or design.get("status") != "ready_for_review":
        raise RuntimeError("QE production requires a schema-v2 ready_for_review design")
    if design.get("design_id") != approval["design_id"] or design.get("revision") != approval["revision"]:
        raise RuntimeError("design identity does not match approval")
    matrices = {item.get("id"): item for item in design.get("calculation_matrix", [])}
    matrix = matrices.get(matrix_id)
    if not matrix or stage not in matrix.get("stages", []):
        raise RuntimeError(f"stage {stage} is not approved for matrix {matrix_id}")
    envelopes = [
        item for item in design.get("engine_stage_envelopes", [])
        if item.get("matrix_id") == matrix_id and item.get("engine") == "quantum-espresso"
    ]
    if len(envelopes) != 1 or stage not in envelopes[0].get("completion_gates", {}):
        raise RuntimeError("approved matrix lacks one matching Quantum ESPRESSO stage envelope")
    return {
        "approval_path": str(approval_path),
        "approval_sha256": sha256_file(approval_path),
        "design_id": approval["design_id"],
        "revision": approval["revision"],
        "matrix_id": matrix_id,
        "stage": stage,
        "design_file": str(design_path),
        "design_sha256": approval["design_sha256"],
        "computation_plan_file": str(plan_path),
        "computation_plan_sha256": approval["computation_plan_sha256"],
        "engine_envelope": envelopes[0],
    }


def require_file(task_dir: Path, value: str, label: str) -> Path:
    path = (task_dir / value).resolve()
    if not path.is_file() or path.stat().st_size == 0:
        raise RuntimeError(f"{label} is missing or empty: {value}")
    return path


def rel_to_task(task_dir: Path, path: Path) -> str:
    try:
        return str(path.relative_to(task_dir.resolve()))
    except ValueError:
        return str(Path("..") / path.relative_to(task_dir.resolve().parent))


def collect_hashes(task_dir: Path, names: Iterable[str], label: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for name in names:
        path = require_file(task_dir, name, label)
        result[name] = sha256_file(path)
    return result


def parse_slurm(job_text: str) -> dict[str, Any]:
    directives: dict[str, str | bool] = {}
    modules: list[str] = []
    commands: list[str] = []
    for raw in job_text.splitlines():
        line = raw.strip()
        if line.startswith("#SBATCH"):
            body = line[len("#SBATCH") :].strip()
            parts = shlex.split(body)
            if not parts:
                continue
            token = parts[0]
            if "=" in token:
                key, value = token.split("=", 1)
            elif len(parts) > 1:
                key, value = token, parts[1]
            else:
                key, value = token, True
            directives[key] = value
        elif line.startswith("module load "):
            modules.append(line[len("module load ") :].strip())
        elif line and not line.startswith("#") and QE_EXECUTABLE_RE.search(line):
            commands.append(line)

    def first(*keys: str) -> str | bool | None:
        for key in keys:
            if key in directives:
                return directives[key]
        return None

    return {
        "job_name": first("-J", "--job-name"),
        "partition": first("-p", "--partition"),
        "qos": first("-q", "--qos"),
        "nodes": first("-N", "--nodes"),
        "ntasks": first("-n", "--ntasks"),
        "ntasks_per_node": first("--ntasks-per-node"),
        "cpus_per_task": first("-c", "--cpus-per-task"),
        "walltime": first("-t", "--time"),
        "modules": modules,
        "qe_commands": commands,
    }


def validate_job(resources: dict[str, Any], cluster: str) -> None:
    from dft_contracts.local_config import load_profile
    load_profile(cluster)  # Explicit prebuilt script values remain authoritative.
    missing = [key for key in ("job_name", "partition", "nodes", "ntasks") if not resources.get(key)]
    if missing:
        raise RuntimeError("missing Slurm fields: " + ", ".join(missing))
    if not resources["qe_commands"]:
        raise RuntimeError("job script contains no recognized Quantum ESPRESSO executable")
    if not any("qe" in module.lower() for module in resources["modules"]):
        raise RuntimeError("job script contains no Quantum ESPRESSO module load")


def qe_summary(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8", errors="replace")
    wanted = (
        "calculation", "prefix", "pseudo_dir", "outdir", "input_dft", "ecutwfc",
        "ecutrho", "occupations", "smearing", "degauss", "conv_thr", "tr2_ph",
        "ldisp", "nq1", "nq2", "nq3", "electron_phonon", "asr", "zasr",
    )
    result: dict[str, str] = {}
    for key in wanted:
        match = re.search(rf"(?im)^\s*{re.escape(key)}\s*=\s*([^\n,!/]+)", text)
        if match:
            result[key] = match.group(1).strip().strip("'\"")
    kpoints = re.search(r"(?ims)^\s*K_POINTS\s+automatic\s*\n\s*([^\n]+)", text)
    if kpoints:
        result["k_points_automatic"] = " ".join(kpoints.group(1).split())
    species = re.search(r"(?ims)^\s*ATOMIC_SPECIES\s*\n(.*?)(?:\n\s*\n|\n\s*[A-Z_]+(?:\s+\w+)?\s*\n)", text)
    if species:
        result["atomic_species"] = " | ".join(
            " ".join(line.split()) for line in species.group(1).splitlines() if line.strip()
        )
    return result


def resource_hash(resources: dict[str, Any], job_hash: str) -> str:
    payload = json.dumps({"resources": resources, "job_sha256": job_hash}, sort_keys=True)
    return sha256_text(payload)


def render_review(spec: dict[str, Any], task_dir: Path) -> str:
    lines = [
        "Quantum ESPRESSO submission review",
        f"task_id: {spec['task_id']}",
        f"matrix_id: {spec['matrix_id']}",
        "engine: quantum-espresso",
        "backend: qewf",
        f"cluster: {spec['cluster']}",
        f"remote_host: {spec['remote']['host']}",
        f"remote_dir: {spec['remote']['directory']}",
        f"design_approval: {spec['design']['approval_path']}",
        f"design_approval_sha256: {spec['design']['approval_sha256']}",
        f"design_id: {spec['design']['design_id']}",
        f"design_revision: {spec['design']['revision']}",
        f"design_sha256: {spec['design']['design_sha256']}",
        f"computation_plan_sha256: {spec['design']['computation_plan_sha256']}",
        f"preapproved_by_workflow: {str(spec['preapproved_by_workflow']).lower()}",
        "",
        "Inputs:",
    ]
    for name, digest in spec["input_sha256"].items():
        lines.append(f"  {name}: {digest}")
        summary = qe_summary(require_file(task_dir, name, "QE input"))
        for key, value in summary.items():
            lines.append(f"    {key}: {value}")
        if name.endswith(".in"):
            lines.append("    exact_input_begin")
            lines.extend(f"      {line}" for line in require_file(task_dir, name, "QE input").read_text(encoding="utf-8").splitlines())
            lines.append("    exact_input_end")
    lines.extend(["", "Pseudopotentials:"])
    for name, digest in spec["pseudopotential_sha256"].items():
        lines.append(f"  {name}: {digest}")
    lines.extend(["", "Resources:"])
    for key, value in spec["resources"].items():
        lines.append(f"  {key}: {json.dumps(value, ensure_ascii=False)}")
    lines.extend([
        f"  resource_hash: {spec['resource_hash']}",
        "",
        f"job_script: {spec['job_script']}",
        f"job_sha256: {spec['input_sha256'][spec['job_script']]}",
        f"structure_source: {spec['structure']['path']}",
        f"structure_sha256: {spec['structure']['sha256']}",
        f"expected_outputs: {json.dumps(spec['expected_outputs'])}",
        f"required_outputs: {json.dumps(spec['required_outputs'])}",
        "approval_gate: exact review/input/resource/design hashes must match",
    ])
    return "\n".join(lines) + "\n"


def current_hashes(spec: dict[str, Any], task_dir: Path) -> tuple[dict[str, str], dict[str, str], dict[str, Any], str]:
    inputs = collect_hashes(task_dir, spec["input_sha256"].keys(), "input")
    pseudos = collect_hashes(task_dir, spec["pseudopotential_sha256"].keys(), "pseudopotential")
    job_path = require_file(task_dir, spec["job_script"], "job script")
    resources = parse_slurm(job_path.read_text(encoding="utf-8"))
    validate_job(resources, spec["cluster"])
    return inputs, pseudos, resources, resource_hash(resources, inputs[spec["job_script"]])


def verify_snapshot(spec: dict[str, Any], task_dir: Path) -> None:
    inputs, pseudos, resources, current_resource_hash = current_hashes(spec, task_dir)
    if inputs != spec["input_sha256"]:
        raise RuntimeError("input hashes changed since registration")
    if pseudos != spec["pseudopotential_sha256"]:
        raise RuntimeError("pseudopotential hashes changed since registration")
    if resources != spec["resources"] or current_resource_hash != spec["resource_hash"]:
        raise RuntimeError("resource envelope changed since registration")
    approval = Path(spec["design"]["approval_path"])
    verified = verify_design_approval(approval, spec["matrix_id"], spec["stage"])
    if verified["approval_sha256"] != spec["design"]["approval_sha256"]:
        raise RuntimeError("design approval changed since registration")
    structure = require_file(task_dir, spec["structure"]["path"], "structure source")
    if sha256_file(structure) != spec["structure"]["sha256"]:
        raise RuntimeError("structure source changed since registration")


def register(args: argparse.Namespace) -> int:
    task_dir = args.task_dir.resolve()
    task_dir.mkdir(parents=True, exist_ok=True)
    if (task_dir / STATE_NAME).exists() and not args.replace_records:
        raise RuntimeError(f"{STATE_NAME} already exists; pass --replace-records to regenerate before submission")
    input_names = list(dict.fromkeys([*args.input, args.job_script]))
    inputs = collect_hashes(task_dir, input_names, "input")
    pseudos = collect_hashes(task_dir, args.pseudo, "pseudopotential")
    approval_path = Path(args.design_approval).expanduser().resolve()
    design = verify_design_approval(approval_path, args.matrix_id, args.stage)
    structure = require_file(task_dir, args.structure, "structure source")
    resources = parse_slurm(require_file(task_dir, args.job_script, "job script").read_text(encoding="utf-8"))
    validate_job(resources, args.cluster)
    spec: dict[str, Any] = {
        "schema_version": 2,
        "contract": "dft.task-spec.v2",
        "engine": "quantum-espresso",
        "backend": "qewf",
        "task_kind": args.stage,
        "task_dir": str(task_dir),
        "task_id": args.task_id,
        "matrix_id": args.matrix_id,
        "stage": args.stage,
        "task_class": args.task_class,
        "cluster": args.cluster,
        "remote": {"host": args.remote_host, "directory": args.remote_dir},
        "design": design,
        "structure": {"path": args.structure, "sha256": sha256_file(structure)},
        "preapproved_by_workflow": args.preapproved_by_workflow,
        "input_sha256": inputs,
        "input_hashes": inputs,
        "pseudopotential_sha256": pseudos,
        "pseudopotential_components": [
            {"path": name, "sha256": digest}
            for name, digest in sorted(pseudos.items())
        ],
        "parent_fingerprints": [],
        "resources": resources,
        "resource_hash": resource_hash(resources, inputs[args.job_script]),
        "job_script": args.job_script,
        "expected_outputs": args.output,
        "required_outputs": args.required_output,
        "recovery": {
            "allowed_actions": ["resubmit_unchanged"] if args.max_recovery_attempts else [],
            "max_attempts": args.max_recovery_attempts,
        },
        "created_at": now_iso(),
    }
    contract_errors = validate_document("task-spec-v2", spec)
    if contract_errors:
        raise RuntimeError("task_spec violates dft.task-spec.v2: " + "; ".join(contract_errors))
    write_json(task_dir / SPEC_NAME, spec)
    write_json(task_dir / STATE_NAME, {
        "schema_version": 1,
        "engine": "quantum-espresso",
        "backend": "qewf",
        "task_id": args.task_id,
        "status": "reviewed" if args.preapproved_by_workflow else "registered",
        "job_id": None,
        "attempt": 0,
        "updated_at": now_iso(),
    })
    review = render_review(spec, task_dir)
    (task_dir / REVIEW_NAME).write_text(review, encoding="utf-8")
    approval_path = task_dir / APPROVAL_NAME
    if approval_path.exists():
        approval_path.unlink()
    print(review, end="")
    return 0


def review(args: argparse.Namespace) -> int:
    task_dir = args.task_dir.resolve()
    spec = read_json(task_dir / SPEC_NAME)
    verify_snapshot(spec, task_dir)
    review_text = render_review(spec, task_dir)
    (task_dir / REVIEW_NAME).write_text(review_text, encoding="utf-8")
    print(review_text, end="")
    if args.approve:
        write_json(task_dir / APPROVAL_NAME, {
            "schema_version": 1,
            "engine": "quantum-espresso",
            "backend": "qewf",
            "task_id": spec["task_id"],
            "review_sha256": sha256_text(review_text),
            "input_sha256": spec["input_sha256"],
            "pseudopotential_sha256": spec["pseudopotential_sha256"],
            "resource_hash": spec["resource_hash"],
            "design_sha256": spec["design"]["approval_sha256"],
            "approved_at": now_iso(),
        })
        print(f"[approved] {task_dir / APPROVAL_NAME}")
    return 0


def verify_approval(spec: dict[str, Any], task_dir: Path) -> None:
    approval_path = task_dir / APPROVAL_NAME
    if not approval_path.is_file():
        raise RuntimeError("missing submission_approval.json; run review --approve")
    approval = read_json(approval_path)
    review_text = (task_dir / REVIEW_NAME).read_text(encoding="utf-8")
    expected = {
        "review_sha256": sha256_text(review_text),
        "input_sha256": spec["input_sha256"],
        "pseudopotential_sha256": spec["pseudopotential_sha256"],
        "resource_hash": spec["resource_hash"],
        "design_sha256": spec["design"]["approval_sha256"],
    }
    for key, value in expected.items():
        if approval.get(key) != value:
            raise RuntimeError(f"approval mismatch: {key}")


def remote_preflight_command(spec: dict[str, Any]) -> str:
    files = [*spec["input_sha256"].items(), *spec["pseudopotential_sha256"].items()]
    checks = [f"test -s {shlex.quote(path)}" for path, _ in files]
    checks.extend(
        f"test \"$(sha256sum {shlex.quote(path)} | awk '{{print $1}}')\" = {shlex.quote(digest)}"
        for path, digest in files
    )
    checks.append(f"sbatch {shlex.quote(spec['job_script'])}")
    return "set -euo pipefail; cd " + shlex.quote(spec["remote"]["directory"]) + "; " + "; ".join(checks)


def submit(args: argparse.Namespace) -> int:
    task_dir = args.task_dir.resolve()
    spec = read_json(task_dir / SPEC_NAME)
    state = read_json(task_dir / STATE_NAME)
    if state.get("job_id") and not args.resubmit:
        raise RuntimeError(f"task already has job_id={state['job_id']}; pass --resubmit only for an approved recovery")
    verify_snapshot(spec, task_dir)
    verify_approval(spec, task_dir)
    command = [args.ssh, spec["remote"]["host"], remote_preflight_command(spec)]
    if args.dry_run:
        print(shlex.join(command))
        return 0
    result = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != 0:
        raise RuntimeError(f"remote submit failed: {result.stderr.strip() or result.stdout.strip()}")
    match = JOB_ID_RE.search(result.stdout)
    if not match:
        raise RuntimeError(f"cannot parse Slurm job id: {result.stdout.strip()}")
    job_id = match.group(1)
    state.update({"status": "submitted", "job_id": job_id, "submitted_at": now_iso(), "updated_at": now_iso()})
    write_json(task_dir / STATE_NAME, state)
    write_json(task_dir / "submission.json", {
        "schema_version": 1,
        "engine": "quantum-espresso",
        "backend": "qewf",
        "task_id": spec["task_id"],
        "job_id": job_id,
        "remote_host": spec["remote"]["host"],
        "remote_dir": spec["remote"]["directory"],
        "submitted_at": state["submitted_at"],
        "review_sha256": sha256_file(task_dir / REVIEW_NAME),
    })
    print(f"Submitted batch job {job_id}")
    return 0


def status(args: argparse.Namespace) -> int:
    task_dir = args.task_dir.resolve()
    spec = read_json(task_dir / SPEC_NAME)
    state = read_json(task_dir / STATE_NAME)
    job_id = state.get("job_id")
    if not job_id:
        raise RuntimeError("task has no recorded job id")
    remote = (
        f"squeue -h -j {shlex.quote(str(job_id))} -o '%i|%T|%M|%R'; "
        f"sacct -n -X -j {shlex.quote(str(job_id))} -o JobIDRaw,State,Elapsed,ExitCode -P | head -n 1"
    )
    result = subprocess.run([args.ssh, spec["remote"]["host"], remote], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != 0:
        raise RuntimeError(f"remote status failed: {result.stderr.strip()}")
    print(result.stdout, end="")
    if args.write:
        queue_line = next((line for line in result.stdout.splitlines() if "|" in line), "")
        scheduler_state = queue_line.split("|")[1] if queue_line and len(queue_line.split("|")) > 1 else "UNKNOWN"
        state.update({"scheduler_state": scheduler_state, "updated_at": now_iso()})
        if scheduler_state in {"PENDING", "RUNNING", "COMPLETING"}:
            state["status"] = scheduler_state.lower()
        write_json(task_dir / STATE_NAME, state)
    return 0


def parse_outputs(args: argparse.Namespace) -> int:
    task_dir = args.task_dir.resolve()
    spec = read_json(task_dir / SPEC_NAME)
    state = read_json(task_dir / STATE_NAME)
    steps: list[dict[str, Any]] = []
    fatal = False
    complete = True
    scheduler_log: dict[str, Any] | None = None
    job_id = state.get("job_id")
    if job_id:
        slurm_path = task_dir / f"slurm-{job_id}.out"
        if slurm_path.is_file():
            slurm_text = slurm_path.read_text(encoding="utf-8", errors="replace")
            slurm_fatal = FATAL_RE.search(slurm_text)
            scheduler_log = {
                "path": slurm_path.name,
                "fatal": slurm_fatal.group(0) if slurm_fatal else None,
            }
            fatal = slurm_fatal is not None
    for name in spec["expected_outputs"]:
        path = task_dir / name
        if not path.is_file() or path.stat().st_size == 0:
            steps.append({"path": name, "status": "missing", "job_done": False, "fatal": None})
            complete = False
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        fatal_match = FATAL_RE.search(text)
        job_done = "JOB DONE" in text
        steps.append({
            "path": name,
            "status": "failed" if fatal_match else ("complete" if job_done else "truncated"),
            "job_done": job_done,
            "fatal": fatal_match.group(0) if fatal_match else None,
        })
        fatal = fatal or fatal_match is not None
        complete = complete and job_done and fatal_match is None
    required: list[dict[str, Any]] = []
    for name in spec["required_outputs"]:
        path = task_dir / name
        nonempty = path.is_file() and path.stat().st_size > 0
        required.append({"path": name, "nonempty": nonempty})
        complete = complete and nonempty
    verdict = "failed" if fatal else ("completed" if complete else "incomplete")
    report = {
        "schema_version": 1,
        "engine": "quantum-espresso",
        "backend": "qewf",
        "task_id": spec["task_id"],
        "workflow_verdict": verdict,
        "scientific_verdict": "not_evaluated",
        "steps": steps,
        "required_outputs": required,
        "scheduler_log": scheduler_log,
        "parsed_at": now_iso(),
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    if args.write:
        write_json(task_dir / "parse.json", report)
        state.update({"status": verdict, "parse_verdict": verdict, "updated_at": now_iso()})
        write_json(task_dir / STATE_NAME, state)
    return 0 if verdict == "completed" else 1


def recover(args: argparse.Namespace) -> int:
    task_dir = args.task_dir.resolve()
    spec = read_json(task_dir / SPEC_NAME)
    state = read_json(task_dir / STATE_NAME)
    if args.action != "resubmit_unchanged" or args.action not in spec["recovery"]["allowed_actions"]:
        raise RuntimeError("only resubmit_unchanged is allowed")
    if state.get("status") not in {"failed", "blocked", "incomplete"}:
        raise RuntimeError("recovery is allowed only for a failed, blocked, or incomplete task")
    attempt = int(state.get("attempt", 0))
    if attempt >= int(spec["recovery"]["max_attempts"]):
        raise RuntimeError("recovery attempt limit reached")
    verify_snapshot(spec, task_dir)
    verify_approval(spec, task_dir)
    archive = task_dir / "recovery_attempts" / f"attempt-{attempt + 1}"
    output_names = [*spec["expected_outputs"], *spec["required_outputs"]]
    if args.dry_run:
        print(f"would archive outputs to {archive} and resubmit unchanged")
        return 0
    archive.mkdir(parents=True, exist_ok=False)
    for name in output_names:
        source = task_dir / name
        if source.is_file() and source.resolve().parent == task_dir:
            shutil.move(str(source), str(archive / source.name))
    state.update({"status": "approved", "job_id": None, "attempt": attempt + 1, "updated_at": now_iso()})
    write_json(task_dir / STATE_NAME, state)
    submit_args = argparse.Namespace(task_dir=task_dir, ssh=args.ssh, dry_run=False, resubmit=True)
    return submit(submit_args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="qewf")
    sub = parser.add_subparsers(dest="command", required=True)

    p_register = sub.add_parser("register", help="bind reviewed QE inputs/resources to immutable hashes")
    p_register.add_argument("--task-dir", type=Path, required=True)
    p_register.add_argument("--task-id", required=True)
    p_register.add_argument("--matrix-id", required=True)
    p_register.add_argument("--stage", required=True)
    p_register.add_argument("--task-class", default="production")
    p_register.add_argument("--input", action="append", required=True)
    p_register.add_argument("--pseudo", action="append", required=True)
    p_register.add_argument("--job-script", default="job.sh")
    p_register.add_argument("--design-approval", required=True)
    p_register.add_argument("--structure", required=True)
    p_register.add_argument("--output", action="append", required=True)
    p_register.add_argument("--required-output", action="append", default=[])
    p_register.add_argument("--cluster", required=True)
    p_register.add_argument("--remote-host", required=True)
    p_register.add_argument("--remote-dir", required=True)
    p_register.add_argument("--preapproved-by-workflow", action="store_true")
    p_register.add_argument("--replace-records", action="store_true")
    p_register.add_argument("--max-recovery-attempts", type=int, choices=(0, 1), default=1)
    p_register.set_defaults(func=register)

    p_review = sub.add_parser("review", help="verify the snapshot and render/approve submit review")
    p_review.add_argument("--task-dir", type=Path, required=True)
    p_review.add_argument("--approve", action="store_true")
    p_review.set_defaults(func=review)

    p_submit = sub.add_parser("submit", help="recheck remote hashes and submit one Slurm task")
    p_submit.add_argument("--task-dir", type=Path, required=True)
    p_submit.add_argument("--ssh", default="ssh")
    p_submit.add_argument("--dry-run", action="store_true")
    p_submit.add_argument("--resubmit", action="store_true")
    p_submit.set_defaults(func=submit)

    p_status = sub.add_parser("status", help="read Slurm state for the recorded job id")
    p_status.add_argument("--task-dir", type=Path, required=True)
    p_status.add_argument("--ssh", default="ssh")
    p_status.add_argument("--write", action="store_true")
    p_status.set_defaults(func=status)

    p_parse = sub.add_parser("parse", help="parse conservative QE workflow completion without scientific interpretation")
    p_parse.add_argument("--task-dir", type=Path, required=True)
    p_parse.add_argument("--write", action="store_true")
    p_parse.set_defaults(func=parse_outputs)

    p_recover = sub.add_parser("recover", help="archive outputs and resubmit without changing inputs/resources")
    p_recover.add_argument("--task-dir", type=Path, required=True)
    p_recover.add_argument("--action", choices=("resubmit_unchanged",), required=True)
    p_recover.add_argument("--ssh", default="ssh")
    p_recover.add_argument("--dry-run", action="store_true")
    p_recover.set_defaults(func=recover)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
