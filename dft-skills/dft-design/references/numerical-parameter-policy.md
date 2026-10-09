# Numerical Parameter Selection Policy

This reference turns an engine-aware scientific design into defensible
starting candidates for basis cutoffs, occupations/smearing, and reciprocal
space sampling. A candidate is an estimate, not a production value. A value
enters a production envelope only after the claim-supporting convergence gate
has been satisfied and the design has been approved.

## Decision order

For every matrix item, record the following before choosing numbers:

1. engine and exact stage (`relax`, `scf`, `dos`, `phonon`, `epc`, ...);
2. structure source, lattice vectors, periodic directions, and atom count;
3. pseudopotential/PAW family, version, labels, and the actual cutoff
   metadata from the selected files;
4. material class: metal, semiconductor, insulator, magnetic, or unknown;
5. claim-supporting observables and their uncertainty target;
6. candidate values, fixed conditions, acceptance rule, selected value, and
   evidence location.

Do not infer a production parameter from a template, a previous project, the
number of idle nodes, or the mere existence of a converged output. If the
material class or pseudopotential metadata is unknown, leave the value
`pending_decision` and block production approval.

## Basis cutoff

### VASP

Read `ENMAX` and `PENMAX` from every selected POTCAR component after the exact
functional, label, and file identity have been fixed.

Use the largest relevant `ENMAX` as the lower-bound candidate:

```text
ENCUT_lower = max(ENMAX of all elements)
```

For an initial convergence campaign, a project without prior evidence may use
multiple candidates around that lower bound, for example the lower bound and
one or two higher safety levels. A factor such as `1.15` or `1.30` is a
candidate-generation aid, not a universal default. These factors are not
universal. Stress, pressure,
phonon, finite-displacement, and EPC claims require an explicitly reviewed
higher-accuracy campaign; record how `PENMAX` informed that campaign when it
is relevant.

Never copy `ENCUT` from a different POTCAR family or composition. Keep the
POTCAR component hashes with the cutoff campaign. Converge the quantity that
the claim uses: energy differences for relative stability, forces/stress for
relaxation, force constants/frequencies for phonons, and the relevant
electron-phonon observable for EPC.

### Quantum ESPRESSO

Read the recommended cutoffs and the pseudopotential type from every selected
UPF file. Set `ecutwfc` from the most restrictive selected UPF recommendation
and choose `ecutrho` using the UPF/engine guidance for that pseudopotential
family. Common starting ratios are only estimates: norm-conserving sets often
start near `ecutrho/ecutwfc = 4`, while ultrasoft or PAW sets may need a much
higher ratio such as `8–12`; the actual UPF recommendation and convergence
campaign take precedence.

Do not translate VASP `ENMAX` into QE `ecutwfc` by tag-name analogy. Record
`ecutwfc`, `ecutrho`, units, UPF labels/hashes, candidate values, and the
target observable in the QE engine envelope. Converge both cutoffs with the
same structure, k mesh, occupations, and pseudopotential set held fixed.

## Occupations, smearing, and SIGMA/degauss

Choose occupations from the material class and the stage, then converge the
width. There is no universal smearing type or universal width.

| Situation | Starting decision | Required check |
|---|---|---|
| Metal relaxation or metallic SCF | Use an engine-supported metallic smearing that gives stable forces and charge mixing | Test width and k mesh together for the force/energy quantity used by the claim |
| Metallic final energy | Use a reviewed metallic integration scheme and a consistent `sigma -> 0` or equivalent energy protocol | Confirm energy ordering and the reported extrapolation/occupancy convention |
| Semiconductor/insulator relaxation | Use small Gaussian/Fermi-like broadening only when needed for stability, or fixed occupations when the band gap is reliable | Confirm that forces and the final gap/energy are insensitive to the choice |
| Semiconductor/insulator static energy or DOS | Use fixed occupations or a tetrahedron method when the mesh and engine support it | Confirm the mesh is dense enough and that no partially occupied states are being hidden |
| Phonon/EPC | Treat electronic smearing as a separate numerical parameter from relax | Converge frequencies, linewidths, `lambda`, `omega_log`, or the actual target observable |

