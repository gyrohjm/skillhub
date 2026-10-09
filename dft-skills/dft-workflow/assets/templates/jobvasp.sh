#!/bin/bash
#SBATCH -J {{JOB_NAME}}
#SBATCH -N {{NODES}}
#SBATCH -n {{NTASKS}}
#SBATCH --ntasks-per-node={{NTASKS_PER_NODE}}
#SBATCH --cpus-per-task={{CPUS_PER_TASK}}
{{SBATCH_PARTITION}}{{SBATCH_QOS}}{{SBATCH_ACCOUNT}}{{SBATCH_NODELIST}}{{SBATCH_GRES}}
#SBATCH -o slurm-%j.out
#SBATCH -e slurm-%j.err

{{VASP_CMD}} > vasp.out 2> vasp.err
