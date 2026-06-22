# Scientific Computation Design

## Question and Claim

- State the decision the calculations will support.
- Convert each proposed explanation into a falsifiable hypothesis.
- State what result would support, reject, or leave each hypothesis
  inconclusive.
- Avoid claims stronger than the designed comparison can establish.

## Systems and Models

- Record composition, phase, structure provenance, charge, spin, constraints,
  boundary conditions, finite-size assumptions, and symmetry assumptions.
- Separate physical model changes from numerical parameter changes.
- Use the smallest model that can discriminate the hypotheses, then test the
  model limitations that could change the conclusion.

## Variables and Controls

- Identify independent variables, observables, nuisance variables, and fixed
  conditions.
- Include a baseline and applicable positive or negative controls.
- Compare like with like: structures, cells, reference energies, sampling,
  smearing, and precision must be compatible when the claim depends on their
  difference.
- Use a factorial matrix only when interactions are scientifically relevant and
  the resource budget can resolve them.

## Convergence and Validation

- Select convergence observables from the claim: examples include energy
  differences, forces, stress, geometry, gaps, frequencies, or response
  functions. Total-energy convergence alone may be insufficient.
- Define candidate values, fixed conditions, an acceptance rule, and how the
  production value will be selected.
- Validate against an analytical limit, trusted literature, experiment, a
  higher-accuracy model, or an independent implementation when available.
- Define acceptable numerical uncertainty separately from physical agreement.

## Task Classes

- `exploratory`: resolves feasibility or an uncertain model; never a production
  result by default.
- `convergence`: selects numerical values using a predefined acceptance rule.
- `validation`: tests the model or method against independent evidence.
- `production`: answers the approved scientific question with fixed, validated
  parameters.

## Evidence and Decisions

- Mark evidence as `verified` only after checking the cited source or completed
  benchmark artifact.
- Use primary papers, official software documentation, trusted databases, or
  project-generated convergence results for production-critical claims.
- Keep `pending` evidence and unresolved decisions visible. A production matrix
  cannot be approved while its critical values depend on them.

## Resource and Stop Rules

- Estimate task count, core/GPU hours, wall time, storage, restart behavior, and
  analysis cost before approval.
- Define failure criteria and the maximum allowed expansion of a matrix.
- Stop when the hypothesis is resolved within the target uncertainty, controls
  fail, the resource envelope is exceeded, or the planned calculations cannot
  discriminate the alternatives.
