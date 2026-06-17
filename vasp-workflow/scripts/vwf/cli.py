from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from shlex import quote as shlex_quote
from typing import Any

from .parse import format_summary, parse_task_dir


QUEUE_STATES = ("undo", "calculating", "done", "failed")
STATE_NAME = "state.json"
APPROVAL_NAME = "submission_approval.json"
REVIEW_NAME = "submission_review.dat"
AUTOMATION_PLAN = "workflow_plan.json"
JOB_ID_RE = re.compile(r"Submitted batch job\s+(\d+)")

# Recovery actions the classification engine may take on its own. Each is an
# envelope-safe continuation that does NOT alter scientific parameters
# (ENCUT/KPOINTS/ISMEAR/SIGMA/EDIFF/EDIFFG/MAGMOM/POTCAR). Anything needing a
# scientific or resource change is downgraded to `block` for human review.
SAFE_RECOVERY_ACTIONS = ("restart_from_contcar", "restage_inputs", "resubmit")
# Stale outputs moved aside before a retry so the next attempt is judged on its
# own results (not a previous run's OUTCAR/OSZICAR).
ATTEMPT_ARCHIVE_FILES = ("OUTCAR", "OSZICAR", "vasp.out", "vasp.err")

DEFAULT_FD_INCAR = """SYSTEM = finite displacement phonon force calculation
PREC = Accurate
EDIFF = 1E-8
IBRION = -1
NSW = 0
ISIF = 2
LREAL = .FALSE.
LWAVE = .FALSE.
LCHARG = .FALSE.
ADDGRID = .TRUE.
ISMEAR = 0
SIGMA = 0.01
"""

PROFILE_DEFAULTS: dict[str, dict[str, Any]] = {
    "generic": {
        "partition": "",
        "qos": "",
        "nodes": 1,
        "ntasks_per_node": 1,
        "cpus_per_task": 1,
        "time": "24:00:00",
        "vasp_cmd": "srun vasp_std",
    },
    "nmg": {
        "partition": "Nano",
        "qos": "",
        "nodes": 1,
        "ntasks_per_node": 40,
        "cpus_per_task": 1,
        "time": "24:00:00",
        "vasp_cmd": "srun vasp_std",
    },
    "phoenix": {
        "partition": "Phoenix",
        "qos": "tiny",
        "nodes": 1,
        "ntasks_per_node": 112,
        "cpus_per_task": 1,
        "time": "24:00:00",
        "vasp_cmd": "mpirun -np ${SLURM_NPROCS:-112} vasp_std",
    },
}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    tmp.replace(path)


def atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    atomic_write_text(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def save_state(taskset: Path, state: dict[str, Any]) -> None:
    state["updated_at"] = now_iso()
    atomic_write_json(taskset / STATE_NAME, state)


def load_state(taskset: Path) -> dict[str, Any]:
    state_path = taskset / STATE_NAME
    if not state_path.exists():
        raise FileNotFoundError(f"missing state file: {state_path}")
    return load_json(state_path)


@contextmanager
def queue_lock(taskset: Path, timeout: float = 120.0, poll: float = 0.2):
    lock_path = taskset / ".queue.lock"
    start = time.monotonic()
    fd: int | None = None
    while fd is None:
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, f"{os.getpid()} {now_iso()}\n".encode("utf-8"))
        except FileExistsError:
            if time.monotonic() - start > timeout:
                raise TimeoutError(f"timed out waiting for queue lock: {lock_path}")
            time.sleep(poll)
    try:
        yield
    finally:
        if fd is not None:
            os.close(fd)
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass


def log_queue(taskset: Path, message: str) -> None:
    line = f"{now_iso()} {message}\n"
    with (taskset / "queue.log").open("a", encoding="utf-8", newline="\n") as f:
        f.write(line)


def parse_triplet(value: str) -> tuple[int, int, int]:
    parts = [x for x in re.split(r"[,\s]+", value.strip()) if x]
    if len(parts) != 3:
        raise ValueError(f"expected three integers, got {value!r}")
    return tuple(int(x) for x in parts)  # type: ignore[return-value]


def dim_to_str(dim: tuple[int, int, int]) -> str:
    return " ".join(str(x) for x in dim)


def case_taskset_path(case_root: Path, taskset: str) -> Path:
    return case_root.resolve() / "phonon" / "fd" / taskset


def required_input_paths(source_dir: Path) -> dict[str, Path]:
    return {name: source_dir / name for name in ("POSCAR", "KPOINTS", "POTCAR")}


def find_source_dir(case_root: Path, explicit: Path | None) -> Path:
    if explicit is not None:
        source = explicit.resolve()
        missing = [name for name, path in required_input_paths(source).items() if not path.exists()]
        if missing:
            raise FileNotFoundError(f"source dir missing required files {missing}: {source}")
        return source

    candidates = [
        case_root / "electronic" / "scf",
        case_root / "scf",
        case_root / "energy" / "static-001",
        case_root,
    ]
    for source in candidates:
        if all(path.exists() for path in required_input_paths(source).values()):
            return source.resolve()
    raise FileNotFoundError(
        "cannot find source inputs. Provide --source-dir containing POSCAR, KPOINTS, and POTCAR."
    )


def read_poscar_summary(path: Path) -> str:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return "unreadable POSCAR"
    title = lines[0].strip() if lines else ""
    symbols = ""
    counts = ""
    if len(lines) >= 7:
        maybe_symbols = lines[5].split()
        if all(re.search(r"[A-Za-z]", x) for x in maybe_symbols):
            symbols = " ".join(maybe_symbols)
            counts = " ".join(lines[6].split())
        else:
            counts = " ".join(maybe_symbols)
    return f"title={title!r} symbols={symbols or 'unknown'} counts={counts or 'unknown'}"


def read_poscar_details(path: Path) -> list[str]:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ["POSCAR.details = unreadable"]
    details: list[str] = []
    if len(lines) < 8:
        return ["POSCAR.details = too short to inspect"]
    scale = lines[1].strip()
    details.append(f"POSCAR.scale = {scale}")
    try:
        scale_value = float(scale.split()[0])
        lengths: list[str] = []
        for idx in range(2, 5):
            vec = [float(x) for x in lines[idx].split()[:3]]
            length = (sum(x * x for x in vec) ** 0.5) * scale_value
            lengths.append(f"{length:.8g}")
        details.append("POSCAR.lattice_lengths = " + " ".join(lengths))
    except (ValueError, IndexError):
        details.append("POSCAR.lattice_lengths = unable_to_parse")
    maybe_symbols = lines[5].split()
    if all(re.search(r"[A-Za-z]", x) for x in maybe_symbols):
        details.append("POSCAR.symbols = " + " ".join(maybe_symbols))
        details.append("POSCAR.counts = " + (" ".join(lines[6].split()) if len(lines) > 6 else "unknown"))
        mode_index = 7
    else:
        details.append("POSCAR.symbols = unknown")
        details.append("POSCAR.counts = " + " ".join(maybe_symbols))
        mode_index = 6
    selective = False
    if len(lines) > mode_index and lines[mode_index].strip().lower().startswith("s"):
        selective = True
        mode_index += 1
    mode = lines[mode_index].strip() if len(lines) > mode_index else "unknown"
    details.append(f"POSCAR.selective_dynamics = {str(selective).lower()}")
    details.append(f"POSCAR.coordinate_mode = {mode}")
    details.append(
        "POSCAR.ordering_review = confirm atom order; generated structures should generally sort by descending z, ascending x, ascending y unless symmetry/labels require otherwise"
    )
    details.append("POSCAR.fixed_atoms_review = confirm whether atoms are fixed; inspect Selective Dynamics flags when present")
    return details


