# Plot Data Contract

Write plot-ready numeric data as `.dat` files. Use whitespace-separated columns
and comment metadata. JSON is for manifests and configuration only.

For registered routes write task-local analysis/data/ (legacy
`<structure_root>/analysis/plot_data/` remains readable), where the
structure root is resolved by the shared DFT workspace layout contract. Do not
create a separate `raw_data/` tree, a task-local analysis tree, or copies of
unchanged DFT engine source outputs; reference the original source files in
headers.

Required header:

```text
# dftplot_dat_version = 1
# engine = vasp
# source = task_root:mgb.dos
# units = energy:eV dos:states/eV
# columns = energy_eV total_dos C_pdos Si_pdos
```

Rules:

- Record the engine identifier and parser/tool provenance. Use `engine = derived`
  only for a quantity computed from multiple fully cited sources.
- Every non-comment row must be numeric.
- Every row must have exactly the same number of fields as `# columns`.
- Use stable, machine-friendly column names: letters, digits, underscore.
- Use one unit token per physical quantity family when possible.
- Keep energies in eV unless the source method requires another unit and the
  header says so.
- For spin data, use explicit columns such as `dos_up`, `dos_down`, or
  `spin_z`.
- For slices or maps, prefer columns such as `x_frac y_frac value` or
  `z_ang value`; avoid embedding arrays in JSON.

Recommended output names:

```text
dos_total.dat
dos_element_pdos.dat
band.dat
fatband_weights.dat
phonon_band.dat
phonon_dos.dat
phonon_unfolded_spectral_weight.dat
chgdiff_z.dat
chgdiff_slice.dat
elf_slice.dat
spin_density_z.dat
spin_density_slice.dat
parchg_slice.dat
pcohp_selected_bonds.dat
```

Template column conventions:

```text
dos_total.dat:
  energy_eV total_dos C_pdos Si_pdos

spin_dos.dat:
  energy_eV dos_up dos_down

band.dat:
  k_distance band_1 band_2 band_3

phonon_band.dat:
  q_distance branch_1 branch_2 branch_3

phonon_dos.dat:
  frequency_THz dos

chgdiff_z.dat:
  z_ang chgdiff

formation_energy.dat:
  index formation_energy_eV

surface_energy.dat:
  index surface_energy_eV_per_A2

adsorption_energy.dat:
  index adsorption_energy_eV

interface_adhesion.dat:
  index interface_adhesion_eV_per_A2

work_function.dat:
  index work_function_eV

bader_charge.dat:
  atom_index charge_e

charge_density_difference.dat:
  z_ang charge_density_difference

elf_slice.dat, spin_density_slice.dat, parchg_slice.dat:
  x_frac y_frac value

pcohp_selected_bonds.dat:
  energy_eV bond_1 bond_2 bond_3
```

Run `scripts/dftplot_dat.py validate <file.dat>` before marking the result
accepted in the source task README/`workflow.json`. Hand the lifecycle event to
`dft-work-manager` for the required concise human log; manager does not extract
or reinterpret the numeric data. Transfer/archive remains a separate explicit
operation.
Legacy `# vaplot_dat_version = 1` files remain valid without an engine header;
add engine provenance when they are revised.
