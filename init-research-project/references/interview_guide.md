# Research Project Interview Guide

Ask one to three questions per round. Summarize what is settled before moving on. Do not initialize files until the user confirms the final blueprint.

## Round 1: Project Identity

- What phenomenon, system, or practical problem is being studied?
- What is the intended English `lowercase_snake_case` project slug?
- Is the project generic, experimental, computational, or hybrid?
- What concrete deliverable is expected: paper, dataset, method, prototype, thesis chapter, or decision?

## Round 2: Scientific Claim

- State the primary research question in one sentence.
- Convert the proposed explanation into falsifiable hypotheses.
- Ask what observation would disprove each hypothesis.
- Separate known evidence, user assumptions, and unresolved claims.
- Challenge causal claims that are supported only by correlation or one uncontrolled calculation.

## Round 3: Current State

- What samples, structures, datasets, scripts, calculations, instruments, and preliminary results already exist?
- What sources establish the structure, phase, method, or baseline?
- Ask permission before searching external literature or databases.
- Record missing evidence as an explicit validation task rather than filling gaps with guesses.

## Round 4: Design and Constraints

- Identify independent variables, dependent observables, controls, nuisance variables, and validation references.
- Confirm equipment, software, cluster, budget, sample, storage, time, and collaboration constraints.
- Define convergence, reproducibility, uncertainty, and failure criteria.
- Select the smallest experiment or calculation that can meaningfully falsify the main hypothesis.

## Round 5: Execution Contract

- Define objectives with measurable success criteria.
- Define milestones, dependencies, decision gates, risks, and stopping rules.
- Separate exploratory work from production-quality work.
- Confirm which outputs may eventually be promoted into `formal_data`.

## Final Blueprint

Before initialization, present:

1. Project name, English slug, mode, and one-sentence goal.
2. Research questions and falsifiable hypotheses.
3. Experimental and/or computational task matrix.
4. Validation strategy and stop conditions.
5. Deliverables, milestones, constraints, and risks.
6. Proposed directory tree and existing-file conflict report.
7. External-search status and unresolved assumptions.

Ask for explicit confirmation before running the initializer with `--apply`.