def read_kpoints_summary(path: Path) -> str:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    preview = " | ".join(line.strip() for line in lines[:5] if line.strip())
    return preview or "empty KPOINTS"


def read_incar_summary(path: Path) -> str:
    keys: list[str] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        clean = line.split("#", 1)[0].split("!", 1)[0].strip()
        if "=" not in clean:
            continue
        key, value = clean.split("=", 1)
        key = key.strip().upper()
        if key:
            keys.append(f"{key}={value.strip()}")
    important = [
        item for item in keys
        if item.split("=", 1)[0] in {
            "ENCUT", "EDIFF", "EDIFFG", "IBRION", "NSW", "ISIF", "ISMEAR",
            "SIGMA", "LORBIT", "LELF", "LCHARG", "LWAVE", "MAGMOM", "ISPIN"
        }
    ]
    return "; ".join(important or keys[:12]) or "empty INCAR"


def read_text_block(path: Path, max_chars: int = 20000) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace").rstrip()
    except OSError:
        return "<unreadable>"
    if len(text) > max_chars:
        return text[:max_chars] + "\n# ... truncated for review; inspect source file before approval ..."
    return text or "<empty>"


def read_potcar_summary(path: Path) -> str:
    titles: list[str] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if "TITEL" in line or line.startswith("VRHFIN"):
            titles.append(line.strip())
        if len(titles) >= 12:
            break
    return "; ".join(titles) if titles else "no TITEL/VRHFIN lines found"


def infer_kpoints_review(path: Path, state: dict[str, Any], hashes: dict[str, str]) -> list[str]:
    source = state.get("input_sources", {}).get("KPOINTS", "unknown")
    lines = [f"KPOINTS.source = {source}"]
    lines.append(f"KPOINTS.sha256 = {hashes.get('KPOINTS', 'missing')}")
    lines.append(f"KPOINTS.summary = {read_kpoints_summary(path)}")
    metadata = state.get("kpoints", {})
    if isinstance(metadata, dict):
        if metadata.get("generator"):
            lines.append(f"KPOINTS.generator = {metadata['generator']}")
        if metadata.get("band_path"):
            lines.append(f"KPOINTS.band_path = {metadata['band_path']}")
    lines.append("KPOINTS.band_path_review = for band jobs, list labels explicitly and state generator: manual, VASPKIT, pymatgen, SeeK-path, or other")
    lines.append("KPOINTS.generator_env_review = if the generator is missing, stop and ask user to install/activate VASPKIT or a Python env with pymatgen/ase/seekpath")
    return lines


def current_input_hashes(taskset: Path) -> dict[str, str]:
    paths = {
        "POSCAR": taskset / "input" / "POSCAR",
        "INCAR.fd": taskset / "input" / "INCAR.fd",
        "KPOINTS": taskset / "input" / "KPOINTS",
        "POTCAR": taskset / "input" / "POTCAR",
        "phonopy.conf": taskset / "input" / "phonopy.conf",
    }
    return {name: sha256_file(path) for name, path in paths.items() if path.exists()}


def resource_envelope(args: argparse.Namespace) -> dict[str, Any]:
    defaults = PROFILE_DEFAULTS.get(args.profile, PROFILE_DEFAULTS["generic"]).copy()
    for key in ("partition", "qos", "time", "vasp_cmd"):
        value = getattr(args, key.replace("vasp_cmd", "vasp_cmd"), None)
        if value is not None:
            defaults[key] = value
    for key in ("nodes", "ntasks_per_node", "cpus_per_task"):
        value = getattr(args, key, None)
        if value is not None:
            defaults[key] = value
    ntasks = args.ntasks if getattr(args, "ntasks", None) else defaults["nodes"] * defaults["ntasks_per_node"]
    defaults["ntasks"] = ntasks
    defaults["profile"] = args.profile
    return defaults


def resource_hash(resources: dict[str, Any], workers: int) -> str:
    payload = {"resources": resources, "workers": workers}
    return sha256_text(json.dumps(payload, sort_keys=True))


def make_marker(target: Path, marker: Path) -> None:
    marker.parent.mkdir(parents=True, exist_ok=True)
    if marker.exists() or marker.is_symlink():
        marker.unlink()
    rel = os.path.relpath(target, marker.parent)
    try:
        marker.symlink_to(rel, target_is_directory=True)
    except OSError:
        atomic_write_text(marker, str(target))


def move_marker(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists() or dst.is_symlink():
        dst.unlink()
    src.rename(dst)


def init_case(args: argparse.Namespace) -> int:
    root = args.case_root.resolve()
    dirs = [
        "structure",
        "test/encut",
        "test/kpoints",
        "test/sigma",
        "test/potcar",
        "test/notes",
        "relax",
        "energy",
        "electronic/scf",
        "electronic/band",
        "electronic/dos",
        "electronic/fatband",
        "electronic/pcohp",
        "electronic/elf",
        "electronic/chgdiff",
        "electronic/spin-density",
        "electronic/parchg",
        "electronic/locpot",
        "electronic/bader",
        "electronic/optics",
        "electronic/wannier",
        "phonon/fd",
        "phonon/dfpt",
        "phonon/gamma",
        "phonon/unfolded",
        "phonon/thermal",
        "analysis/plot_data",
        "analysis/figures",
        "analysis/reports",
        "automation",
    ]
    for rel in dirs:
        (root / rel).mkdir(parents=True, exist_ok=True)
    workflow = root / "workflow.json"
    if not workflow.exists():
        atomic_write_json(workflow, {
            "schema_version": 1,
            "case_root": str(root),
            "workflow_order": [
                "structure",
                "test",
                "relax",
                "electronic/scf",
                "downstream electronic",
                "phonon from relaxed structure",
                "analysis/archive",
            ],
            "created_at": now_iso(),
        })
    print(f"[ok] initialized case tree: {root}")
    return 0


def automation_dir(case_root: Path) -> Path:
    return case_root / "automation"


def automation_plan_path(case_root: Path) -> Path:
    return automation_dir(case_root) / AUTOMATION_PLAN


def automation_log(case_root: Path, message: str) -> None:
    directory = automation_dir(case_root)
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "automation.log").open("a", encoding="utf-8") as f:
        f.write(f"{now_iso()} {message}\n")


