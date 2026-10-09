# DFT Ideation Guardrails

Before an idea receives `keep`, check:

- Structure: phase, stoichiometry, defects, surfaces/interfaces, reconstruction,
  symmetry and provenance are representable.
- State: charge, spin order, oxidation assumptions, occupations, boundary
  conditions and environment are explicit.
- Observable: the chosen DFT level can resolve it; required SOC, +U, hybrid,
  dispersion, phonons, NEB, dielectric response or finite-temperature treatment
  is named rather than hidden.
- Comparison: energies share compatible composition/reference reactions,
  pseudopotential family, basis policy, k sampling, smearing and normalization.
- Convergence: each artifact-sensitive axis is tied to the claim-supporting
  observable and a numerical threshold.
- Alternatives: at least one control can distinguish the proposed mechanism
  from a simpler explanation.
- Corrections: charged defects, slabs, dipoles, finite supercells, image
  interactions, chemical potentials and entropy are handled when relevant.
- Cost: expensive methods are staged behind lower-cost screening and stopping
  gates when scientifically valid.
- Failure value: a falsified or inconclusive outcome still updates the research
  question rather than merely “failing to publish.”

Hard blockers include incompatible energy comparisons, no falsification rule,
no stable reference state, an observable outside the method's capability,
unbounded combinatorial matrices, or a novelty claim based only on memory.
