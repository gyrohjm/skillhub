# G3 / H100 Cautions

Treat Phoenix G3/H100 as a special high-risk path.

## Default Assumption

Old G3 results and old H100 module conclusions are stale unless the current
system, driver, CUDA stack, MPI stack, and VASP build have been revalidated.

## Required Validation

Before production VASP on G3/H100:

1. Run live Slurm and module checks.
2. Confirm the node is not in a bad state.
3. Confirm the exact VASP executable and module stack.
4. Submit a tiny smoke test through Slurm.
5. Inspect VASP startup output for GPU detection and early cuSOLVER/OpenACC
   errors.
6. Archive the smoke test logs and module list.

Useful checks:

```bash
sinfo -N -n g3 -o "%N|%P|%t|%c|%m|%G|%f"
scontrol show node g3
squeue -w g3 -o "%i|%P|%j|%u|%T|%M|%D|%R"
module avail vasp
nvidia-smi
```

## Red Lines

- Do not assume an A100 workflow works on H100.
- Do not treat a successful import/module load as proof that VASP can complete
  electronic steps.
- Do not run production work until a post-reinstall smoke test passes for the
  exact build and launch command.
- Do not change KPOINTS or INCAR physics to make the smoke test look faster.
