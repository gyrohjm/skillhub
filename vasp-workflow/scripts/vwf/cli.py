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


SKILL_ROOT = Path(__file__).resolve().parents[2]
JOBVASP_TEMPLATE = SKILL_ROOT / "assets" / "templates" / "jobvasp.sh"
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
ATTEMPT_ARCHIVE_FILES = ("OUTCAR", "OSZICAR", "CONTCAR", "vasp.out", "vasp.err")
DEFAULT_POTCAR_FUNCTIONAL = "PBE"
DEFAULT_RELAX_EDIFF = "1E-6"
DEFAULT_RELAX_EDIFFG = "-0.01"
DEFAULT_RELAX_NSW = 80
DEFAULT_SCF_EDIFF = "1E-7"
SLUG_RE = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")
DEFAULT_CLUSTER_CASE_ROOT = Path("/home/jmhe/project")
INCAR_PRESETS = ("standard", "magnetic-vdw-relax")
MAGNETIC_VDW_MAGMOM = "0.05 -0.05 0.05 -0.05 0.05 -0.05 0.05 -0.05"
PROFILE_POTCAR_ROOTS = {
    "nmg": Path("/home/jmhe/app/pot"),
    "phoenix": Path("/home/jmhe/app/pot_database"),
    "phoenix-gpu-a100": Path("/home/jmhe/app/pot_database"),
    "phoenix-gpu-g3": Path("/home/jmhe/app/pot_database"),
}

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
        "account": "",
        "nodelist": "",
        "gres": "",
        "nodes": 1,
        "ntasks_per_node": 1,
        "cpus_per_task": 1,
        "time": "24:00:00",
        "vasp_cmd": "srun vasp_std",
    },
    "nmg": {
        "partition": "Nano",
        "qos": "",
        "account": "",
        "nodelist": "",
        "gres": "",
        "nodes": 1,
        "ntasks_per_node": 40,
        "cpus_per_task": 1,
        "time": "",
        "vasp_cmd": "module load intel_parallel; module load vasp/6.4.2/avx512/orig; ulimit -s unlimited; srun -n $SLURM_NTASKS vasp_std",
    },
    "phoenix": {
        "partition": "Phoenix",
        "qos": "huge",
        "account": "",
        "nodelist": "",
        "gres": "",
        "nodes": 1,
        "ntasks_per_node": 112,
        "cpus_per_task": 1,
        "time": "",
        "vasp_cmd": "module load intel_parallel; module load vasp6.4.2-avx512; unset I_MPI_PMI_LIBRARY; ulimit -s unlimited; srun vasp_std",
    },
    "phoenix-gpu-a100": {
        "partition": "Phoenix-GPU",
        "qos": "",
        "account": "nano",
        "nodelist": "g1",
        "gres": "gpu:a100:1",
        "nodes": 1,
        "ntasks_per_node": 1,
        "cpus_per_task": 8,
        "time": "",
        "vasp_cmd": "\n".join([
            "module load nvhpc/22.9_mu",
            "module load cuda/12.1",
            "module load gcc/12.3",
            "module load vasp6.3.2-gpu-mkl",
            "export OMP_NUM_THREADS=$SLURM_CPUS_PER_TASK",
            "export OMP_PLACES=cores",
            "export OMP_PROC_BIND=close",
            "export OMPI_MCA_btl_openib_warn_no_device_params_found=0",
            "echo \"SLURM_NTASKS = $SLURM_NTASKS\"",
            "echo \"SLURM_CPUS_PER_TASK = $SLURM_CPUS_PER_TASK\"",
            "echo \"OMP_NUM_THREADS = $OMP_NUM_THREADS\"",
            "echo \"CUDA_VISIBLE_DEVICES = $CUDA_VISIBLE_DEVICES\"",
            "nvidia-smi",
            "mpirun -np $SLURM_NTASKS vasp_std",
        ]),
    },
    "phoenix-gpu-g3": {
        "partition": "Phoenix-GPU",
        "qos": "",
        "account": "nano",
        "nodelist": "g3",
        "gres": "gpu:h100:1",
        "nodes": 1,
        "ntasks_per_node": 1,
        "cpus_per_task": 5,
        "time": "",
        "vasp_cmd": "\n".join([
            "module load nvhpc/22.9_mu",
            "module load cuda/12.1",
            "module load gcc/12.3",
            "module load vasp6.3.2-gpu-mkl",
            "export OMP_NUM_THREADS=$SLURM_CPUS_PER_TASK",
            "export OMP_PLACES=cores",
            "export OMP_PROC_BIND=close",
            "export OMPI_MCA_btl_openib_warn_no_device_params_found=0",
            "echo \"SLURM_NTASKS = $SLURM_NTASKS\"",
            "echo \"SLURM_CPUS_PER_TASK = $SLURM_CPUS_PER_TASK\"",
            "echo \"OMP_NUM_THREADS = $OMP_NUM_THREADS\"",
            "echo \"CUDA_VISIBLE_DEVICES = $CUDA_VISIBLE_DEVICES\"",
            "nvidia-smi",
            "mpirun -np $SLURM_NTASKS vasp_std",
        ]),
    },
}

STANDARD_STAGE_PATHS = {
    "relax": "relax",
    "scf": "electronic/scf",
    "band": "electronic/band",
    "dos": "electronic/dos",
}

