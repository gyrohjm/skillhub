# DFT Analysis Adapters

An adapter is trusted only when it records the engine/version, source files,
units, transformations, parser/tool version, and validation evidence.

## VASP

Bundled conventions cover VASP-native and common post-processing sources such
as `vasprun.xml`, `OUTCAR`, `DOSCAR`, `EIGENVAL`, `PROCAR`, `CHGCAR`,
`ELFCAR`, `PARCHG`, phonopy, LOBSTER, PyProcar, and VASPKIT outputs. Confirm the
exact parser/tool used; file recognition alone does not prove correctness.

## Quantum ESPRESSO, CP2K, ABINIT, and GPAW

The common `.dat`, figure, report, verdict, and optional export contracts are
operational. No bundled universal extractor is claimed. Use an engine-native or
community parser with explicit versioning (for example ASE or pymatgen support
where appropriate), then validate at least one scalar and one array against the
native output or an independent tool before scientific interpretation.

If validation cannot be demonstrated, label the data `provisional`, report the
gap, and do not issue a supported/falsified verdict.

## Cross-engine comparisons

Require aligned structures/reference states, XC functional, relativistic and
spin treatment, pseudopotential/electron definitions, basis and sampling
convergence, occupation/smearing treatment, units, normalization, and energy
zero. Cross-engine agreement is a validation study, not an automatic merge of
datasets.