def default_automation_plan(case_root: Path) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "case_root": str(case_root),
        "auto_submit": False,
        "auto_recover": False,
        "created_at": now_iso(),
        "stages": [
            {
                "name": "relax",
                "depends_on": [],
                "path": "relax",
                "status": "planned",
                "submit_command": "sbatch job.sh",
                "review_file": REVIEW_NAME,
                "approval_file": APPROVAL_NAME,
                # Existence gate first (don't parse a half-written run), then the
                # authoritative check: ionic convergence via `vwf parse`.
                "completion_files": ["CONTCAR", "OUTCAR"],
                "require_convergence": True,
                "detect_failure_from_parse": True,
                "auto_recover": False,
                # When auto_recover is enabled (+ max_retries>0), "classify" maps
                # the parsed error to one safe action; set "command" to instead
                # run recovery_command. See references/automation-cron.md.
                "recovery_strategy": "classify",
                "max_retries": 0,
                "retry_count": 0,
                "recovery_command": "",
            },
            {
                "name": "scf",
                "depends_on": ["relax"],
                "path": "electronic/scf",
                "status": "planned",
                "submit_command": "sbatch job.sh",
                "review_file": REVIEW_NAME,
                "approval_file": APPROVAL_NAME,
                # Derived input: take the converged geometry from relax. Declared
                # here so it is part of the approved envelope (Safety Model).
                "inputs_from": [{"stage": "relax", "file": "CONTCAR", "to": "POSCAR"}],
                "completion_files": ["OUTCAR", "CHGCAR"],
                "require_convergence": True,
                "detect_failure_from_parse": True,
                "auto_recover": False,
                # When auto_recover is enabled (+ max_retries>0), "classify" maps
                # the parsed error to one safe action; set "command" to instead
                # run recovery_command. See references/automation-cron.md.
                "recovery_strategy": "classify",
                "max_retries": 0,
                "retry_count": 0,
                "recovery_command": "",
            },
        ],
    }


def automation_init(args: argparse.Namespace) -> int:
    case_root = args.case_root.resolve()
    directory = automation_dir(case_root)
    directory.mkdir(parents=True, exist_ok=True)
    plan_path = automation_plan_path(case_root)
    if plan_path.exists() and not args.overwrite:
        raise FileExistsError(f"automation plan already exists: {plan_path}")
    plan = default_automation_plan(case_root)
    atomic_write_json(plan_path, plan)
    print(f"[ok] wrote automation plan template: {plan_path}")
    print("[next] edit stages, generate reviews/approvals, then test with automation tick --dry-run")
    return 0


def resolve_stage_path(case_root: Path, stage: dict[str, Any], key: str) -> Path:
    value = Path(str(stage[key]))
    if value.is_absolute():
        return value
    return case_root / str(stage.get("path", ".")) / value


def stage_has_approval(case_root: Path, stage: dict[str, Any]) -> bool:
    review = resolve_stage_path(case_root, stage, "review_file")
    approval = resolve_stage_path(case_root, stage, "approval_file")
    if not review.exists() or not approval.exists():
        return False
    try:
        payload = load_json(approval)
    except Exception:
        return False
    if not payload.get("approved", False):
        return False
    if payload.get("review_hash"):
        review_text = review.read_text(encoding="utf-8", errors="replace")
        return payload.get("review_hash") == sha256_text(review_text)
    return True


def stage_complete(case_root: Path, stage: dict[str, Any]) -> bool:
    stage_root = case_root / str(stage.get("path", "."))
    for rel in stage.get("completion_files", []):
        if not (stage_root / str(rel)).exists():
            return False
    for item in stage.get("completion_text", []):
        path = stage_root / str(item.get("file", ""))
        needle = str(item.get("contains", ""))
        if not path.exists() or needle not in path.read_text(encoding="utf-8", errors="replace"):
            return False
    # Judge a stage done by its scientific outcome, not just a clean exit: a run
    # that terminated normally but never converged is NOT complete.
    if stage.get("require_convergence"):
        if parse_task_dir(stage_root).get("converged") is not True:
            return False
    return True


def stage_failed(case_root: Path, stage: dict[str, Any]) -> bool:
    stage_root = case_root / str(stage.get("path", "."))
    for rel in stage.get("failure_files", []):
        path = stage_root / str(rel)
        if path.exists() and path.stat().st_size > 0:
            return True
    for item in stage.get("failure_text", []):
        path = stage_root / str(item.get("file", ""))
        needle = str(item.get("contains", ""))
        if path.exists() and needle in path.read_text(encoding="utf-8", errors="replace"):
            return True
    # Detect terminal failures from parsed output: a real crash (error_type) or
    # a run that finished cleanly yet did not converge. A still-running job has
    # neither, so it is not flagged here.
    if stage.get("detect_failure_from_parse"):
        result = parse_task_dir(stage_root)
        if result.get("error_type"):
            return True
        if result.get("finished") and result.get("converged") is False:
            return True
    return False


def squeue_state(job_id: str) -> str | None:
    squeue = shutil.which("squeue")
    if squeue is None:
        return None
    result = subprocess.run([squeue, "-h", "-j", job_id, "-o", "%T"], text=True, capture_output=True)
    if result.returncode != 0:
        return None
    output = result.stdout.strip().splitlines()
    return output[0].strip() if output else ""


def _set_blocked(stage: dict[str, Any], reason: str) -> bool:
    """Set a stage blocked idempotently; return True only on a real transition."""
    if stage.get("status") == "blocked" and stage.get("blocked_reason") == reason:
        return False
    stage["status"] = "blocked"
    stage["blocked_reason"] = reason
    return True


def plan_recovery(result: dict[str, Any], stage: dict[str, Any]) -> dict[str, Any]:
    """Map a parsed failure to a single conservative recovery action.

    Pure (no side effects). Returns ``{action, reason, recommendation}`` where
    ``action`` is one of ``SAFE_RECOVERY_ACTIONS`` or ``block``. Any condition
    whose only fix would change a scientific parameter or the resource envelope
    is mapped to ``block`` with a recommendation for the human. The stage's
    optional ``recovery_actions`` allow-list can further restrict what may run.
    """
    allowed = set(stage.get("recovery_actions", SAFE_RECOVERY_ACTIONS))
    files = result.get("files_seen") or []
    has_contcar = "CONTCAR" in files
    has_chgcar_source = any(str(s.get("file")) == "CHGCAR" for s in stage.get("inputs_from", []))
    etype = result.get("error_type")

    def choose(action: str, reason: str, recommendation: str = "") -> dict[str, Any]:
        if action != "block" and action not in allowed:
            return {"action": "block",
                    "reason": f"{reason} (action '{action}' not allowed by recovery_actions)",
                    "recommendation": recommendation}
        return {"action": action, "reason": reason, "recommendation": recommendation}

    if etype == "OUT_OF_MEMORY":
        return choose("block", "out of memory",
                      "Reduce system size or raise memory / adjust NCORE-KPAR; resource change needs approval.")
    if etype == "COMMAND_NOT_FOUND":
        return choose("block", "VASP command or module unavailable in the job shell",
                      "Fix the environment (module load / vasp binary) before retrying.")
    if etype in ("ZHEGV_FAILED", "LAPACK_ERROR"):
        return choose("block", f"numerical failure {etype}",
                      "ALGO/precision/structure adjustments are scientific; review before retry.")
    if etype == "CHGCAR_READ_FAILED":
        if has_chgcar_source:
            return choose("restage_inputs", "CHGCAR missing/incompatible; re-stage from the declared source")
        return choose("block", "CHGCAR read failed and no declared CHGCAR source",
                      "Provide a valid CHGCAR or review ICHARG; flipping ICHARG is a scientific change.")
    if etype == "ZBRENT_FAILED":
        if has_contcar:
            return choose("restart_from_contcar", "ZBRENT line-search failure; continue relaxation from CONTCAR")
        return choose("block", "ZBRENT failure without a CONTCAR to continue from",
                      "Inspect starting geometry and forces; review needed.")
    if etype == "TIME_LIMIT":
        if has_contcar:
            return choose("restart_from_contcar", "wall-time limit; continue from CONTCAR")
        return choose("resubmit", "wall-time limit; resubmit to continue (no restart geometry yet)")
    if etype:
        return choose("block", f"unhandled error_type {etype}", "Manual review required.")

    # No hard crash: decide from the convergence verdict.
    if result.get("converged") is False:
        is_static = (result.get("nsw") == 0) or (result.get("ibrion") == -1)
        if not is_static and has_contcar:
            return choose("restart_from_contcar", "ionic relaxation not converged; continue from CONTCAR")
        return choose("block", "electronic non-convergence",
                      "Review ALGO/NELM/mixing/SIGMA (scientific); not changed automatically.")
    return choose("block", "no recoverable condition identified", "Manual review.")