FCC_BAND_PATH = ["G", "X", "W", "K", "G", "L", "U", "W", "L", "K"]
FCC_KPOINTS = {
    "G": (0.0, 0.0, 0.0),
    "X": (0.0, 0.5, 0.5),
    "W": (0.25, 0.75, 0.5),
    "K": (0.375, 0.75, 0.375),
    "L": (0.5, 0.5, 0.5),
    "U": (0.625, 0.625, 0.25),
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


def verify_design_approval(
    approval_path: Path,
    matrix_id: str,
    stage: str,
    case_meta: dict[str, Any],
) -> dict[str, Any]:
    approval_path = approval_path.expanduser().resolve()
    if not approval_path.is_file():
        raise FileNotFoundError(f"scientific design approval does not exist: {approval_path}")
    approval = load_json(approval_path)
    required = {
        "schema_version",
        "approval_type",
        "status",
        "design_id",
        "revision",
        "scope",
        "reviewer",
        "approved_at",
        "design_file",
        "design_sha256",
        "computation_plan_file",
        "computation_plan_sha256",
    }
    missing = sorted(required - set(approval))
    if missing:
        raise ValueError(f"scientific design approval is missing fields: {missing}")
    if (
        approval["schema_version"] != 1
        or approval["approval_type"] != "scientific_design"
        or approval["status"] != "approved"
    ):
        raise ValueError("scientific design approval header is invalid")
    if not isinstance(approval["scope"], list) or not approval["scope"]:
        raise ValueError("scientific design approval scope must be a non-empty list")
    if matrix_id not in approval["scope"]:
        raise ValueError(f"design matrix {matrix_id!r} is not in approved scope {approval['scope']}")

    design_name = Path(str(approval["design_file"]))
    plan_name = Path(str(approval["computation_plan_file"]))
    if design_name.name != str(design_name) or plan_name.name != str(plan_name):
        raise ValueError("scientific design snapshot file names must not contain directories")
    design_path = approval_path.parent / design_name
    plan_path = approval_path.parent / plan_name
    if sha256_file(design_path) != approval["design_sha256"]:
        raise ValueError("scientific design JSON hash does not match approval")
    if sha256_file(plan_path) != approval["computation_plan_sha256"]:
        raise ValueError("scientific computation plan hash does not match approval")
    design = load_json(design_path)
    if design.get("design_id") != approval["design_id"] or design.get("revision") != approval["revision"]:
        raise ValueError("scientific design ID or revision does not match approval")
    if design.get("status") != "ready_for_review":
        raise ValueError("approved scientific design snapshot must have status ready_for_review")
    matrix = next((item for item in design.get("calculation_matrix", []) if item.get("id") == matrix_id), None)
    if matrix is None:
        raise ValueError(f"approved scientific design does not contain matrix {matrix_id!r}")
    if stage not in matrix.get("stages", []):
        raise ValueError(f"stage {stage!r} is not listed for design matrix {matrix_id!r}")
    expected_system = case_meta.get("system_slug")
    expected_case = case_meta.get("case_slug")
    if expected_system and matrix.get("system_slug") != expected_system:
        raise ValueError(
            f"design matrix system_slug {matrix.get('system_slug')!r} does not match requested {expected_system!r}"
        )
    if expected_case and matrix.get("case_slug") != expected_case:
        raise ValueError(f"design matrix case_slug {matrix.get('case_slug')!r} does not match requested {expected_case!r}")
    return {
        "status": "approved",
        "scientific_design_approved": True,
        "design_id": approval["design_id"],
        "design_revision": approval["revision"],
        "matrix_id": matrix_id,
        "task_class": matrix.get("class"),
        "design_sha256": approval["design_sha256"],
        "computation_plan_sha256": approval["computation_plan_sha256"],
        "approval_sha256": sha256_file(approval_path),
        "approval_source": str(approval_path),
        "design_source": str(design_path.resolve()),
        "computation_plan_source": str(plan_path.resolve()),
    }


def resolve_design_provenance(args: argparse.Namespace, stage: str, case_meta: dict[str, Any]) -> dict[str, Any]:
    approval_path = getattr(args, "design_approval", None)
    matrix_id = getattr(args, "design_task", None)
    if bool(approval_path) != bool(matrix_id):
        raise ValueError("--design-approval and --design-task must be provided together")
    if not approval_path:
        return {
            "status": "exploratory_untracked",
            "scientific_design_approved": False,
            "note": "CLI-compatible exploratory task; do not auto-advance to production without computation-design approval",
        }
    return verify_design_approval(approval_path, matrix_id, stage, case_meta)


def snapshot_design_review(case_root: Path, provenance: dict[str, Any]) -> dict[str, Any]:
    if not provenance.get("scientific_design_approved"):
        return provenance
    destination = (
        case_root
        / "design"
        / str(provenance["design_id"])
        / f"r{int(provenance['design_revision']):04d}"
    )
    destination.mkdir(parents=True, exist_ok=True)
    sources = {
        "calculation_design.json": Path(provenance["design_source"]),
        "computation_plan.md": Path(provenance["computation_plan_source"]),
        "approval.json": Path(provenance["approval_source"]),
    }
    for name, source in sources.items():
        target = destination / name
        if target.exists():
            if sha256_file(target) != sha256_file(source):
                raise ValueError(f"conflicting immutable scientific design snapshot: {target}")
            continue
        shutil.copy2(source, target)
    result = dict(provenance)
    result["case_snapshot"] = str(destination)
    return result


def record_design_in_workflow(case_root: Path, provenance: dict[str, Any]) -> None:
    if not provenance.get("scientific_design_approved"):
        return
    workflow_path = case_root / "workflow.json"
    workflow = load_json(workflow_path) if workflow_path.exists() else {
        "schema_version": 1,
        "case_root": str(case_root),
        "created_at": now_iso(),
    }
    records = workflow.setdefault("scientific_designs", [])
    record = {
        key: provenance[key]
        for key in (
            "design_id",
            "design_revision",
            "matrix_id",
            "task_class",
            "design_sha256",
            "approval_sha256",
            "case_snapshot",
        )
    }
    if record not in records:
        records.append(record)
    atomic_write_json(workflow_path, workflow)


def validate_slug(name: str, value: str | None) -> str | None:
    if value is None:
        return None
    if not SLUG_RE.fullmatch(value):
        raise ValueError(f"{name} must use English lowercase_snake_case; got {value!r}")
    return value


def resolve_case_root(args: argparse.Namespace) -> tuple[Path, dict[str, Any]]:
    project = validate_slug("project_slug", getattr(args, "project_slug", None))
    system = validate_slug("system_slug", getattr(args, "system_slug", None))
    case = validate_slug("case_slug", getattr(args, "case_slug", None))
    cluster = getattr(args, "cluster", "generic")
    explicit = getattr(args, "case_root", None)
    if explicit is not None:
        root = explicit.resolve()
        source = "explicit --case-root"
    else:
        missing = [
            name for name, value in (
                ("--project-slug", project),
                ("--system-slug", system),
                ("--case-slug", case),
            )
            if not value
        ]
        if missing:
            raise ValueError("--case-root or all of --project-slug, --system-slug, and --case-slug is required")
        root = DEFAULT_CLUSTER_CASE_ROOT / str(project) / "calculations" / str(system) / str(case)
        source = "derived from project/system/case default cluster layout"
    return root, {
        "project_slug": project,
        "system_slug": system,
        "case_slug": case,
        "cluster": cluster,
        "case_root_source": source,
        "case_root": str(root),
    }


def add_case_args(parser: argparse.ArgumentParser, *, require_case_root: bool = False) -> None:
    parser.add_argument("--case-root", type=Path, required=require_case_root)
    parser.add_argument("--cluster", choices=("nmg", "phoenix", "generic"), default="generic")
    parser.add_argument("--project-slug")
    parser.add_argument("--system-slug")
    parser.add_argument("--case-slug")


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


def poscar_elements(path: Path) -> list[str]:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    if len(lines) < 7:
        raise ValueError(f"POSCAR is too short to read element order: {path}")
    symbols = lines[5].split()
    counts = lines[6].split()
    if not symbols or not all(re.fullmatch(r"[A-Z][A-Za-z0-9_]*", item) for item in symbols):
        raise ValueError(
            "POSCAR must include a VASP 5 element-symbol line so POTCAR can be resolved automatically"
        )
    if not counts or not all(item.isdigit() for item in counts):
        raise ValueError(f"POSCAR element count line is invalid: {path}")
    return symbols


def parse_potcar_labels(items: list[str] | None) -> dict[str, str]:
    labels: dict[str, str] = {}
    for item in items or []:
        if "=" not in item:
            raise argparse.ArgumentTypeError("--potcar-label must use ELEMENT=LABEL")
        element, label = item.split("=", 1)
        element = element.strip()
        label = label.strip()
        if not element or not label:
            raise argparse.ArgumentTypeError("--potcar-label must use non-empty ELEMENT=LABEL")
        labels[element] = label
    return labels


def default_potcar_root(profile: str) -> Path | None:
    return PROFILE_POTCAR_ROOTS.get(profile)


def potcar_candidates(root: Path, label: str) -> list[Path]:
    if not root.exists():
        return []
    candidates: set[Path] = set()
    direct = root / label / "POTCAR"
    if direct.is_file():
        candidates.add(direct.resolve())
    for path in root.rglob("POTCAR"):
        if path.is_file() and path.parent.name == label:
            candidates.add(path.resolve())
    return sorted(candidates)


def resolve_potcar(args: argparse.Namespace, poscar_src: Path, task_dir: Path) -> tuple[Path, dict[str, Any]]:
    if args.potcar is not None:
        potcar_src = args.potcar.resolve()
        if not potcar_src.exists():
            raise FileNotFoundError(f"POTCAR source does not exist: {potcar_src}")
        copy_or_link(potcar_src, task_dir / "POTCAR")
        return potcar_src, {
            "mode": "explicit",
            "source": str(potcar_src),
            "root": "",
            "components": [],
        }

    root = args.potcar_root.resolve() if args.potcar_root else default_potcar_root(args.profile)
    if root is None:
        raise ValueError("generic profile has no default POTCAR root; pass --potcar or --potcar-root")
    labels = parse_potcar_labels(args.potcar_label)
    components: list[dict[str, Any]] = []
    problems: list[str] = []
    for element in poscar_elements(poscar_src):
        label = labels.get(element, element)
        candidates = potcar_candidates(root, label)
        if not candidates:
            problems.append(f"{element}: no POTCAR found for label {label!r} under {root}")
            continue
        if len(candidates) > 1:
            listed = ", ".join(str(path) for path in candidates[:12])
            problems.append(f"{element}: multiple POTCAR candidates for label {label!r}: {listed}")
            continue
        path = candidates[0]
        components.append({
            "element": element,
            "label": label,
            "path": str(path),
            "title": read_potcar_summary(path),
            "sha256": sha256_file(path),
        })
    if problems:
        raise ValueError("POTCAR auto-resolution failed; confirm --potcar or --potcar-label. " + " | ".join(problems))

    task_dir.mkdir(parents=True, exist_ok=True)
    with (task_dir / "POTCAR").open("wb") as out:
        for component in components:
            out.write(Path(component["path"]).read_bytes())
            out.write(b"\n")
    return task_dir / "POTCAR", {
        "mode": "auto",
        "source": str(task_dir / "POTCAR"),
        "root": str(root),
        "components": components,
    }


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
    for key in ("partition", "qos", "account", "nodelist", "gres", "time", "vasp_cmd"):
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


def standard_task_path(case_root: Path, kind: str) -> Path:
    if kind not in STANDARD_STAGE_PATHS:
        raise ValueError(f"unsupported standard task kind: {kind}")
    return case_root.resolve() / STANDARD_STAGE_PATHS[kind]


def standard_hashes(task_dir: Path) -> dict[str, str]:
    names = ("POSCAR", "POSCAR-ini", "INCAR", "KPOINTS", "POTCAR", "job.sh")
    return {name: sha256_file(task_dir / name) for name in names if (task_dir / name).exists()}


def find_structure_source(kind: str, case_root: Path, explicit: Path | None, source_dir: Path | None) -> tuple[Path, str]:
    if explicit is not None:
        path = explicit.resolve()
        if not path.exists():
            raise FileNotFoundError(path)
        return path, "explicit --source-poscar"
    if source_dir is not None:
        source = source_dir.resolve()
        for name in ("CONTCAR", "POSCAR"):
            path = source / name
            if path.exists():
                return path, f"{source}/{name}"
        raise FileNotFoundError(f"source dir has no CONTCAR or POSCAR: {source}")
    if kind == "relax":
        path = case_root / "structure" / "POSCAR.initial"
        if path.exists():
            return path.resolve(), "structure/POSCAR.initial"
    if kind in {"scf", "band", "dos"}:
        path = case_root / "relax" / "CONTCAR"
        if path.exists():
            return path.resolve(), "relax/CONTCAR"
    raise FileNotFoundError("provide --source-poscar or --source-dir so the structure source is explicit")


def write_mesh_kpoints(mesh: tuple[int, int, int]) -> str:
    return "\n".join([
        "Automatic mesh",
        "0",
        "Gamma",
        dim_to_str(mesh),
        "0 0 0",
        "",
    ])


def write_fcc_band_kpoints(line_points: int) -> str:
    lines = [
        "FCC path G-X-W-K-G-L-U-W-L-K",
        str(line_points),
        "Line-mode",
        "reciprocal",
    ]
    for start, end in zip(FCC_BAND_PATH, FCC_BAND_PATH[1:]):
        a = FCC_KPOINTS[start]
        b = FCC_KPOINTS[end]
        lines.append(f"{a[0]:.8f} {a[1]:.8f} {a[2]:.8f} ! {start}")
        lines.append(f"{b[0]:.8f} {b[1]:.8f} {b[2]:.8f} ! {end}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def incar_line(key: str, value: Any) -> str:
    return f"{key} = {value}"


def render_incar_sections(sections: list[tuple[str, list[str]]]) -> str:
    lines: list[str] = []
    for title, entries in sections:
        if not entries:
            continue
        if lines:
            lines.append("")
        lines.append(f"# --- {title} ---")
        lines.extend(entries)
    return "\n".join(lines).rstrip() + "\n"


def build_magnetic_vdw_relax_incar(args: argparse.Namespace) -> str:
    if args.task_kind != "relax":
        raise ValueError("--incar-preset magnetic-vdw-relax is only valid for relax tasks")
    encut = args.encut if args.encut is not None else 520
    nsw = args.nsw if args.nsw is not None else 100
    isif = args.isif if args.isif is not None else 2
    return render_incar_sections([
        ("global", [
            incar_line("SYSTEM", "magnetic vdW relax generated by vwf"),
            incar_line("ENCUT", encut),
            incar_line("PREC", "Accurate"),
            incar_line("GGA", "PE"),
            incar_line("IVDW", 12),
            incar_line("LASPH", ".TRUE."),
            incar_line("LREAL", ".FALSE."),
            incar_line("ISYM", 0),
        ]),
        ("electronic", [
            incar_line("ISPIN", 2),
            incar_line("MAGMOM", args.magmom or MAGNETIC_VDW_MAGMOM),
            incar_line("NCORE", args.ncore if args.ncore is not None else 14),
            incar_line("LORBIT", args.lorbit),
            incar_line("ADDGRID", ".TRUE."),
            incar_line("ISTART", 0),
            incar_line("ICHARG", 2),
            incar_line("EDIFF", standard_ediff("relax", args)),
            incar_line("ISMEAR", args.ismear),
            incar_line("SIGMA", args.sigma),
        ]),
        ("ionic", [
            incar_line("EDIFFG", args.ediffg),
            incar_line("IBRION", args.ibrion),
            incar_line("NSW", nsw),
            incar_line("ISIF", isif),
        ]),
        ("output", [
            incar_line("LWAVE", ".FALSE."),
            incar_line("LCHARG", ".FALSE."),
        ]),
    ])


def build_standard_incar(kind: str, args: argparse.Namespace) -> str:
    if args.incar_preset == "magnetic-vdw-relax":
        return build_magnetic_vdw_relax_incar(args)
    if args.encut is None:
        raise ValueError("--encut is required when using the built-in INCAR template")
    ediff = standard_ediff(kind, args)
    nsw = args.nsw if args.nsw is not None else DEFAULT_RELAX_NSW
    isif = args.isif if args.isif is not None else 3
    global_entries = [
        incar_line("SYSTEM", f"{kind} generated by vwf"),
        incar_line("PREC", "Accurate"),
        incar_line("ENCUT", args.encut),
        incar_line("LREAL", ".FALSE."),
    ]
    electronic_entries = [
        incar_line("EDIFF", ediff),
        incar_line("ISMEAR", args.ismear),
        incar_line("SIGMA", args.sigma),
    ]
    if args.ncore:
        electronic_entries.append(incar_line("NCORE", args.ncore))
    ionic_entries: list[str] = []
    output_entries: list[str] = []
    if kind == "relax":
        ionic_entries += [
            incar_line("EDIFFG", args.ediffg),
            incar_line("IBRION", args.ibrion),
            incar_line("NSW", nsw),
            incar_line("ISIF", isif),
        ]
        output_entries += [
            incar_line("LWAVE", ".FALSE."),
            incar_line("LCHARG", ".FALSE."),
        ]
    elif kind == "scf":
        ionic_entries += [
            incar_line("IBRION", -1),
            incar_line("NSW", 0),
            incar_line("ISIF", 2),
        ]
        output_entries += [
            incar_line("LWAVE", ".TRUE."),
            incar_line("LCHARG", ".TRUE."),
        ]
    elif kind == "band":
        electronic_entries += [
            incar_line("ICHARG", 11),
            incar_line("LORBIT", args.lorbit),
        ]
        ionic_entries += [
            incar_line("IBRION", -1),
            incar_line("NSW", 0),
        ]
        output_entries += [
            incar_line("LWAVE", ".FALSE."),
            incar_line("LCHARG", ".FALSE."),
        ]
    elif kind == "dos":
        electronic_entries += [
            incar_line("ICHARG", 11),
            incar_line("LORBIT", args.lorbit),
            incar_line("NEDOS", args.nedos),
        ]
        ionic_entries += [
            incar_line("IBRION", -1),
            incar_line("NSW", 0),
        ]
        output_entries += [
            incar_line("LWAVE", ".FALSE."),
            incar_line("LCHARG", ".FALSE."),
        ]
    else:
        raise ValueError(kind)
    return render_incar_sections([
        ("global", global_entries),
        ("electronic", electronic_entries),
        ("ionic", ionic_entries),
        ("output", output_entries),
    ])


def standard_ediff(kind: str, args: argparse.Namespace) -> str:
    if args.ediff is not None:
        return str(args.ediff)
    if kind == "scf":
        return DEFAULT_SCF_EDIFF
    return DEFAULT_RELAX_EDIFF


def incar_default_metadata(kind: str, args: argparse.Namespace, used_builtin_template: bool) -> dict[str, Any]:
    if not used_builtin_template:
        return {"source": "explicit template", "built_in_defaults": {}, "defaulted": [], "overridden": []}
    if args.incar_preset == "magnetic-vdw-relax":
        if kind != "relax":
            return {"source": "built-in magnetic-vdw-relax preset", "built_in_defaults": {}, "defaulted": [], "overridden": []}
        defaults = {
            "ENCUT": 520,
            "PREC": "Accurate",
            "ISPIN": 2,
            "MAGMOM": MAGNETIC_VDW_MAGMOM,
            "NCORE": 14,
            "GGA": "PE",
            "IVDW": 12,
            "LASPH": ".TRUE.",
            "LREAL": ".FALSE.",
            "ISYM": 0,
            "LORBIT": 11,
            "ADDGRID": ".TRUE.",
            "ISTART": 0,
            "ICHARG": 2,
            "EDIFF": DEFAULT_RELAX_EDIFF,
            "EDIFFG": DEFAULT_RELAX_EDIFFG,
            "IBRION": 2,
            "NSW": 100,
            "ISIF": 2,
            "ISMEAR": 0,
            "SIGMA": "0.05",
            "LWAVE": ".FALSE.",
            "LCHARG": ".FALSE.",
        }
        effective = defaults.copy()
        effective.update({
            "ENCUT": int(args.encut) if args.encut is not None else 520,
            "MAGMOM": args.magmom or MAGNETIC_VDW_MAGMOM,
            "NCORE": int(args.ncore) if args.ncore is not None else 14,
            "EDIFF": standard_ediff(kind, args),
            "EDIFFG": str(args.ediffg),
            "IBRION": int(args.ibrion),
            "NSW": int(args.nsw) if args.nsw is not None else 100,
            "ISIF": int(args.isif) if args.isif is not None else 2,
            "ISMEAR": int(args.ismear),
            "SIGMA": str(args.sigma),
            "LORBIT": int(args.lorbit),
        })
        defaulted = [key for key, value in defaults.items() if effective.get(key) == value]
        overridden = [
            {"key": key, "default": defaults[key], "effective": effective[key]}
            for key in defaults
            if effective.get(key) != defaults[key]
        ]
        return {
            "source": "built-in magnetic-vdw-relax preset grouped by global/electronic/ionic/output",
            "built_in_defaults": defaults,
            "defaulted": defaulted,
            "overridden": overridden,
            "ediff_policy": "magnetic-vdw-relax uses EDIFF=1E-6 by default; changes require review envelope approval",
            "relax_ediffg_policy": "magnetic-vdw-relax uses EDIFFG=-0.01 by default; changes require review envelope approval",
            "magmom_review": "MAGMOM count and order must match POSCAR element/site order before submit",
        }
    if kind == "relax":
        defaults = {
            "EDIFF": DEFAULT_RELAX_EDIFF,
            "EDIFFG": DEFAULT_RELAX_EDIFFG,
            "NSW": DEFAULT_RELAX_NSW,
            "IBRION": 2,
            "ISIF": 3,
            "ISMEAR": 0,
            "SIGMA": "0.05",
            "PREC": "Accurate",
            "LREAL": ".FALSE.",
        }
        effective = {
            "EDIFF": standard_ediff(kind, args),
            "EDIFFG": str(args.ediffg),
            "NSW": int(args.nsw) if args.nsw is not None else DEFAULT_RELAX_NSW,
            "IBRION": int(args.ibrion),
            "ISIF": int(args.isif) if args.isif is not None else 3,
            "ISMEAR": int(args.ismear),
            "SIGMA": str(args.sigma),
            "PREC": "Accurate",
            "LREAL": ".FALSE.",
        }
        source = "built-in relax template defaults plus CLI overrides"
        policy = "relax EDIFF fixed at 1E-6 by default; any tightening requires a new review envelope"
    elif kind == "scf":
        defaults = {
            "EDIFF": DEFAULT_SCF_EDIFF,
            "IBRION": -1,
            "NSW": 0,
            "ISIF": 2,
            "ISMEAR": 0,
            "SIGMA": "0.05",
            "PREC": "Accurate",
            "LREAL": ".FALSE.",
            "LWAVE": ".TRUE.",
            "LCHARG": ".TRUE.",
        }
        effective = {
            "EDIFF": standard_ediff(kind, args),
            "IBRION": -1,
            "NSW": 0,
            "ISIF": 2,
            "ISMEAR": int(args.ismear),
            "SIGMA": str(args.sigma),
            "PREC": "Accurate",
            "LREAL": ".FALSE.",
            "LWAVE": ".TRUE.",
            "LCHARG": ".TRUE.",
        }
        source = "built-in scf template defaults plus CLI overrides"
        policy = "SCF EDIFF fixed at 1E-7 by default; changes require review envelope approval"
    else:
        return {"source": "built-in template", "built_in_defaults": {}, "defaulted": [], "overridden": []}
    defaulted = [key for key, value in defaults.items() if effective.get(key) == value]
    overridden = [
        {"key": key, "default": defaults[key], "effective": effective[key]}
        for key in defaults
        if effective.get(key) != defaults[key]
    ]
    metadata = {
        "source": source,
        "built_in_defaults": defaults,
        "defaulted": defaulted,
        "overridden": overridden,
        "ediff_policy": policy,
    }
    if kind == "relax":
        metadata["relax_ediffg_policy"] = "fixed at -0.01 by default; changes require review envelope approval"
    return metadata


def build_stage_slurm(job_name: str, resources: dict[str, Any]) -> str:
    template = JOBVASP_TEMPLATE.read_text(encoding="utf-8")

    def directive(flag: str, value: Any) -> str:
        return f"#SBATCH {flag}{value}\n" if value not in (None, "") else ""

    replacements = {
        "JOB_NAME": job_name,
        "NODES": str(resources["nodes"]),
        "NTASKS": str(resources["ntasks"]),
        "NTASKS_PER_NODE": str(resources["ntasks_per_node"]),
        "CPUS_PER_TASK": str(resources["cpus_per_task"]),
        "SBATCH_TIME": directive("-t ", resources.get("time")),
        "SBATCH_PARTITION": directive("-p ", resources.get("partition")),
        "SBATCH_QOS": directive("-q ", resources.get("qos")),
        "SBATCH_ACCOUNT": directive("-A ", resources.get("account")),
        "SBATCH_NODELIST": directive("-w ", resources.get("nodelist")),
        "SBATCH_GRES": directive("--gres=", resources.get("gres")),
        "VASP_CMD": str(resources["vasp_cmd"]),
    }
    text = template
    for key, value in replacements.items():
        text = text.replace("{{" + key + "}}", value)
    unresolved = sorted(set(re.findall(r"\{\{([A-Z0-9_]+)\}\}", text)))
    if unresolved:
        raise ValueError(f"unresolved jobvasp.sh template placeholders: {unresolved}")
    return text.rstrip() + "\n"


def copy_or_link(src: Path, dst: Path, use_link: bool = False, strict_link: bool = False) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists() or dst.is_symlink():
        dst.unlink()
    if use_link:
        try:
            dst.symlink_to(os.path.relpath(src, dst.parent))
            return
        except OSError as exc:
            if strict_link:
                raise RuntimeError(f"failed to symlink {src} -> {dst}: {exc}") from exc
            pass
    shutil.copy2(src, dst)


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
    root, case_meta = resolve_case_root(args)
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
            **case_meta,
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


def prepare_standard(args: argparse.Namespace) -> int:
    kind = args.task_kind
    case_root, case_meta = resolve_case_root(args)
    task_dir = standard_task_path(case_root, kind)
    if task_dir.exists() and any(task_dir.iterdir()) and not args.overwrite:
        raise FileExistsError(f"task directory is not empty; pass --overwrite to replace generated inputs: {task_dir}")

    design_provenance = resolve_design_provenance(args, kind, case_meta)
    design_provenance = snapshot_design_review(case_root, design_provenance)

    poscar_src, poscar_source_label = find_structure_source(kind, case_root, args.source_poscar, args.source_dir)
    potcar_src, potcar_meta = resolve_potcar(args, poscar_src, task_dir)

    task_dir.mkdir(parents=True, exist_ok=True)
    copy_or_link(poscar_src, task_dir / "POSCAR")
    if kind == "relax":
        copy_or_link(poscar_src, task_dir / "POSCAR-ini")
    if potcar_meta["mode"] == "explicit":
        copy_or_link(potcar_src, task_dir / "POTCAR")

    if args.incar_template:
        incar_src = args.incar_template.resolve()
        incar_text = incar_src.read_text(encoding="utf-8", errors="replace")
        incar_source = str(incar_src)
        used_builtin_incar = False
    else:
        incar_text = build_standard_incar(kind, args)
        incar_source = f"built-in {kind} INCAR preset {args.incar_preset} with CLI parameters"
        used_builtin_incar = True
    atomic_write_text(task_dir / "INCAR", incar_text.rstrip() + "\n")

    kpoints_metadata: dict[str, Any] = {}
    if kind == "band":
        if args.kpoints_source:
            k_src = args.kpoints_source.resolve()
            copy_or_link(k_src, task_dir / "KPOINTS")
            kpoints_metadata = {"source": str(k_src), "generator": "explicit --kpoints-source"}
        else:
            atomic_write_text(task_dir / "KPOINTS", write_fcc_band_kpoints(args.line_points))
            kpoints_metadata = {
                "source": "built-in FCC line-mode template",
                "generator": "vwf built-in fcc",
                "band_path": "G-X-W-K-G-L-U-W-L-K",
                "line_points": args.line_points,
            }
    else:
        if args.kpoints_source:
            k_src = args.kpoints_source.resolve()
            copy_or_link(k_src, task_dir / "KPOINTS")
            kpoints_metadata = {"source": str(k_src), "generator": "explicit --kpoints-source"}
        else:
            mesh = parse_triplet(args.kmesh)
            atomic_write_text(task_dir / "KPOINTS", write_mesh_kpoints(mesh))
            kpoints_metadata = {
                "source": f"built-in Gamma mesh {dim_to_str(mesh)}",
                "generator": "vwf built-in mesh",
                "mesh": list(mesh),
            }

    resources = resource_envelope(args)
    atomic_write_text(task_dir / "job.sh", build_stage_slurm(kind, resources))
    (task_dir / "job.sh").chmod(0o755)

    explicit_stage_from = list(args.stage_from or [])
    explicit_destinations = {dst_str for _, dst_str, _ in explicit_stage_from}
    automatic_stage_from: list[tuple[str, str, bool]] = []
    if kind in {"band", "dos"}:
        scf_dir = case_root / "electronic" / "scf"
        for filename in ("CHGCAR", "WAVECAR"):
            if filename in explicit_destinations:
                continue
            src = scf_dir / filename
            if src.exists():
                automatic_stage_from.append((str(src), filename, True))

    stage_from_records: list[dict[str, Any]] = []
    for origin, spec in [
        *[("automatic scf link", item) for item in automatic_stage_from],
        *[("explicit --stage-from", item) for item in explicit_stage_from],
    ]:
        src_str, dst_str, link = spec
        src = Path(src_str).resolve()
        if src.exists():
            copy_or_link(src, task_dir / dst_str, use_link=link, strict_link=link)
            stage_from_records.append({
                "source": str(src),
                "destination": dst_str,
                "mode": "symlink" if link else "copy",
                "origin": origin,
            })

    hashes = standard_hashes(task_dir)
    task_spec = {
        "schema_version": 1,
        "task_kind": kind,
        "stage": kind,
        "case_root": str(case_root),
        **case_meta,
        "task_dir": str(task_dir),
        "input_sources": {
            "POSCAR": str(poscar_src),
            "POSCAR_source_note": poscar_source_label,
            "POSCAR-ini": str(poscar_src) if kind == "relax" else "",
            "INCAR": incar_source,
            "KPOINTS": kpoints_metadata.get("source", "unknown"),
            "POTCAR": potcar_meta["source"],
            "POTCAR_functional": args.potcar_functional,
            "POTCAR_root": potcar_meta["root"],
            "POTCAR_resolution": potcar_meta["mode"],
            "job.sh": str(JOBVASP_TEMPLATE),
        },
        "POTCAR_components": potcar_meta["components"],
        "input_hashes": hashes,
        "kpoints": kpoints_metadata,
        "incar_defaults": incar_default_metadata(kind, args, used_builtin_incar),
        "resources": resources,
        "resource_hash": resource_hash(resources, 1),
        "design_provenance": design_provenance,
        "created_at": now_iso(),
    }
    if stage_from_records:
        task_spec["stage_from"] = stage_from_records
    if kind == "scf":
        task_spec["dependency"] = "relax/CONTCAR unless overridden"
    if kind in {"band", "dos"}:
        task_spec["dependency"] = "electronic/scf CHGCAR/WAVECAR unless overridden"
    atomic_write_json(task_dir / "task_spec.json", task_spec)
    record_design_in_workflow(case_root, design_provenance)
    print(f"[ok] prepared {kind}: {task_dir}")
    print(f"[next] run: python -m vwf review submit --taskset {task_dir}")
    return 0


def parse_stage_from(value: str) -> tuple[str, str, bool]:
    # src[:dst[:link]]; link is "link" or "copy".
    parts = value.split(":")
    if len(parts) == 1:
        src = parts[0]
        dst = Path(src).name
        link = False
    elif len(parts) == 2:
        src, dst = parts
        link = False
    elif len(parts) == 3:
        src, dst, mode = parts
        link = mode == "link"
        if mode not in {"link", "copy"}:
            raise argparse.ArgumentTypeError("stage-from mode must be 'link' or 'copy'")
    else:
        raise argparse.ArgumentTypeError("expected src[:dst[:link|copy]]")
    return src, dst, link


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
                "preapproved_by_workflow": False,
                "workflow_preapproval_note": "Set true only when the initial reviewed computation plan already covers this stage's exact inputs/resources.",
                # Existence gate first (don't parse a half-written run), then the
                # authoritative check: ionic convergence via `vwf parse`.
                "completion_files": ["CONTCAR", "OUTCAR"],
                "incar_defaults": {
                    "EDIFF": DEFAULT_RELAX_EDIFF,
                    "EDIFFG": DEFAULT_RELAX_EDIFFG,
                    "NSW": DEFAULT_RELAX_NSW,
                    "IBRION": 2,
                    "ISIF": 3,
                    "ISMEAR": 0,
                    "SIGMA": "0.05",
                    "PREC": "Accurate",
                    "LREAL": ".FALSE.",
                },
                "relax_ediff_policy": "fixed at 1E-6 by default; changes require review envelope approval",
                "relax_ediffg_policy": "fixed at -0.01 by default; changes require review envelope approval",
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
                "preapproved_by_workflow": False,
                "workflow_preapproval_note": "Set true only when the initial reviewed computation plan already covers this stage's exact inputs/resources.",
                # Derived input: take the converged geometry from relax. Declared
                # here so it is part of the approved envelope (Safety Model).
                "inputs_from": [{"stage": "relax", "file": "CONTCAR", "to": "POSCAR"}],
                "completion_files": ["OUTCAR", "CHGCAR"],
                "incar_defaults": {
                    "EDIFF": DEFAULT_SCF_EDIFF,
                    "IBRION": -1,
                    "NSW": 0,
                    "ISIF": 2,
                    "ISMEAR": 0,
                    "SIGMA": "0.05",
                    "PREC": "Accurate",
                    "LREAL": ".FALSE.",
                    "LWAVE": ".TRUE.",
                    "LCHARG": ".TRUE.",
                },
                "scf_ediff_policy": "fixed at 1E-7 by default; changes require review envelope approval",
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


def stage_current_input_hashes(stage_root: Path) -> dict[str, str] | None:
    if (stage_root / STATE_NAME).exists():
        return current_input_hashes(stage_root)
    if (stage_root / "task_spec.json").exists():
        return standard_hashes(stage_root)
    return None


def stage_current_resource_hash(stage_root: Path) -> str | None:
    if (stage_root / STATE_NAME).exists():
        state = load_json(stage_root / STATE_NAME)
        if "resources" in state and "workers" in state:
            return resource_hash(state["resources"], int(state["workers"]))
        return state.get("resource_hash")
    if (stage_root / "task_spec.json").exists():
        task_spec = load_json(stage_root / "task_spec.json")
        resources = task_spec.get("resources")
        if isinstance(resources, dict):
            return resource_hash(resources, 1)
        return task_spec.get("resource_hash")
    return None


def stage_recorded_input_hashes(stage_root: Path) -> dict[str, str] | None:
    if (stage_root / STATE_NAME).exists():
        state = load_json(stage_root / STATE_NAME)
        hashes = state.get("input_hashes")
        return hashes if isinstance(hashes, dict) else None
    if (stage_root / "task_spec.json").exists():
        task_spec = load_json(stage_root / "task_spec.json")
        hashes = task_spec.get("input_hashes")
        return hashes if isinstance(hashes, dict) else None
    return None


def stage_recorded_resource_hash(stage_root: Path) -> str | None:
    if (stage_root / STATE_NAME).exists():
        state = load_json(stage_root / STATE_NAME)
        value = state.get("resource_hash")
        return str(value) if value else None
    if (stage_root / "task_spec.json").exists():
        task_spec = load_json(stage_root / "task_spec.json")
        value = task_spec.get("resource_hash")
        return str(value) if value else None
    return None


def stage_has_workflow_preapproval(case_root: Path, stage: dict[str, Any], review_text: str) -> bool:
    if not stage.get("preapproved_by_workflow", False):
        return False
    stage_root = case_root / str(stage.get("path", "."))
    current_input_hashes = stage_current_input_hashes(stage_root)
    current_resource_hash = stage_current_resource_hash(stage_root)
    if current_input_hashes is None or current_resource_hash is None:
        return False
    if stage_recorded_input_hashes(stage_root) != current_input_hashes:
        return False
    if stage_recorded_resource_hash(stage_root) != current_resource_hash:
        return False

    expected_review_hash = stage.get("workflow_preapproved_review_hash")
    if expected_review_hash and expected_review_hash != sha256_text(review_text):
        return False

    expected_input_hashes = stage.get("workflow_preapproved_input_hashes")
    if expected_input_hashes is not None and expected_input_hashes != current_input_hashes:
        return False

    expected_resource_hash = stage.get("workflow_preapproved_resource_hash")
    if expected_resource_hash is not None and expected_resource_hash != current_resource_hash:
        return False

    return True


def stage_has_approval(case_root: Path, stage: dict[str, Any]) -> bool:
    if not stage.get("review_file"):
        return False
    review = resolve_stage_path(case_root, stage, "review_file")
    if not review.exists():
        return False
    review_text = review.read_text(encoding="utf-8", errors="replace")

    if stage_has_workflow_preapproval(case_root, stage, review_text):
        return True

    approval_file = stage.get("approval_file")
    if not approval_file:
        return False
    approval = resolve_stage_path(case_root, stage, "approval_file")
    if not approval.exists():
        return False
    try:
        payload = load_json(approval)
    except Exception:
        return False
    if not payload.get("approved", False):
        return False
    if payload.get("review_hash"):
        if payload.get("review_hash") != sha256_text(review_text):
            return False
    else:
        return False
    stage_root = case_root / str(stage.get("path", "."))
    if payload.get("input_hashes") != stage_current_input_hashes(stage_root):
        return False
    if payload.get("resource_hash") != stage_current_resource_hash(stage_root):
        return False
    return True


def stage_has_scientific_design(case_root: Path, stage: dict[str, Any]) -> bool:
    stage_root = case_root / str(stage.get("path", "."))
    metadata_path = stage_root / (STATE_NAME if (stage_root / STATE_NAME).exists() else "task_spec.json")
    if not metadata_path.is_file():
        return False
    try:
        metadata = load_json(metadata_path)
    except Exception:
        return False
    provenance = metadata.get("design_provenance")
    return bool(isinstance(provenance, dict) and provenance.get("scientific_design_approved"))


def stage_complete(case_root: Path, stage: dict[str, Any]) -> bool:
    stage_root = case_root / str(stage.get("path", "."))
    if stage.get("kind") == "phonon-fd-worker-queue":
        counts = fd_queue_counts(stage_root)
        return counts["total"] > 0 and counts["done"] == counts["total"]
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
    if stage.get("kind") == "phonon-fd-worker-queue":
        counts = fd_queue_counts(stage_root)
        if stage.get("fail_fast"):
            return counts["failed"] > 0
        return counts["failed"] > 0 and counts["undo"] == 0 and counts["calculating"] == 0
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


def fd_queue_counts(taskset: Path) -> dict[str, int]:
    counts = {"total": 0, "undo": 0, "calculating": 0, "done": 0, "failed": 0}
    state_path = taskset / STATE_NAME
    if state_path.exists():
        try:
            state = load_json(state_path)
            for job in state.get("jobs", {}).values():
                status = str(job.get("status", "undo"))
                if status in counts:
                    counts[status] += 1
                counts["total"] += 1
            return counts
        except Exception:
            pass
    for name in QUEUE_STATES:
        directory = taskset / "queue" / name
        if directory.exists():
            counts[name] = len([p for p in directory.iterdir() if not p.name.startswith(".")])
    counts["total"] = sum(counts[name] for name in QUEUE_STATES)
    return counts


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
                except OSError as exc:
                    missing.append(f"{dst} (symlink failed: {exc})")
                    continue
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

    def block(stage: dict[str, Any], reason: str) -> None:
        stage["status"] = "blocked"
        stage["blocked_reason"] = reason
        print(f"[blocked] {stage['name']}: {reason}")
        log(f"{stage['name']} -> blocked: {reason}")

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
                    block(stage, "job left Slurm queue but completion criteria are not satisfied")
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
                block(stage, "required staged input missing: " + ", ".join(staging["missing"]))
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
            block(stage, "missing review, matching stage approval, or workflow preapproval")
            changed = True
            continue
        if not stage_has_scientific_design(case_root, stage):
            block(stage, "automatic production submission requires an approved computation-design scope")
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
            block(stage, f"submit command exited {result.returncode}")
        else:
            match = JOB_ID_RE.search(result.stdout + "\n" + result.stderr)
            stage["job_id"] = match.group(1) if match else None
            stage["status"] = "submitted"
            stage["submitted_at"] = now_iso()
            log(f"{stage['name']} -> submitted job_id={stage.get('job_id')}")
        changed = True

    for stage in stages:
        if stage.get("status") in {"blocked", "failed"}:
            reason = str(stage.get("blocked_reason") or stage.get("fail_reason") or stage.get("status"))
            key = sha256_text(f"{stage.get('name')}|{stage.get('status')}|{reason}")
            if stage.get("last_escalation_key") != key:
                if not args.dry_run:
                    record_human_review(case_root, plan, stage, reason)
                    stage["last_escalation_key"] = key
                changed = True

    if changed and not args.dry_run:
        plan["updated_at"] = now_iso()
        atomic_write_json(plan_path, plan)
    for stage in stages:
        print(f"{stage['name']}: {stage.get('status', 'planned')} job_id={stage.get('job_id')}")
    return 0


def record_human_review(case_root: Path, plan: dict[str, Any], stage: dict[str, Any], reason: str) -> None:
    directory = automation_dir(case_root)
    directory.mkdir(parents=True, exist_ok=True)
    item = {
        "created_at": now_iso(),
        "stage": stage.get("name"),
        "status": stage.get("status"),
        "reason": reason,
        "path": str(case_root / str(stage.get("path", "."))),
        "job_id": stage.get("job_id"),
        "recommendation": stage.get("recommendation") or stage.get("blocked_recommendation"),
    }
    with (directory / "review_queue.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")
    with (directory / "review_queue.dat").open("a", encoding="utf-8") as f:
        f.write(
            f"{item['created_at']} stage={item['stage']} status={item['status']} "
            f"reason={item['reason']} path={item['path']} job_id={item.get('job_id')}\n"
        )
    notify = str(plan.get("notify_command", "")).strip()
    if notify:
        env = os.environ.copy()
        env.update({
            "VWF_CASE_ROOT": str(case_root),
            "VWF_STAGE": str(item["stage"]),
            "VWF_STATUS": str(item["status"]),
            "VWF_REASON": reason,
            "VWF_STAGE_PATH": str(item["path"]),
        })
        result = subprocess.run(notify, cwd=case_root, shell=True, text=True, capture_output=True, env=env)
        with (directory / "notify.out").open("a", encoding="utf-8") as f:
            f.write(result.stdout)
        with (directory / "notify.err").open("a", encoding="utf-8") as f:
            f.write(result.stderr)


def automation_review(args: argparse.Namespace) -> int:
    case_root = args.case_root.resolve()
    path = automation_dir(case_root) / "review_queue.jsonl"
    if not path.exists():
        print("[ok] no review queue")
        return 0
    lines = path.read_text(encoding="utf-8").splitlines()
    for line in lines:
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            print(line)
            continue
        print(f"{item.get('created_at')} {item.get('stage')} {item.get('status')}: {item.get('reason')}")
        print(f"  path: {item.get('path')}")
    if args.clear:
        archive = automation_dir(case_root) / f"review_queue.{int(time.time())}.jsonl"
        path.rename(archive)
        dat = automation_dir(case_root) / "review_queue.dat"
        if dat.exists():
            dat.rename(automation_dir(case_root) / f"review_queue.{int(time.time())}.dat")
        print(f"[ok] archived review queue -> {archive}")
    return 0


def automation_watch(args: argparse.Namespace) -> int:
    case_root = args.case_root.resolve()
    cycles = 0
    while True:
        tick_args = argparse.Namespace(case_root=case_root, dry_run=args.dry_run)
        automation_tick(tick_args)
        plan = load_json(automation_plan_path(case_root))
        statuses = [stage.get("status", "planned") for stage in plan.get("stages", [])]
        if statuses and all(status == "done" for status in statuses):
            print("[done] all stages completed")
            return 0
        if args.stop_on_blocked and any(status in {"blocked", "failed"} for status in statuses):
            print("[blocked] watch stopped for human review")
            return 2
        if args.max_resubmit is not None:
            retries = sum(int(stage.get("retry_count", 0)) for stage in plan.get("stages", []))
            if retries >= args.max_resubmit:
                print(f"[blocked] max resubmit/recovery attempts reached: {retries}/{args.max_resubmit}")
                return 2
        cycles += 1
        if args.max_cycles and cycles >= args.max_cycles:
            print(f"[stop] max cycles reached: {cycles}")
            return 1
        time.sleep(args.interval_seconds)


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
    case_root, case_meta = resolve_case_root(args)
    source = find_source_dir(case_root, args.source_dir)
    taskset = case_taskset_path(case_root, args.taskset)
    design_provenance = resolve_design_provenance(args, "phonon-fd", case_meta)
    design_provenance = snapshot_design_review(case_root, design_provenance)

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
        **case_meta,
        "taskset": str(taskset),
        "source_dir": str(source),
        "input_sources": {
            "POSCAR": str((source / "POSCAR").resolve()),
            "KPOINTS": str((source / "KPOINTS").resolve()),
            "POTCAR": str((source / "POTCAR").resolve()),
            "POTCAR_functional": args.potcar_functional,
            "INCAR.fd": incar_source,
        },
        "input_hashes": hashes,
        "dim": list(dim),
        "displacement_distance": args.displacement_distance,
        "workers": args.workers,
        "resources": resources,
        "resource_hash": resource_hash(resources, args.workers),
        "design_provenance": design_provenance,
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "jobs": jobs,
        "workers_state": {f"worker-{idx:03d}": {"status": "prepared", "job_id": None} for idx in range(1, args.workers + 1)},
    }
    save_state(taskset, state)
    task_spec = {
        "schema_version": 1,
        "task_kind": "phonon-fd",
        **case_meta,
        "taskset": str(taskset),
        "source_dir": str(source),
        "input_hashes": hashes,
        "workers": args.workers,
        "resources": resources,
        "design_provenance": design_provenance,
        "created_at": now_iso(),
    }
    atomic_write_json(taskset / "task_spec.json", task_spec)
    record_design_in_workflow(case_root, design_provenance)
    log_queue(taskset, f"prepared {len(jobs)} displacement jobs with {args.workers} workers")
    print(f"[ok] prepared {len(jobs)} displacement jobs -> {taskset}")
    print(f"[next] run: python -m vwf review submit --taskset {taskset}")
    return 0


def build_submission_review(taskset: Path, state: dict[str, Any]) -> str:
    input_dir = taskset / "input"
    hashes = current_input_hashes(taskset)
    resources = state["resources"]
    design = state.get("design_provenance", {})
    incar_path = input_dir / "INCAR.fd"
    lines = [
        "# vasp_workflow_submission_review = 1",
        f"generated_at = {now_iso()}",
        f"taskset = {taskset}",
        f"kind = {state.get('kind')}",
        f"project_slug = {state.get('project_slug') or 'unknown'}",
        f"system_slug = {state.get('system_slug') or 'unknown'}",
        f"case_slug = {state.get('case_slug') or 'unknown'}",
        f"cluster = {state.get('cluster') or 'unknown'}",
        f"case_root_source = {state.get('case_root_source') or 'unknown'}",
        "",
        "[scientific_design]",
        f"status = {design.get('status', 'exploratory_untracked')}",
        f"approved = {str(bool(design.get('scientific_design_approved'))).lower()}",
        f"design_id = {design.get('design_id', '')}",
        f"design_revision = {design.get('design_revision', '')}",
        f"matrix_id = {design.get('matrix_id', '')}",
        f"design_sha256 = {design.get('design_sha256', '')}",
        f"approval_sha256 = {design.get('approval_sha256', '')}",
        f"case_snapshot = {design.get('case_snapshot', '')}",
        "scientific_design_approval_does_not_authorize_sbatch = true",
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
        f"POTCAR.functional = {state['input_sources'].get('POTCAR_functional', DEFAULT_POTCAR_FUNCTIONAL)}",
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
        f"account = {resources.get('account')}",
        f"nodelist = {resources.get('nodelist')}",
        f"gres = {resources.get('gres')}",
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


def build_standard_submission_review(task_dir: Path, task_spec: dict[str, Any]) -> str:
    hashes = standard_hashes(task_dir)
    resources = task_spec.get("resources", {})
    design = task_spec.get("design_provenance", {})
    lines = [
        "# vasp_workflow_submission_review = 1",
        f"generated_at = {now_iso()}",
        f"task_dir = {task_dir}",
        f"kind = {task_spec.get('task_kind')}",
        f"workflow_stage = {task_spec.get('stage')}",
        f"dependency = {task_spec.get('dependency', 'none or explicit user source')}",
        f"project_slug = {task_spec.get('project_slug') or 'unknown'}",
        f"system_slug = {task_spec.get('system_slug') or 'unknown'}",
        f"case_slug = {task_spec.get('case_slug') or 'unknown'}",
        f"cluster = {task_spec.get('cluster') or 'unknown'}",
        f"case_root_source = {task_spec.get('case_root_source') or 'unknown'}",
        "",
        "[scientific_design]",
        f"status = {design.get('status', 'exploratory_untracked')}",
        f"approved = {str(bool(design.get('scientific_design_approved'))).lower()}",
        f"design_id = {design.get('design_id', '')}",
        f"design_revision = {design.get('design_revision', '')}",
        f"matrix_id = {design.get('matrix_id', '')}",
        f"task_class = {design.get('task_class', '')}",
        f"design_sha256 = {design.get('design_sha256', '')}",
        f"approval_sha256 = {design.get('approval_sha256', '')}",
        f"case_snapshot = {design.get('case_snapshot', '')}",
        "scientific_design_approval_does_not_authorize_sbatch = true",
        "",
        "[inputs]",
        f"POSCAR.source = {task_spec.get('input_sources', {}).get('POSCAR', 'unknown')}",
        f"POSCAR.source_note = {task_spec.get('input_sources', {}).get('POSCAR_source_note', 'unknown')}",
        f"POSCAR.sha256 = {hashes.get('POSCAR', 'missing')}",
        f"POSCAR.summary = {read_poscar_summary(task_dir / 'POSCAR')}",
        *read_poscar_details(task_dir / "POSCAR"),
        f"POSCAR-ini.source = {task_spec.get('input_sources', {}).get('POSCAR-ini', '')}",
        f"POSCAR-ini.sha256 = {hashes.get('POSCAR-ini', '')}",
        "POSCAR-ini.restart_rule = keep this initial geometry backup so a scattered relax can restart from the original approved structure",
        f"INCAR.source = {task_spec.get('input_sources', {}).get('INCAR', 'unknown')}",
        f"INCAR.sha256 = {hashes.get('INCAR', 'missing')}",
        f"INCAR.summary = {read_incar_summary(task_dir / 'INCAR')}",
    ]
    incar_defaults = task_spec.get("incar_defaults")
    if isinstance(incar_defaults, dict) and incar_defaults.get("built_in_defaults"):
        defaults = incar_defaults.get("built_in_defaults", {})
        defaulted = " ".join(str(x) for x in incar_defaults.get("defaulted", [])) or "none"
        overridden = incar_defaults.get("overridden", [])
        overridden_text = (
            " ".join(f"{item.get('key')}:{item.get('default')}->{item.get('effective')}" for item in overridden)
            if overridden
            else "none"
        )
        lines.extend([
            f"INCAR.default_source = {incar_defaults.get('source', 'unknown')}",
            "INCAR.built_in_defaults = " + " ".join(f"{key}={value}" for key, value in defaults.items()),
            f"INCAR.defaulted_keys = {defaulted}",
            f"INCAR.overridden_keys = {overridden_text}",
        ])
        if incar_defaults.get("ediff_policy"):
            lines.append(f"INCAR.ediff_policy = {incar_defaults['ediff_policy']}")
        if incar_defaults.get("relax_ediffg_policy"):
            lines.append(f"INCAR.relax_ediffg_policy = {incar_defaults['relax_ediffg_policy']}")
        if incar_defaults.get("magmom_review"):
            lines.append(f"INCAR.magmom_review = {incar_defaults['magmom_review']}")
    lines.extend([
        "INCAR.change_review = confirm complete effective INCAR and any inherited/appended/overridden parameters",
        "INCAR.complete_begin",
        read_text_block(task_dir / "INCAR"),
        "INCAR.complete_end",
        f"KPOINTS.source = {task_spec.get('input_sources', {}).get('KPOINTS', 'unknown')}",
        f"KPOINTS.sha256 = {hashes.get('KPOINTS', 'missing')}",
        f"KPOINTS.summary = {read_kpoints_summary(task_dir / 'KPOINTS')}",
    ])
    kpoints = task_spec.get("kpoints", {})
    if isinstance(kpoints, dict):
        if kpoints.get("generator"):
            lines.append(f"KPOINTS.generator = {kpoints['generator']}")
        if kpoints.get("mesh"):
            lines.append("KPOINTS.mesh = " + " ".join(str(x) for x in kpoints["mesh"]))
        if kpoints.get("band_path"):
            lines.append(f"KPOINTS.band_path = {kpoints['band_path']}")
    lines.extend([
        "KPOINTS.generator_env_review = if VASPKIT/pymatgen/SeeK-path is expected but missing, stop and activate/install the environment",
        f"POTCAR.source = {task_spec.get('input_sources', {}).get('POTCAR', 'unknown')}",
        f"POTCAR.root = {task_spec.get('input_sources', {}).get('POTCAR_root', '')}",
        f"POTCAR.resolution = {task_spec.get('input_sources', {}).get('POTCAR_resolution', 'explicit')}",
        f"POTCAR.functional = {task_spec.get('input_sources', {}).get('POTCAR_functional', DEFAULT_POTCAR_FUNCTIONAL)}",
        f"POTCAR.sha256 = {hashes.get('POTCAR', 'missing')}",
        f"POTCAR.summary = {read_potcar_summary(task_dir / 'POTCAR')}",
        "POTCAR.user_choice_required = true",
        "POTCAR.choice_review = user must confirm functional, element order, and potential labels before generation/submission",
        "POTCAR.public_repo_rule = do not commit or publish POTCAR contents",
        f"job.sh.source = {task_spec.get('input_sources', {}).get('job.sh', 'unknown')}",
        f"job.sh.sha256 = {hashes.get('job.sh', 'missing')}",
        "",
    ])
    stage_from_records = task_spec.get("stage_from", [])
    if stage_from_records:
        lines.append("[stage_from]")
        for index, record in enumerate(stage_from_records, start=1):
            lines.append(
                f"stage_from.{index} = {record.get('source')} -> "
                f"{record.get('destination')} ({record.get('mode')}; {record.get('origin', 'unknown')})"
            )
        lines.append("")
    components = task_spec.get("POTCAR_components", [])
    if components:
        lines.append("[potcar_components]")
        for item in components:
            lines.append(
                "POTCAR.component = "
                f"element:{item.get('element')} label:{item.get('label')} "
                f"path:{item.get('path')} sha256:{item.get('sha256')} title:{item.get('title')}"
            )
        lines.append("")
    lines.extend([
        "[resources]",
        f"profile = {resources.get('profile')}",
        f"partition = {resources.get('partition')}",
        f"qos = {resources.get('qos')}",
        f"account = {resources.get('account')}",
        f"nodelist = {resources.get('nodelist')}",
        f"gres = {resources.get('gres')}",
        f"nodes = {resources.get('nodes')}",
        f"ntasks = {resources.get('ntasks')}",
        f"ntasks_per_node = {resources.get('ntasks_per_node')}",
        f"cpus_per_task = {resources.get('cpus_per_task')}",
        f"walltime = {resources.get('time')}",
        f"vasp_cmd = {resources.get('vasp_cmd')}",
        "",
        "[approval]",
        "User must confirm the inputs and resources above before sbatch.",
    ])
    return "\n".join(lines) + "\n"


def review_submit(args: argparse.Namespace) -> int:
    taskset = args.taskset.resolve()
    if (taskset / STATE_NAME).exists():
        state = load_state(taskset)
        review_text = build_submission_review(taskset, state)
        review_path = taskset / "input" / REVIEW_NAME
        hashes = current_input_hashes(taskset)
        approval_path = taskset / "input" / APPROVAL_NAME
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
    elif (taskset / "task_spec.json").exists():
        task_spec = load_json(taskset / "task_spec.json")
        review_text = build_standard_submission_review(taskset, task_spec)
        review_path = taskset / REVIEW_NAME
        hashes = standard_hashes(taskset)
        approval_path = taskset / APPROVAL_NAME
        approval = {
            "schema_version": 1,
            "approved": bool(args.approve),
            "approved_at": now_iso() if args.approve else None,
            "review_path": str(review_path),
            "review_hash": sha256_text(review_text),
            "input_hashes": hashes,
            "resource_hash": task_spec.get("resource_hash"),
        }
    else:
        raise FileNotFoundError(f"cannot find {STATE_NAME} or task_spec.json in {taskset}")
    atomic_write_text(review_path, review_text)
    atomic_write_json(approval_path, approval)
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


def add_resource_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--profile", choices=sorted(PROFILE_DEFAULTS), default="generic")
    parser.add_argument("--partition", default=None)
    parser.add_argument("--qos", default=None)
    parser.add_argument("--account", default=None)
    parser.add_argument("--nodelist", default=None)
    parser.add_argument("--gres", default=None)
    parser.add_argument("--nodes", type=int, default=None)
    parser.add_argument("--ntasks", type=int, default=None)
    parser.add_argument("--ntasks-per-node", type=int, default=None, dest="ntasks_per_node")
    parser.add_argument("--cpus-per-task", type=int, default=None, dest="cpus_per_task")
    parser.add_argument("--time", default=None)
    parser.add_argument("--vasp-cmd", default=None)


def add_design_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--design-approval",
        type=Path,
        default=None,
        help="Hash-locked computation-design approval.json for a production task.",
    )
    parser.add_argument(
        "--design-task",
        default=None,
        help="Calculation-matrix ID in the approved scientific design scope.",
    )


def add_standard_prepare_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser], kind: str) -> None:
    parser = subparsers.add_parser(kind)
    add_case_args(parser)
    parser.add_argument("--source-poscar", type=Path, default=None)
    parser.add_argument("--source-dir", type=Path, default=None)
    parser.add_argument("--potcar", type=Path, default=None, help="Explicit POTCAR source chosen by the user.")
    parser.add_argument("--potcar-root", type=Path, default=None, help="Root directory used to auto-resolve element POTCAR files.")
    parser.add_argument("--potcar-label", action="append", default=[], help="Override one element label, e.g. Si=Si_GW or O=O_s.")
    parser.add_argument("--potcar-functional", default=DEFAULT_POTCAR_FUNCTIONAL)
    parser.add_argument("--incar-preset", choices=INCAR_PRESETS, default="standard")
    parser.add_argument("--incar-template", type=Path, default=None)
    parser.add_argument("--kpoints-source", type=Path, default=None)
    parser.add_argument("--kmesh", default="1 1 1")
    parser.add_argument("--encut", type=int, default=None)
    parser.add_argument("--ediff", default=None)
    parser.add_argument("--ediffg", default=DEFAULT_RELAX_EDIFFG)
    parser.add_argument("--ibrion", type=int, default=2)
    parser.add_argument("--isif", type=int, default=None)
    parser.add_argument("--nsw", type=int, default=None)
    parser.add_argument("--ismear", type=int, default=0)
    parser.add_argument("--sigma", default="0.05")
    parser.add_argument("--lorbit", type=int, default=11)
    parser.add_argument("--nedos", type=int, default=2001)
    parser.add_argument("--line-points", type=int, default=20)
    parser.add_argument("--ncore", type=int, default=None)
    parser.add_argument("--magmom", default=None, help="MAGMOM line used by magnetic INCAR presets.")
    parser.add_argument("--stage-from", type=parse_stage_from, action="append", default=[])
    parser.add_argument("--overwrite", action="store_true")
    add_design_args(parser)
    add_resource_args(parser)
    parser.set_defaults(func=prepare_standard, task_kind=kind)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="vwf", description="VASP workflow helper for skill-managed tasks.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init-case")
    add_case_args(p_init)
    p_init.set_defaults(func=init_case)

    p_prepare = sub.add_parser("prepare")
    prep_sub = p_prepare.add_subparsers(dest="prepare_cmd", required=True)
    for kind in ("relax", "scf", "band", "dos"):
        add_standard_prepare_parser(prep_sub, kind)
    p_fd = prep_sub.add_parser("phonon-fd")
    add_case_args(p_fd)
    p_fd.add_argument("--taskset", required=True)
    p_fd.add_argument("--source-dir", type=Path, default=None)
    p_fd.add_argument("--potcar-functional", default=DEFAULT_POTCAR_FUNCTIONAL)
    p_fd.add_argument("--dim", default="1 1 1")
    p_fd.add_argument("--displacement-distance", type=float, default=0.01)
    p_fd.add_argument("--workers", type=int, default=5)
    add_resource_args(p_fd)
    p_fd.add_argument("--phonopy-bin", default="phonopy")
    p_fd.add_argument("--incar-template", type=Path, default=None)
    p_fd.add_argument("--copy-source-incar", action="store_true")
    p_fd.add_argument("--mock-displacements", type=int, default=0)
    p_fd.add_argument("--overwrite", action="store_true")
    add_design_args(p_fd)
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
    p_auto_watch = auto_sub.add_parser("watch")
    p_auto_watch.add_argument("--case-root", type=Path, required=True)
    p_auto_watch.add_argument("--interval-seconds", type=float, default=60.0)
    p_auto_watch.add_argument("--max-cycles", type=int, default=0)
    p_auto_watch.add_argument("--max-resubmit", type=int, default=None)
    p_auto_watch.add_argument("--stop-on-blocked", action="store_true", default=True)
    p_auto_watch.add_argument("--dry-run", action="store_true")
    p_auto_watch.set_defaults(func=automation_watch)
    p_auto_review = auto_sub.add_parser("review")
    p_auto_review.add_argument("--case-root", type=Path, required=True)
    p_auto_review.add_argument("--clear", action="store_true")
    p_auto_review.set_defaults(func=automation_review)
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
