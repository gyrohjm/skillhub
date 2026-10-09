# Plot Data Retention

Figures are not enough. Always preserve the data used to draw band, DOS,
fat-band, phonon, pCOHP, ELF, CHGDIFF, spin-density, PARCHG, EOS, convergence,
and charge-density plots.

## Files To Preserve

Keep plot-ready data:

```text
*.dat
*.csv
```

Prefer `.dat` for primary numeric arrays. Use the source leaf `workflow.json`
for compact task/analysis references and add specialized JSON only when the
analysis contract genuinely requires it; never use JSON as the only copy of
numeric plotting data.

Keep final images:

```text
*.png
*.pdf
```

For `vaspmgr plot`, expected outputs include:

```text
band.dat
band.png
band.pdf
dos.dat
dos.png
dos.pdf
band_dos.png
band_dos.pdf
fatband.png
fatband.pdf
phonon_band.png
phonon_band.pdf
phonon_dos.png
phonon_dos.pdf
chgdiff_z.dat
elf_slice.dat
pcohp_selected_bonds.dat
formation_energy.dat
surface_energy.dat
adsorption_energy.dat
interface_adhesion.dat
work_function.dat
bader_charge.dat
charge_density_difference.dat
```

The exact prefix may differ, so collect by extension and manifest the paths.

## Inputs That Explain The Plot

When present, preserve the raw files that make the plotted data interpretable:

```text
EIGENVAL
DOSCAR
PROCAR
KLABELS
REFORMATTED_BAND.dat
KPOINTS
POSCAR
OUTCAR
band.yaml
total_dos.dat
projected_dos.dat
COHPCAR.lobster
ICOHPLIST.lobster
lobsterout
```

Do not assume a PNG can be regenerated without these files.

## Collection

Paired projects use cluster task data/, figures/ and scripts/. The owning numbered-stage
README is the stage report: embed figures and link raw source leaves, plotting data and
scripts using relative paths. Do not create reports per calculation variant. After
recorded convergence/acceptance, publish selected evidence and conclusions to the sole
local main report with provenance; source artifacts remain on the cluster.

Existing single-root registered routes keep intermediate plot-ready data, figures and dedicated scripts
under the producing task's analysis/{data,figures,scripts}/. Update analysis/README.md
with conclusions, limitations, source references and reading order. Cross-stage
comparisons may live in route analysis/ with exact source-task references.

The project results/ is a compact final publication area, not a mirror of every task.
It contains one main_report.md and selected final figures/tables. Use the project
publish command to record source task/UUID, revision, data/script hashes and source path.
Final copies are regenerated from task sources; keep stable filenames and Git history.

Legacy structure-level analysis/{plot_data,figures,reports}/ remains supported. A
legacy source path is preserved until explicitly migrated. Never copy raw engine
outputs merely for plotting. Transfer bundles are separate explicit exports with
checksums, scope and destination; they do not replace live analysis or the main report.