def _archive_attempt(stage_dir: Path, attempt: int, dry_run: bool) -> list[str]:
    """Move stale outputs into recovery_attempts/attempt-N so the next run is
    judged on its own results. Returns the moved file names."""
    moved: list[str] = []
    dest = stage_dir / "recovery_attempts" / f"attempt-{attempt}"
    candidates = [stage_dir / name for name in ATTEMPT_ARCHIVE_FILES]
    candidates += sorted(stage_dir.glob("slurm-*.out")) + sorted(stage_dir.glob("slurm-*.err"))
    for path in candidates:
        if path.exists():
            if not dry_run:
                dest.mkdir(parents=True, exist_ok=True)
                path.rename(dest / path.name)
            moved.append(path.name)
    return moved


def try_stage_recovery(case_root: Path, plan: dict[str, Any], stage: dict[str, Any], dry_run: bool) -> bool:
    if not plan.get("auto_recover", False) or not stage.get("auto_recover", False):
        return False
    retry_count = int(stage.get("retry_count", 0))
    max_retries = int(stage.get("max_retries", 0))
    if retry_count >= max_retries:
        return _set_blocked(stage, f"max retries reached: {retry_count}/{max_retries}")
    next_retry = retry_count + 1
    stage_cwd = case_root / str(stage.get("path", "."))
    command = str(stage.get("recovery_command", "")).strip()
    strategy = str(stage.get("recovery_strategy", "command" if command else "classify"))

    # Legacy path: run the user-supplied recovery command verbatim.
    if strategy == "command" and command:
        print(f"[recover] {stage['name']} retry {next_retry}/{max_retries}: {command}")
        if dry_run:
            return False
        result = subprocess.run(command, cwd=stage_cwd, shell=True, text=True, capture_output=True)
        (stage_cwd / f"automation_recovery_{next_retry}.out").write_text(result.stdout, encoding="utf-8")
        (stage_cwd / f"automation_recovery_{next_retry}.err").write_text(result.stderr, encoding="utf-8")
        stage["retry_count"] = next_retry
        stage["last_recovery_at"] = now_iso()
        if result.returncode == 0:
            stage["status"] = "ready"
            stage.pop("job_id", None)
            stage.pop("blocked_reason", None)
            automation_log(case_root, f"{stage['name']} recovered retry={next_retry}")
        else:
            stage["status"] = "blocked"
            stage["blocked_reason"] = f"recovery command exited {result.returncode}"
            automation_log(case_root, f"{stage['name']} recovery failed retry={next_retry}: {stage['blocked_reason']}")
        return True

    # Classification engine: choose one envelope-safe action from the parsed error.
    parsed = parse_task_dir(stage_cwd)
    decision = plan_recovery(parsed, stage)
    action = decision["action"]
    print(f"[recover] {stage['name']} retry {next_retry}/{max_retries}: {action} — {decision['reason']}")
    if dry_run:
        return False
    if action == "block":
        reason = decision["reason"] + (f"; {decision['recommendation']}" if decision.get("recommendation") else "")
        if _set_blocked(stage, reason):
            automation_log(case_root, f"{stage['name']} recovery blocked: {reason}")
            return True
        return False

    if action == "restart_from_contcar":
        contcar = stage_cwd / "CONTCAR"
        if contcar.exists() and contcar.stat().st_size > 0:
            shutil.copy2(contcar, stage_cwd / "POSCAR")
    elif action == "restage_inputs":
        by_name = {s.get("name"): s for s in plan.get("stages", [])}
        stage_inputs(case_root, stage, by_name, dry_run=False)
    # "resubmit": no file change.
    archived = _archive_attempt(stage_cwd, next_retry, dry_run=False)
    stage["retry_count"] = next_retry
    stage["last_recovery_at"] = now_iso()
    stage["last_recovery_action"] = action
    stage["status"] = "ready"
    stage.pop("job_id", None)
    stage.pop("blocked_reason", None)
    automation_log(case_root, f"{stage['name']} recovered via {action} retry={next_retry}; archived={archived}")
    return True


def _staged_up_to_date(src: Path, dst: Path, use_link: bool) -> bool:
    """Cheap check whether dst already reflects src (avoids hashing big files).

    copy2 preserves mtime, so size+mtime equality means the copy is current.
    """
    if use_link:
        try:
            return dst.is_symlink() and (dst.parent / os.readlink(dst)).resolve() == src.resolve()
        except OSError:
            return False
    if not dst.exists() or dst.is_symlink():
        return False
    s, d = src.stat(), dst.stat()
    return s.st_size == d.st_size and int(s.st_mtime) == int(d.st_mtime)


def stage_inputs(case_root: Path, stage: dict[str, Any], by_name: dict[str, dict[str, Any]], dry_run: bool) -> dict[str, Any]:
    """Copy/link declared upstream outputs into this stage's inputs.

    A stage declares `inputs_from` entries, e.g.
    ``{"stage": "relax", "file": "CONTCAR", "to": "POSCAR"}`` or, for large
    files, ``{"stage": "scf", "file": "CHGCAR", "link": true}``. Staging only
    runs once dependencies are ``done`` (which, with `require_convergence`,
    means the upstream actually converged), so a derived input is always taken
    from a converged source. Per the skill Safety Model these derivations are
    part of the approved envelope, so staging does NOT touch approval files.

    Idempotent: a destination already matching the source is left untouched.
    Returns ``{"staged": [msgs], "missing": [names], "changed": bool}``.
    """
    specs = stage.get("inputs_from", [])
    staged_msgs: list[str] = []
    missing: list[str] = []
    records: list[dict[str, Any]] = []
    changed = False
    for spec in specs:
        fname = str(spec.get("file"))
        to = str(spec.get("to", fname))
        optional = bool(spec.get("optional", False))
        use_link = bool(spec.get("link", False))
        up = by_name.get(spec.get("stage"))
        if up is None:
            missing.append(f"{fname} (unknown upstream stage {spec.get('stage')!r})")
            continue
        src = case_root / str(up.get("path", ".")) / fname
        dst = case_root / str(stage.get("path", ".")) / to
        if not src.exists():
            if not optional:
                missing.append(str(src))
            continue
        if _staged_up_to_date(src, dst, use_link):
            continue
        if not dry_run:
            dst.parent.mkdir(parents=True, exist_ok=True)
            if dst.exists() or dst.is_symlink():
                dst.unlink()
            if use_link:
                try:
                    dst.symlink_to(os.path.relpath(src, dst.parent))
                except OSError:
                    shutil.copy2(src, dst)
            else:
                shutil.copy2(src, dst)
        changed = True
        size = src.stat().st_size
        record = {"from": str(src), "to": str(dst), "bytes": size, "link": use_link, "at": now_iso()}
        if not use_link and size <= 8 * 1024 * 1024:
            record["sha256"] = sha256_file(src)
        records.append(record)
        staged_msgs.append(f"{fname} -> {to}" + (" (link)" if use_link else ""))
    if changed and not dry_run:
        stage["staged"] = records
        atomic_write_json(
            case_root / str(stage.get("path", ".")) / "staged_inputs.json",
            {"stage": stage.get("name"), "staged_at": now_iso(), "records": records},
        )
    return {"staged": staged_msgs, "missing": missing, "changed": changed}


