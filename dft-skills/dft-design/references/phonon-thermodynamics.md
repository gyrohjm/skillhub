# Phonon Thermodynamics Domain Contract

Use `phonon-thermodynamics` with `domain_metadata.method` equal to
`finite_displacement` or `dfpt`. Finite displacement requires `supercell`,
`displacement_distance_A`, and `imaginary_frequency_tolerance_cm1`; DFPT
requires `q_mesh` and the same explicit imaginary-mode tolerance.

Converge the claim-supporting quantity against supercell or q mesh. Record
acoustic sum-rule handling, non-analytical correction policy, Born charges and
dielectric tensor provenance when LO–TO splitting matters. Treat small
imaginary modes within the approved numerical tolerance separately from robust
instabilities; neither may be silently discarded.
