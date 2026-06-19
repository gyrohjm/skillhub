# Plot Data Contract

Write plot-ready numeric data as `.dat` files. Use whitespace-separated columns
and comment metadata. JSON is for manifests and configuration only.

On clusters, write these files under
`<case_root>/analysis/plot_data/`. Do not create a separate `raw_data/` tree or
copy unchanged VASP source outputs into the analysis directory; reference the
original source paths in headers.

Required header:

```text
# vaplot_dat_version = 1
# source = /absolute/or/archive/source/path
# units = energy:eV dos:states/eV
# columns = energy_eV total_dos C_pdos Si_pdos
```

Rules:

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

elf_slice.dat, spin_density_slice.dat, parchg_slice.dat:
  x_frac y_frac value

pcohp_selected_bonds.dat:
  energy_eV bond_1 bond_2 bond_3
```

Run `scripts/vaplot_dat.py validate <file.dat>` before handing data to
`vasp-work-manager` for task registration, archive records, and verification.