def automation_tick(args: argparse.Namespace) -> int:
    case_root = args.case_root.resolve()
    plan_path = automation_plan_path(case_root)
    plan = load_json(plan_path)
    stages: list[dict[str, Any]] = plan.get("stages", [])
    by_name = {stage["name"]: stage for stage in stages}
    changed = False

    def log(message: str) -> None:
        if not args.dry_run:
            automation_log(case_root, message)

    for stage in stages:
        status = stage.get("status", "planned")
        if status in {"submitted", "running"}:
            if stage_complete(case_root, stage):
                stage["status"] = "done"
                log(f"{stage['name']} -> done")
                changed = True
            elif stage_failed(case_root, stage):
                stage["status"] = "failed"
                log(f"{stage['name']} -> failed")
                changed = True
            elif stage.get("job_id"):
                queue_state = squeue_state(str(stage["job_id"]))
                if queue_state:
                    stage["status"] = "running" if queue_state == "RUNNING" else "submitted"
                elif queue_state == "":
                    stage["status"] = "blocked"
                    stage["blocked_reason"] = "job left Slurm queue but completion criteria are not satisfied"
                    log(f"{stage['name']} -> blocked: {stage['blocked_reason']}")
                    changed = True

    for stage in stages:
        if stage.get("status") in {"failed", "blocked"}:
            if try_stage_recovery(case_root, plan, stage, args.dry_run):
                changed = True

    for stage in stages:
        if stage.get("status", "planned") != "planned":
            continue
        dep_names = list(stage.get("depends_on", []))
        deps = [by_name[name].get("status") for name in dep_names if name in by_name]
        if (not dep_names) or (len(deps) == len(dep_names) and all(status == "done" for status in deps)):
            # Stage derived inputs (e.g. relax/CONTCAR -> scf/POSCAR) from the
            # now-converged upstream before the stage becomes submittable.
            staging = stage_inputs(case_root, stage, by_name, args.dry_run)
            for msg in staging["staged"]:
                print(f"[stage-inputs] {stage['name']}: {msg}")
                log(f"{stage['name']} staged {msg}")
            if staging["missing"]:
                stage["status"] = "blocked"
                stage["blocked_reason"] = "required staged input missing: " + ", ".join(staging["missing"])
                print(f"[blocked] {stage['name']}: {stage['blocked_reason']}")
                log(f"{stage['name']} -> blocked: {stage['blocked_reason']}")
                changed = True
                continue
            stage["status"] = "ready"
            log(f"{stage['name']} -> ready")
            changed = True

    for stage in stages:
        if stage.get("status") != "ready":
            continue
        if not plan.get("auto_submit", False):
            print(f"[ready] {stage['name']} (auto_submit=false)")
            continue
        if not stage_has_approval(case_root, stage):
            stage["status"] = "blocked"
            stage["blocked_reason"] = "missing review or approved submission_approval.json"
            print(f"[blocked] {stage['name']}: {stage['blocked_reason']}")
            log(f"{stage['name']} -> blocked: {stage['blocked_reason']}")
            changed = True
            continue
        command = str(stage["submit_command"])
        stage_cwd = case_root / str(stage.get("path", "."))
        print(f"[submit] {stage['name']}: {command}")
        if args.dry_run:
            continue
        result = subprocess.run(command, cwd=stage_cwd, shell=True, text=True, capture_output=True)
        (stage_cwd / "automation_submit.out").write_text(result.stdout, encoding="utf-8")
        (stage_cwd / "automation_submit.err").write_text(result.stderr, encoding="utf-8")
        if result.returncode != 0:
            stage["status"] = "blocked"
            stage["blocked_reason"] = f"submit command exited {result.returncode}"
            log(f"{stage['name']} -> blocked: {stage['blocked_reason']}")
        else:
            match = JOB_ID_RE.search(result.stdout + "\n" + result.stderr)
            stage["job_id"] = match.group(1) if match else None
            stage["status"] = "submitted"
            stage["submitted_at"] = now_iso()
            log(f"{stage['name']} -> submitted job_id={stage.get('job_id')}")
        changed = True

    if changed and not args.dry_run:
        plan["updated_at"] = now_iso()
        atomic_write_json(plan_path, plan)
    for stage in stages:
        print(f"{stage['name']}: {stage.get('status', 'planned')} job_id={stage.get('job_id')}")
    return 0


def automation_cron_line(args: argparse.Namespace) -> int:
    case_root = args.case_root.resolve()
    scripts_root = Path(__file__).resolve().parents[1]
    log_path = automation_dir(case_root) / "cron.log"
    python = sys.executable
    line = (
        f"*/{args.interval_minutes} * * * * "
        f"cd {shlex_quote(str(case_root))} && "
        f"PYTHONPATH={shlex_quote(str(scripts_root))}${{PYTHONPATH:+:$PYTHONPATH}} "
        f"{shlex_quote(python)} -m vwf automation tick --case-root {shlex_quote(str(case_root))} "
        f">> {shlex_quote(str(log_path))} 2>&1"
    )
    print(line)
    return 0


def list_displacement_poscars(path: Path) -> list[Path]:
    def key(p: Path) -> int:
        m = re.search(r"POSCAR-(\d+)$", p.name)
        return int(m.group(1)) if m else 10**9
    return sorted(path.glob("POSCAR-*"), key=key)


def displacement_label(path: Path) -> str:
    m = re.search(r"POSCAR-(\d+)$", path.name)
    if not m:
        raise ValueError(f"not a displacement POSCAR: {path}")
    return f"disp-{int(m.group(1)):03d}"


def build_phonopy_conf(dim: tuple[int, int, int], distance: float) -> str:
    return f"DIM = {dim_to_str(dim)}\nPRIMITIVE_AXES = AUTO\nDISPLACEMENT_DISTANCE = {distance:.8f}\n"


def build_run_script(vasp_cmd: str) -> str:
    return f"""#!/bin/sh
set -eu
cd "$(dirname "$0")"
echo "[start] $(date)"
echo "[cwd] $PWD"
{vasp_cmd} > vasp.out 2> vasp.err
echo "[end] $(date)"
"""


