# Computational Research Design Checklist

Use this reference when project mode is `computational` or `hybrid`.

## Model Definition

- Establish structure, phase, composition, boundary conditions, charge, spin, defects, interfaces, and finite-size assumptions.
- Record the provenance of every production structure and parameter choice.
- Separate exploratory models from production models.

## Method and Parameter Matrix

- Define the physical quantity or hypothesis each calculation tests.
- Define method, code/version, pseudopotential or basis, functional/model, numerical precision, sampling, smearing, and relaxation constraints.
- Run convergence tests on quantities that affect the scientific claim, not only total energy.
- Define a minimal baseline, controlled variants, and validation references.
- Estimate task count, storage, wall time, and restart requirements before production execution.

## Validation

- Check structural sanity, symmetry assumptions, energy/force convergence, k-point or sampling convergence, and finite-size effects.
- Compare against analytical limits, trusted literature, experiment, or an independent method where available.
- Define acceptable numerical uncertainty and physical agreement before running the final matrix.
- Record failed calculations; do not silently discard them.

## Stop and Handoff Rules

- Stop expanding the matrix when the hypothesis is resolved within predefined uncertainty or when further calculations cannot discriminate competing explanations.
- Escalate unresolved structure, phase, or method provenance before production runs.
- For VASP input preparation, review, or submission, hand off to `vasp-workflow`.
- For completed-output extraction and plotting, hand off to `vasp-analysis`.