Engine mappings must be explicit:

- VASP records `ISMEAR` and `SIGMA` in eV. `ISMEAR=0`, Methfessel–Paxton,
  Fermi–Dirac, cold smearing, and tetrahedron choices have different numerical
  meanings; do not choose by tag number alone.
- QE records `occupations`, `smearing`, and `degauss`, with `degauss` in Ry.
  Metallic `smearing` and `tetrahedra`/`fixed` occupations are separate
  choices. If a value is discussed in eV, record the conversion to Ry in the
  design.

When no project evidence exists, a width campaign can start with a small set
such as `0.02`, `0.05`, `0.10`, and `0.20 eV` for VASP-like units, reduced or
expanded according to the material and stage. These are candidate values, not
defaults. A large width chosen only because it makes an SCF finish is not
evidence of a converged production protocol.

For metallic MgB2/MgB6 work, keep the relax, static SCF, phonon, and EPC
occupations visibly separate. A scalar EPC result cannot be declared
converged merely because the preceding relax converged with the same width.

## K-point density from the lattice

Use reciprocal vectors rather than the direct lattice lengths alone. If the
direct lattice vectors are the rows of `A` in Å, construct

```text
B = 2*pi * inverse(A).transpose()
```

and let `b_i` be the reciprocal vector for direction `i` in Å⁻¹. For a target
spacing `Delta_k_i` in Å⁻¹, generate the starting mesh as

```text
N_i = max(1, ceil(norm(b_i) / Delta_k_i))
```

The design must state whether the `2*pi` factor is included, the units of the
target spacing, and the rounding rule. For non-orthogonal cells, do not use a
simple `a_i`-length shortcut. For a slab or 2D system, set the non-periodic
direction to `1` unless the project deliberately models periodic vacuum
interactions.

Typical initial spacing ranges are only search seeds:

- ordinary bulk exploratory work: roughly `0.15–0.25 Å⁻¹`;
- metallic bulk/static work: roughly `0.10–0.20 Å⁻¹`;
- phonon/EPC or other Fermi-surface-sensitive work: often `0.05–0.15 Å⁻¹`.

The final mesh is selected by the claim-supporting convergence test, not by
the lattice formula alone. Record Gamma-centered versus Monkhorst–Pack
sampling, shifts, parity choices, and any separate q mesh. Do not silently
reuse a relax mesh for DOS, phonon, or EPC work.

## Required parameter record

Every schema-v2 engine envelope has `parameter_selection.basis_cutoff`,
`parameter_selection.occupations`, and `parameter_selection.kpoints`. Each
category uses the same structure:

```text
status: pending | candidate | validated
method: candidate-generation and selection method
source_metadata: exact POTCAR/UPF, material-class, stage, or lattice facts
candidate_values: explicit tested values
units: explicit units or dimensionless
fixed_conditions: engine, functional, pseudopotential, structure, other meshes
target_observable_ids: claim-supporting observable IDs
acceptance_rule: numerical threshold and required consecutive points
selected_value: null until evidence is accepted
evidence_refs: convergence-study IDs or verified evidence IDs
```

An approved convergence study may set its study-level `selected_value`; update
the matching parameter category to `validated` only after confirming that its
method, fixed conditions, observable, units, and evidence apply to the target
matrix. Do not promote a value by changing the status label alone.

For research-mode production approval, all three categories are `validated`, every selected
value belongs to its candidate list, the references resolve, and
`engine_parameters` contains the exact reviewed engine values. Raw evidence is
referenced by workspace-relative task or analysis paths. Record SHA256 only for
approved scientific input/dependency identity or an explicitly requested
transfer; routine campaign status does not need a new hash.

An estimated value may prepare an exploratory or convergence task, but it
cannot authorize production preparation or submission by itself.