def build_worker_slurm(taskset: Path, worker_id: str, resources: dict[str, Any]) -> str:
    scripts_root = Path(__file__).resolve().parents[1]
    lines = [
        "#!/bin/bash",
        f"#SBATCH -J fdw-{worker_id}",
        f"#SBATCH -N {resources['nodes']}",
        f"#SBATCH -n {resources['ntasks']}",
        f"#SBATCH --ntasks-per-node={resources['ntasks_per_node']}",
        f"#SBATCH --cpus-per-task={resources['cpus_per_task']}",
        f"#SBATCH -t {resources['time']}",
        "#SBATCH -o worker-%j.out",
        "#SBATCH -e worker-%j.err",
    ]
    if resources.get("partition"):
        lines.append(f"#SBATCH -p {resources['partition']}")
    if resources.get("qos"):
        lines.append(f"#SBATCH -q {resources['qos']}")
    lines.extend([
        "",
        "set -euo pipefail",
        f"TASKSET={json.dumps(str(taskset))}",
        f"export PYTHONPATH={json.dumps(str(scripts_root))}${{PYTHONPATH:+:$PYTHONPATH}}",
        "python -m vwf worker run --taskset \"$TASKSET\" --worker-id " + worker_id,
        "",
    ])
    return "\n".join(lines)


def prepare_phonon_fd(args: argparse.Namespace) -> int:
    case_root = args.case_root.resolve()
    source = find_source_dir(case_root, args.source_dir)
    taskset = case_taskset_path(case_root, args.taskset)
    if taskset.exists() and not args.overwrite:
        raise FileExistsError(f"taskset already exists; pass --overwrite to replace: {taskset}")
    if taskset.exists():
        shutil.rmtree(taskset)

    dim = parse_triplet(args.dim)
    resources = resource_envelope(args)
    input_dir = taskset / "input"
    disp_dir = taskset / "displacements"
    jobs_dir = taskset / "jobs"

    for directory in [input_dir, disp_dir, jobs_dir, taskset / "workers", *(taskset / "queue" / x for x in QUEUE_STATES)]:
        directory.mkdir(parents=True, exist_ok=True)

    shutil.copy2(source / "POSCAR", input_dir / "POSCAR")
    shutil.copy2(source / "KPOINTS", input_dir / "KPOINTS")
    shutil.copy2(source / "POTCAR", input_dir / "POTCAR")
    if args.incar_template is not None:
        incar_text = args.incar_template.read_text(encoding="utf-8", errors="replace")
        incar_source = str(args.incar_template.resolve())
    elif (source / "INCAR").exists() and args.copy_source_incar:
        incar_text = (source / "INCAR").read_text(encoding="utf-8", errors="replace").rstrip() + "\n\n" + DEFAULT_FD_INCAR
        incar_source = str((source / "INCAR").resolve()) + " + fd overrides"
    else:
        incar_text = DEFAULT_FD_INCAR
        incar_source = "built-in fd static-force template"
    atomic_write_text(input_dir / "INCAR.fd", incar_text.rstrip() + "\n")
    atomic_write_text(input_dir / "phonopy.conf", build_phonopy_conf(dim, args.displacement_distance))

    shutil.copy2(input_dir / "POSCAR", disp_dir / "POSCAR")
    atomic_write_text(disp_dir / "phonopy.conf", build_phonopy_conf(dim, args.displacement_distance))
    if args.mock_displacements:
        for idx in range(1, args.mock_displacements + 1):
            shutil.copy2(input_dir / "POSCAR", disp_dir / f"POSCAR-{idx:03d}")
    else:
        cmd = [args.phonopy_bin, "-d", "--dim", dim_to_str(dim), "--pa", "auto", "-c", "POSCAR"]
        subprocess.run(cmd, cwd=disp_dir, check=True)

    poscars = list_displacement_poscars(disp_dir)
    if not poscars:
        raise RuntimeError(f"no displacement POSCAR-* files generated in {disp_dir}")

    jobs: dict[str, dict[str, Any]] = {}
    for poscar in poscars:
        label = displacement_label(poscar)
        job_dir = jobs_dir / label
        job_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(poscar, job_dir / "POSCAR")
        shutil.copy2(input_dir / "KPOINTS", job_dir / "KPOINTS")
        shutil.copy2(input_dir / "POTCAR", job_dir / "POTCAR")
        shutil.copy2(input_dir / "INCAR.fd", job_dir / "INCAR")
        run_script = job_dir / "run_vasp.sh"
        atomic_write_text(run_script, build_run_script(resources["vasp_cmd"]))
        run_script.chmod(0o755)
        make_marker(job_dir, taskset / "queue" / "undo" / label)
        jobs[label] = {
            "status": "undo",
            "path": str(job_dir.relative_to(taskset)),
            "source_poscar": str(poscar.relative_to(taskset)),
            "attempts": 0,
            "created_at": now_iso(),
            "updated_at": now_iso(),
        }

    for idx in range(1, args.workers + 1):
        worker_id = f"worker-{idx:03d}"
        worker_dir = taskset / "workers" / worker_id
        worker_dir.mkdir(parents=True, exist_ok=True)
        script = worker_dir / "submit.slurm"
        atomic_write_text(script, build_worker_slurm(taskset, worker_id, resources))
        script.chmod(0o755)

    hashes = current_input_hashes(taskset)
    state = {
        "schema_version": 1,
        "kind": "phonon-fd-worker-queue",
        "case_root": str(case_root),
        "taskset": str(taskset),
        "source_dir": str(source),
        "input_sources": {
            "POSCAR": str((source / "POSCAR").resolve()),
            "KPOINTS": str((source / "KPOINTS").resolve()),
            "POTCAR": str((source / "POTCAR").resolve()),
            "INCAR.fd": incar_source,
        },
        "input_hashes": hashes,
        "dim": list(dim),
        "displacement_distance": args.displacement_distance,
        "workers": args.workers,
        "resources": resources,
        "resource_hash": resource_hash(resources, args.workers),
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "jobs": jobs,
        "workers_state": {f"worker-{idx:03d}": {"status": "prepared", "job_id": None} for idx in range(1, args.workers + 1)},
    }
    save_state(taskset, state)
    task_spec = {
        "schema_version": 1,
        "task_kind": "phonon-fd",
        "taskset": str(taskset),
        "source_dir": str(source),
        "input_hashes": hashes,
        "workers": args.workers,
        "resources": resources,
        "created_at": now_iso(),
    }
    atomic_write_json(taskset / "task_spec.json", task_spec)
    log_queue(taskset, f"prepared {len(jobs)} displacement jobs with {args.workers} workers")
    print(f"[ok] prepared {len(jobs)} displacement jobs -> {taskset}")
    print(f"[next] run: python -m vwf review submit --taskset {taskset}")
    return 0


