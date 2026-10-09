import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


@pytest.fixture(autouse=True)
def isolated_local_profiles(tmp_path, monkeypatch):
    # Fictional environments exercise profile loading without reading the user's data.
    from dft_contracts.local_config import preserve_private_files
    private = tmp_path / "private_config"
    monkeypatch.setenv("DFT_SKILLS_CONFIG_DIR", str(private))
    base = {"project_root": str(tmp_path), "potcar_root": "/opt/example/potentials"}
    profiles = {}
    for name in ("nmg", "phoenix", "phoenix-gpu-a100", "phoenix-gpu-g3"):
        profiles[name] = dict(base, resources={"time": "", "partition": "example_cpu", "ntasks_per_node": 8, "vasp_cmd": "module load example_cpu; srun vasp_std"})
    for name, gpu in (("phoenix-gpu-a100", "a100"), ("phoenix-gpu-g3", "h100")):
        profiles[name]["resources"] = {"time": "", "partition": "example_gpu", "account": "example_account", "nodelist": "example_node", "gres": f"gpu:{gpu}:1", "ntasks_per_node": 1, "cpus_per_task": 4, "vasp_cmd": "module load example_gpu; nvidia-smi; mpirun -np $SLURM_NTASKS vasp_std"}
    preserve_private_files({"profiles.json": json.dumps({"profiles": profiles}).encode()})
