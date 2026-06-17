# Calculation Taxonomy

Use these top-level categories consistently:

- `test/`: convergence and sensitivity tests for ENCUT, KPOINTS, SIGMA,
  smearing, POTCAR variants, precision flags, and similar parameters.
- `relax/`: geometry optimization, constrained relax, staged relax.
- `energy/`: static total energy, adsorption/formation energy, EOS, site scans.
- `electronic/`: SCF, band, DOS/PDOS, fatband, pCOHP/COBI/COOP, ELF, CHGDIFF,
  spin density, PARCHG, LOCPOT/work function, Bader, optics, Wannier,
  electronic unfolding.
- `phonon/`: finite displacement, DFPT, Gamma phonon, phonon DOS/band, thermal
  properties, phonon unfolding.

Default dependency order:

```text
structure -> test
test -> relax
relax/CONTCAR -> electronic/scf
electronic/scf -> electronic/band|dos|fatband|pcohp|elf|chgdiff|spin-density|parchg|locpot|bader|optics|wannier
relax/CONTCAR -> phonon/fd|dfpt|gamma|unfolded|thermal
analysis reads workflow outputs or manager archives
```

`test/` is for selecting production parameters, not for producing final
reported results. Test one scientific parameter family at a time when possible,
for example ENCUT convergence, KPOINTS convergence, SIGMA/smearing sensitivity,
or POTCAR comparison. Record the tested values, fixed background settings,
criterion, selected value, and user approval in `task_spec.json` or a local
notes file before moving to `relax/`.

`relax/` is the structural gate for later calculations. A downstream production
task must state which relaxed `CONTCAR` it uses. If a user asks to skip relax or
use the original `POSCAR`, write that exception into the submit review.

`electronic/scf/` is the canonical static calculation after relax. It should
produce the final total energy and reusable `WAVECAR`/`CHGCAR` when those files
are needed by band, DOS, pCOHP, ELF, charge-density, spin-density, PARCHG,
LOCPOT, Bader, optics, Wannier, or similar child tasks.

Phonon calculations must use the optimized relaxed structure. For finite
displacement, the phonopy supercells/displacements are generated from the
approved relaxed `CONTCAR`; for DFPT/Gamma phonon, the submitted `POSCAR` should
also come from the approved relaxed structure unless the user explicitly asks
for another reference.

Before preparing a child task, confirm whether it should use relaxed `CONTCAR`,
original `POSCAR`, SCF charge, or a phonopy-generated supercell. Record that
choice in `task_spec.json` and in the submit review.

Before preparing structures from scratch, confirm lattice constants, coordinate
mode, fixed-atom/selective-dynamics requirements, and atom ordering. Unless the
user specifies a symmetry/site-label reason to keep another order, generated
POSCAR files should generally be sorted by descending `z`, then ascending `x`,
then ascending `y`.

For band calculations, record the high-symmetry path directly in the task spec
and submit review. Paths may be generated with VASPKIT, pymatgen, SeeK-path, or
another explicit tool, but the review must say which tool produced the path and
must list the labels in order.