def build_submission_review(taskset: Path, state: dict[str, Any]) -> str:
    input_dir = taskset / "input"
    hashes = current_input_hashes(taskset)
    resources = state["resources"]
    incar_path = input_dir / "INCAR.fd"
    lines = [
        "# vasp_workflow_submission_review = 1",
        f"generated_at = {now_iso()}",
        f"taskset = {taskset}",
        f"kind = {state.get('kind')}",
        "",
        "[inputs]",
        f"POSCAR.source = {state['input_sources'].get('POSCAR', 'unknown')}",
        f"POSCAR.sha256 = {hashes.get('POSCAR', 'missing')}",
        f"POSCAR.summary = {read_poscar_summary(input_dir / 'POSCAR')}",
        *read_poscar_details(input_dir / "POSCAR"),
        f"INCAR.source = {state['input_sources'].get('INCAR.fd', 'unknown')}",
        f"INCAR.sha256 = {hashes.get('INCAR.fd', 'missing')}",
        f"INCAR.summary = {read_incar_summary(input_dir / 'INCAR.fd')}",
        "INCAR.change_review = confirm inherited, appended, or overridden parameters for follow-up calculations",
        "INCAR.complete_begin",
        read_text_block(incar_path),
        "INCAR.complete_end",
        *infer_kpoints_review(input_dir / "KPOINTS", state, hashes),
        f"POTCAR.source = {state['input_sources'].get('POTCAR', 'unknown')}",
        f"POTCAR.sha256 = {hashes.get('POTCAR', 'missing')}",
        f"POTCAR.summary = {read_potcar_summary(input_dir / 'POTCAR')}",
        "POTCAR.user_choice_required = true",
        "POTCAR.choice_review = user must confirm functional, element order, and potential labels before generation/submission",
        "POTCAR.public_repo_rule = do not commit or publish POTCAR contents",
        "",
        "[resources]",
        f"profile = {resources.get('profile')}",
        f"partition = {resources.get('partition')}",
        f"qos = {resources.get('qos')}",
        f"nodes = {resources.get('nodes')}",
        f"ntasks = {resources.get('ntasks')}",
        f"ntasks_per_node = {resources.get('ntasks_per_node')}",
        f"cpus_per_task = {resources.get('cpus_per_task')}",
        f"walltime = {resources.get('time')}",
        f"vasp_cmd = {resources.get('vasp_cmd')}",
        "",
        "[task_count]",
        f"total_displacements = {len(state.get('jobs', {}))}",
        f"workers = {state.get('workers')}",
        "submission_model = dynamic_worker_queue",
        "",
        "[approval]",
        "User must confirm the inputs and resources above before sbatch.",
    ]
    return "\n".join(lines) + "\n"


def review_submit(args: argparse.Namespace) -> int:
    taskset = args.taskset.resolve()
    state = load_state(taskset)
    review_text = build_submission_review(taskset, state)
    review_path = taskset / "input" / REVIEW_NAME
    atomic_write_text(review_path, review_text)
    hashes = current_input_hashes(taskset)
    approval = {
        "schema_version": 1,
        "approved": bool(args.approve),
        "approved_at": now_iso() if args.approve else None,
        "review_path": str(review_path),
        "review_hash": sha256_text(review_text),
        "input_hashes": hashes,
        "resource_hash": state["resource_hash"],
        "workers": state["workers"],
    }
    atomic_write_json(taskset / "input" / APPROVAL_NAME, approval)
    print(review_text.rstrip())
    print(f"[wrote] {review_path}")
    if args.approve:
        print("[approved] submission_approval.json marks this review as approved")
    else:
        print("[pending] review written; pass --approved to submit only after user confirmation")
    return 0


def validate_approval(taskset: Path, state: dict[str, Any], approved_flag: bool) -> None:
    review_path = taskset / "input" / REVIEW_NAME
    approval_path = taskset / "input" / APPROVAL_NAME
    if not review_path.exists():
        raise RuntimeError(f"missing submit review: {review_path}")
    review_text = review_path.read_text(encoding="utf-8")
    current_hashes = current_input_hashes(taskset)
    if current_hashes != state.get("input_hashes"):
        raise RuntimeError("input hashes changed since prepare; regenerate review before submit")
    if resource_hash(state["resources"], int(state["workers"])) != state.get("resource_hash"):
        raise RuntimeError("resource envelope changed since prepare; regenerate review before submit")
    if not approved_flag:
        if not approval_path.exists():
            raise RuntimeError("missing approval file; use review submit --approve or pass --approved after user confirmation")
        approval = load_json(approval_path)
        if not approval.get("approved"):
            raise RuntimeError("submission_approval.json is not approved; pass --approved only after user confirmation")
        if approval.get("review_hash") != sha256_text(review_text):
            raise RuntimeError("approval hash does not match current submission_review.dat")
        if approval.get("input_hashes") != current_hashes:
            raise RuntimeError("approval input hashes do not match current inputs")


