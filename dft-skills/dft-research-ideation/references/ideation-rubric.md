# DFT Ideation Rubric

## Generation operators

- Contradiction resolution: design one calculation matrix that distinguishes
  competing explanations under a common comparison contract.
- Mechanism transfer: transfer a mechanism—not merely a material label—from a
  related system and state what would falsify the transfer.
- Missing-control completion: add the omitted phase, structure, charge,
  magnetic state, surface, chemical potential or reference calculation.
- Regime extension: move into strain, field, composition, pressure, thickness,
  temperature proxy or defect-density regimes only with physical motivation.
- Method-limit test: ask whether a published conclusion survives a known
  numerical or functional limitation.
- Literature–data tension: use verified local results to challenge or narrow a
  published generalization.

Generate 4–8 candidates. Diversity should come from different mechanisms or
decision uses, not cosmetic variations of one workflow.

## Four independent review lenses

1. Literature and novelty: evidence quality, closest overlap, distinction from
   routine extension and whether the novelty statement is calibrated.
2. Materials physics: mechanism plausibility, thermodynamic/kinetic distinction,
   relevant degrees of freedom, boundary conditions and alternative causes.
3. DFT numerics: observable-method fit, reference-state compatibility,
   convergence burden, corrections, finite-size effects and uncertainty.
4. Resources and reproducibility: task count, dependency chain, HPC fit,
   storage, failure recovery, controls and whether a negative result is useful.

Record review comments in `review_history`; do not average away a hard veto.

## Scores

Score each dimension from 1 to 5. Higher is better:

- `literature_grounding`: 1 speculative; 3 traceable core evidence; 5 multiple
  verified primary sources plus local context.
- `novelty`: 1 known duplicate; 3 defensible distinction with partial overlap;
  5 broad recorded search finds no close equivalent.
- `significance`: 1 isolated number; 3 resolves a useful mechanism/property;
  5 changes a recognized scientific decision.
- `falsifiability`: 1 vague trend; 3 measurable but weak threshold; 5 explicit
  alternatives, observable and quantitative decision rule.
- `dft_tractability`: 1 method cannot answer; 3 feasible with major caveats; 5
  direct observable-method match and bounded matrix.
- `numerical_robustness`: 1 dominated by unresolved artifacts; 3 manageable
  convergence/corrections; 5 strong controls and uncertainty plan.
- `resource_fit`: 1 exceeds available resources; 3 feasible with tradeoffs; 5
  comfortably executable with informative stopping rules.

A selected idea must meet the machine-enforced minimums and cannot retain
unknown novelty checks, high overlap, unverified cited evidence or pending user
decisions.
