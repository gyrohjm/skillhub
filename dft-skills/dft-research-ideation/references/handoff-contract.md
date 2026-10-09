# Ideation to DFT Design Handoff

`dft.research-idea.v1` is an evidence and decision record. It is not a
calculation design. After explicit selection, `dft_design_seed.json` maps:

- research question -> draft `research_questions`;
- hypothesis/falsification -> draft `hypotheses`;
- scoped materials -> unresolved systems and structure provenance;
- target observables -> draft observables and decision rules;
- controls/reference states -> design interview inputs;
- convergence axes -> convergence studies that still need ranges and thresholds;
- calculation outline -> candidate matrix stages;
- evidence cards -> design evidence with provenance;
- risks/resources -> uncertainty, resource and stopping-rule interview inputs.

The seed deliberately omits approved engines, production parameters, concrete
pseudopotentials, k meshes, cutoffs and Slurm resources. `dft-design` must
resolve those fields, validate its own contract and obtain explicit scientific
approval. Ideation selection never authorizes `dft-workflow` or `sbatch`.