def submit_workers(args: argparse.Namespace) -> int:
    taskset = args.taskset.resolve()
    state = load_state(taskset)
    validate_approval(taskset, state, args.approved)
    sbatch = shutil.which("sbatch")
    if not args.dry_run and sbatch is None:
        raise RuntimeError("sbatch not found; use --dry-run or run on a Slurm login node")

    submitted = 0
    for worker_id in sorted(state["workers_state"]):
        worker_state = state["workers_state"][worker_id]
        if worker_state.get("job_id") and not args.resubmit:
            continue
        worker_dir = taskset / "workers" / worker_id
        script = worker_dir / "submit.slurm"
        if not script.exists():
            raise FileNotFoundError(script)
        print(f"[submit-worker] {worker_id}: {script}")
        if args.dry_run:
            submitted += 1
            continue
        result = subprocess.run([sbatch, "submit.slurm"], cwd=worker_dir, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode != 0:
            raise RuntimeError(f"sbatch failed for {worker_id}: {result.stderr.strip()}")
        match = JOB_ID_RE.search(result.stdout)
        if not match:
            raise RuntimeError(f"cannot parse job id from sbatch output: {result.stdout!r}")
        worker_state["job_id"] = match.group(1)
        worker_state["status"] = "submitted"
        worker_state["submitted_at"] = now_iso()
        submitted += 1
    if not args.dry_run:
        save_state(taskset, state)
    print(f"[ok] workers submitted={submitted} dry_run={args.dry_run}")
    return 0


def claim_next_job(taskset: Path, worker_id: str) -> tuple[str, Path] | None:
    with queue_lock(taskset):
        state = load_state(taskset)
        undo_dir = taskset / "queue" / "undo"
        candidates = sorted(p for p in undo_dir.iterdir() if not p.name.startswith("."))
        if not candidates:
            return None
        marker = candidates[0]
        label = marker.name
        calculating_marker = taskset / "queue" / "calculating" / label
        move_marker(marker, calculating_marker)
        job = state["jobs"][label]
        job["status"] = "calculating"
        job["worker"] = worker_id
        job["attempts"] = int(job.get("attempts", 0)) + 1
        job["started_at"] = now_iso()
        job["updated_at"] = now_iso()
        save_state(taskset, state)
        log_queue(taskset, f"{worker_id} claimed {label}")
        return label, taskset / job["path"]


def finish_job(taskset: Path, label: str, status: str, reason: str) -> None:
    if status not in {"done", "failed"}:
        raise ValueError(status)
    with queue_lock(taskset):
        state = load_state(taskset)
        src = taskset / "queue" / "calculating" / label
        dst = taskset / "queue" / status / label
        if src.exists() or src.is_symlink():
            move_marker(src, dst)
        job = state["jobs"][label]
        job["status"] = status
        job["finished_at"] = now_iso()
        job["updated_at"] = now_iso()
        if status == "failed":
            job["fail_reason"] = reason
            atomic_write_text(taskset / job["path"] / "fail_reason.txt", reason + "\n")
        save_state(taskset, state)
        log_queue(taskset, f"{label} -> {status}: {reason}")


def run_one_job(job_dir: Path, mock: bool) -> tuple[str, str]:
    if mock:
        if (job_dir / "mock_fail").exists():
            return "failed", "mock_fail marker present"
        atomic_write_text(job_dir / "OUTCAR", "mock VASP completed\n Voluntary context switches\n")
        atomic_write_text(job_dir / "vasp.out", "mock success\n")
        return "done", "mock success"

    script = job_dir / "run_vasp.sh"
    if not script.exists():
        return "failed", f"missing run script: {script}"
    result = subprocess.run(["sh", str(script)], cwd=job_dir)
    if result.returncode != 0:
        return "failed", f"run_vasp.sh exited {result.returncode}"
    return "done", "run_vasp.sh exited 0"


def worker_run(args: argparse.Namespace) -> int:
    taskset = args.taskset.resolve()
    worker_id = args.worker_id
    completed = 0
    start = time.monotonic()
    while True:
        if args.max_jobs and completed >= args.max_jobs:
            break
        if args.walltime_guard_seconds and time.monotonic() - start > args.walltime_guard_seconds:
            print(f"[guard] {worker_id} stopping before walltime guard")
            break
        claimed = claim_next_job(taskset, worker_id)
        if claimed is None:
            print(f"[empty] {worker_id}: no undo jobs left")
            break
        label, job_dir = claimed
        print(f"[run] {worker_id}: {label} -> {job_dir}")
        status, reason = run_one_job(job_dir, args.mock)
        finish_job(taskset, label, status, reason)
        completed += 1
    print(f"[ok] {worker_id} processed {completed} jobs")
    return 0


def queue_status(args: argparse.Namespace) -> int:
    taskset = args.taskset.resolve()
    state = load_state(taskset)
    counts: dict[str, int] = {}
    for job in state.get("jobs", {}).values():
        status = str(job.get("status", "unknown"))
        counts[status] = counts.get(status, 0) + 1
    marker_counts = {
        name: len([p for p in (taskset / "queue" / name).iterdir() if not p.name.startswith(".")])
        for name in QUEUE_STATES
    }
    print(f"taskset = {taskset}")
    print("state_counts = " + ", ".join(f"{k}:{v}" for k, v in sorted(counts.items())))
    print("queue_markers = " + ", ".join(f"{k}:{v}" for k, v in marker_counts.items()))
    return 0


def cmd_parse(args: argparse.Namespace) -> int:
    task_dir = args.task_dir.resolve()
    result = parse_task_dir(task_dir)
    if args.write and task_dir.exists():
        atomic_write_json(task_dir / "parse_result.json", result)
    if args.as_json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        for line in format_summary(result):
            print(line)
        if args.write and task_dir.exists():
            print(f"[ok] wrote {task_dir / 'parse_result.json'}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="vwf", description="VASP workflow helper for skill-managed tasks.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init-case")
    p_init.add_argument("--case-root", type=Path, required=True)
    p_init.set_defaults(func=init_case)

    p_prepare = sub.add_parser("prepare")
    prep_sub = p_prepare.add_subparsers(dest="prepare_cmd", required=True)
    p_fd = prep_sub.add_parser("phonon-fd")
    p_fd.add_argument("--case-root", type=Path, required=True)
    p_fd.add_argument("--taskset", required=True)
    p_fd.add_argument("--source-dir", type=Path, default=None)
    p_fd.add_argument("--dim", default="1 1 1")
    p_fd.add_argument("--displacement-distance", type=float, default=0.01)
    p_fd.add_argument("--workers", type=int, default=5)
    p_fd.add_argument("--profile", choices=sorted(PROFILE_DEFAULTS), default="generic")
    p_fd.add_argument("--partition", default=None)
    p_fd.add_argument("--qos", default=None)
    p_fd.add_argument("--nodes", type=int, default=None)
    p_fd.add_argument("--ntasks", type=int, default=None)
    p_fd.add_argument("--ntasks-per-node", type=int, default=None, dest="ntasks_per_node")
    p_fd.add_argument("--cpus-per-task", type=int, default=None, dest="cpus_per_task")
    p_fd.add_argument("--time", default=None)
    p_fd.add_argument("--vasp-cmd", default=None)
    p_fd.add_argument("--phonopy-bin", default="phonopy")
    p_fd.add_argument("--incar-template", type=Path, default=None)
    p_fd.add_argument("--copy-source-incar", action="store_true")
    p_fd.add_argument("--mock-displacements", type=int, default=0)
    p_fd.add_argument("--overwrite", action="store_true")
    p_fd.set_defaults(func=prepare_phonon_fd)

    p_review = sub.add_parser("review")
    review_sub = p_review.add_subparsers(dest="review_cmd", required=True)
    p_review_submit = review_sub.add_parser("submit")
    p_review_submit.add_argument("--taskset", type=Path, required=True)
    p_review_submit.add_argument("--approve", action="store_true")
    p_review_submit.set_defaults(func=review_submit)

    p_submit = sub.add_parser("submit")
    submit_sub = p_submit.add_subparsers(dest="submit_cmd", required=True)
    p_workers = submit_sub.add_parser("workers")
    p_workers.add_argument("--taskset", type=Path, required=True)
    p_workers.add_argument("--approved", action="store_true")
    p_workers.add_argument("--dry-run", action="store_true")
    p_workers.add_argument("--resubmit", action="store_true")
    p_workers.set_defaults(func=submit_workers)

    p_worker = sub.add_parser("worker")
    worker_sub = p_worker.add_subparsers(dest="worker_cmd", required=True)
    p_run = worker_sub.add_parser("run")
    p_run.add_argument("--taskset", type=Path, required=True)
    p_run.add_argument("--worker-id", required=True)
    p_run.add_argument("--max-jobs", type=int, default=0)
    p_run.add_argument("--walltime-guard-seconds", type=int, default=0)
    p_run.add_argument("--mock", action="store_true")
    p_run.set_defaults(func=worker_run)

    p_queue = sub.add_parser("queue")
    queue_sub = p_queue.add_subparsers(dest="queue_cmd", required=True)
    p_status = queue_sub.add_parser("status")
    p_status.add_argument("--taskset", type=Path, required=True)
    p_status.set_defaults(func=queue_status)

    p_parse = sub.add_parser("parse", help="Parse a finished task dir for convergence/energy/forces/errors.")
    p_parse.add_argument("--task-dir", type=Path, required=True)
    p_parse.add_argument("--json", action="store_true", dest="as_json", help="Emit the full result as JSON.")
    p_parse.add_argument("--write", action="store_true", help="Write parse_result.json into the task dir.")
    p_parse.set_defaults(func=cmd_parse)

    p_auto = sub.add_parser("automation")
    auto_sub = p_auto.add_subparsers(dest="automation_cmd", required=True)
    p_auto_init = auto_sub.add_parser("init")
    p_auto_init.add_argument("--case-root", type=Path, required=True)
    p_auto_init.add_argument("--overwrite", action="store_true")
    p_auto_init.set_defaults(func=automation_init)
    p_auto_tick = auto_sub.add_parser("tick")
    p_auto_tick.add_argument("--case-root", type=Path, required=True)
    p_auto_tick.add_argument("--dry-run", action="store_true")
    p_auto_tick.set_defaults(func=automation_tick)
    p_auto_cron = auto_sub.add_parser("cron-line")
    p_auto_cron.add_argument("--case-root", type=Path, required=True)
    p_auto_cron.add_argument("--interval-minutes", type=int, default=10)
    p_auto_cron.set_defaults(func=automation_cron_line)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except Exception as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 1
