---
name: dft-research-ideation
description: Conduct literature-grounded research-gap mapping and generate, challenge, rank, and select falsifiable research ideas specifically for DFT and computational materials projects. Use when exploring what DFT calculation is worth doing next, turning papers or local results into hypotheses, checking novelty, resolving contradictory literature, proposing observables/controls/reference states/convergence axes, or preparing an idea handoff to dft-design. Orchestrates research-teach for authenticated literature acquisition and hands selected proposals to dft-design; does not approve calculations, invent production parameters, submit jobs, or claim novelty without a recorded search.
---

# DFT Research Ideation

For DFT project work, read the applicable AGENTS.md and project storage_role; MEMORY.md belongs to the local planning side.
Before saving documents or handing off decisions, follow
[project records](../dft-contracts/references/project-records.md) for fixed paths,
names and evidence-linked memory. Environment details stay in private local profiles.

For paired local/cluster projects, read [paired projects](../dft-contracts/references/paired-projects.md) before preparing inputs, writing analysis or transferring results.



Turn verified literature and local calculation evidence into a small portfolio
of testable, computationally defensible DFT ideas.

```text
research-teach -> dft-research-ideation -> dft-design -> dft-workflow
```

`research-teach` owns search planning, screening, authenticated downloading,
conversion and source-note verification. This skill owns gap synthesis, idea
generation, novelty checking, adversarial review and user selection.
`dft-design` owns the formal calculation matrix and scientific approval.

## Select a mode

- `scope`: confirm the research question, decision use and constraints.
- `landscape`: create evidence cards, controversy map and DFT-addressable gaps.
- `ideate`: generate 4–8 candidates from verified gaps.
- `review`: challenge and score existing candidates.
- `select`: record the user's chosen idea and create a proposal-only handoff.
- `full`: run all stages in order, pausing at the confirmation gates.

## Initialize project records

```bash
python3 <this-skill-directory>/scripts/dft_ideation.py bootstrap \
  --project <workspace_root> --project-slug <lowercase_slug>
```

This creates only missing files under `plans/research/ideation/`. This is the
intentional pre-system staging area: ideation can start before a composition or
structure slug is resolved. After selection, hand the proposal to
`dft-design`, which writes the scoped plan under
the registered route docs/ scope (legacy `plans/<composition>/<structure>/`). Resolve `<this-skill-directory>` from the
loaded `SKILL.md`; do not copy the skill script into the project.

## Required workflow

1. Read `../dft-contracts/references/workspace-layout.md`; discover the nearest
   workspace, then read project context, existing DFT designs, accepted live
   task results, relevant `failed/` evidence, and the user's constraints. Do
   not assume `$PWD` or a stored absolute path is the workspace. Confirm the
   research question, materials/structures,
   phenomenon, intended decision, exclusions, available compute and core
   journals.
2. If verified literature notes do not already exist, invoke
   `$research-teach` in `research`/`build` mode. Follow its three confirmation
   gates and browser/privacy rules. Do not duplicate its downloader or PDF
   conversion logic.
3. Read `references/literature-protocol.md`. Build passage-level evidence cards
   with DOI/URL or local-result hash and precise page/figure/table locator.
4. Synthesize themes, contradictions, missing controls, unexplored regimes,
   method limits and uncertainty gaps. A gap is useful only when the record
   explains why DFT can discriminate among alternatives.
5. Generate candidates using at least three operators: contradiction
   resolution, mechanism transfer, missing-control completion, regime
   extension, method-limit testing, or literature-plus-local-result tension.
6. For every idea, specify hypothesis, falsification, observable and unit,
   quantitative decision rule, controls, compatible reference states,
   convergence axes, uncertainty sources, calculation outline, resource
   estimate and failure modes.
7. Run a targeted novelty search for every idea. Record exact queries, sources,
   date, closest overlap and outcome. `unknown` means novelty is unresolved;
   absence from one query never proves novelty.
8. Read `references/ideation-rubric.md` and perform four independent review
   lenses: literature/novelty, materials physics, DFT numerics/comparability,
   and resources/reproducibility. Refine low-scoring ideas and retain review
   history rather than hiding rejected candidates.
9. Validate and rank the portfolio. Discuss tradeoffs with the user; never pick
   the winner silently.
10. Only after explicit user selection, create the immutable selection record.
    Hand `dft_design_seed.json` to `$dft-design`; it is not an approved
    calculation design.

```bash
python3 <this-skill-directory>/scripts/dft_ideation.py validate \
  --portfolio <workspace_root>/plans/research/ideation/idea_portfolio.json
python3 <this-skill-directory>/scripts/dft_ideation.py rank \
  --portfolio <workspace_root>/plans/research/ideation/idea_portfolio.json
python3 <this-skill-directory>/scripts/dft_ideation.py select \
  --project <workspace_root> \
  --portfolio <workspace_root>/plans/research/ideation/idea_portfolio.json \
  --idea I1 --reviewer <name>
```

## Scientific guardrails

- Distinguish published evidence, verified local results, inference, proposal
  and user decision. Never convert plausibility into evidence.
- Do not call a routine material substitution, parameter sweep or higher-cost
  functional “novel” without a mechanism-level question and novelty search.
- Do not propose energy comparisons without compatible reference states,
  pseudopotential/method policy and normalization.
- Do not use a target observable that the proposed DFT level cannot resolve.
  Mark needs for SOC, hybrid DFT, +U, finite-size correction, phonons, NEB,
  finite temperature or beyond-DFT methods explicitly.
- Design convergence around the claim-supporting observable, not total energy
  alone. Include numerical uncertainty and a stopping rule.
- Reviews, textbooks and authoritative pages may orient or teach; quantitative
  research claims should trace to primary papers, official documentation,
  trusted databases or verified local results.
- A negative or inconclusive result can be valuable if it falsifies a clear
  hypothesis. Do not optimize only for positive outcomes.

Read `references/dft-guardrails.md` before scoring production-oriented ideas.

## Output contract

The live source of truth is
`plans/research/ideation/idea_portfolio.json` using
`dft.research-idea.v1`. Selection writes:

```text
docs/records/dft_ideation/<portfolio_id>/rNNNN/
  idea_portfolio.json
  selection.json
  dft_design_seed.json
```

Selection authorizes only a `dft-design` interview. It does not authorize input
generation, production parameters or submission.

## Reference map

- `references/literature-protocol.md`: DFT-specific search, screening and gap
  extraction.
- `references/ideation-rubric.md`: generation operators, four review lenses and
  scoring anchors.
- `references/dft-guardrails.md`: physics, comparability and numerical failure
  checks.
- `references/handoff-contract.md`: portfolio and `dft-design` seed mapping.
- `references/online-inspirations.md`: public projects examined and the design
  choices adopted or rejected.
