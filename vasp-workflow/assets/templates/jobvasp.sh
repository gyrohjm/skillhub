#!/bin/bash
# VASP Slurm job template rendered by vwf.
# Edit this template when the standard submit script structure needs to change.
# Scientific inputs and resource values still must be reviewed before sbatch.
#SBATCH -J {{JOB_NAME}}
#SBATCH -N {{NODES}}
#SBATCH -n {{NTASKS}}
#SBATCH --ntasks-per-node={{NTASKS_PER_NODE}}
#SBATCH --cpus-per-task={{CPUS_PER_TASK}}
{{SBATCH_TIME}}#SBATCH -o slurm-%j.out
#SBATCH -e slurm-%j.err
{{SBATCH_PARTITION}}{{SBATCH_QOS}}{{SBATCH_ACCOUNT}}{{SBATCH_NODELIST}}{{SBATCH_GRES}}
set -euo pipefail
cd "${SLURM_SUBMIT_DIR:-$(dirname "$0")}"

{{VASP_CMD}} > vasp.out 2> vasp.err
