# Online Inspirations

Public projects were used as design references, not copied as runtime
dependencies:

- [ResearchAgent](https://github.com/JinheonBaek/ResearchAgent): seed-paper and
  citation-neighborhood retrieval, iterative problem generation, multi-metric
  review and concise refinement history. Adopted: iterative evidence-grounded
  generation and explicit review dimensions.
- [HypoGeniC/HypoRefine](https://github.com/ChicagoHAI/hypothesis-generation):
  combines literature and observed data for hypothesis refinement. Adopted:
  literature plus verified local DFT results; rejected: treating model output as
  evidence without a calculation/source contract.
- [PaperQA2](https://github.com/Future-House/paper-qa): agentic search, evidence
  gathering, metadata-aware retrieval, local full-text index and cited answers.
  Adopted: passage-level evidence and iterative query refinement; runtime use is
  optional because `research-teach` already owns local acquisition/conversion.
- [Scideator](https://arxiv.org/abs/2409.14634): purpose/mechanism/evaluation
  facet recombination and novelty iteration. Adopted: mechanism-level
  recombination and closest-overlap checks; constrained here by DFT observables,
  reference states and numerical feasibility.
- [Chain-of-Ideas Agent](https://github.com/DAMO-NLP-SG/CoI-Agent): literature
  chains followed by idea and experiment design. Adopted: preserve development
  lineage; rejected: direct experiment generation before DFT design approval.
- [K-Dense scientific literature-review skill](https://github.com/K-Dense-AI/scientific-agent-skills/blob/main/scientific-skills/literature-review/SKILL.md):
  documented search strategy, inclusion/exclusion, multi-source retrieval,
  thematic synthesis and citation verification. Adopted through the existing
  `research-teach` screening and verification gates.
- [MatClaw](https://github.com/DingyangLyu/MatClaw): materials-computation skills
  with runnable workflows and method decision trees. Adopted: DFT-specific
  feasibility gates; rejected: automatic execution from an unapproved idea.

The resulting boundary is intentionally conservative: literature acquisition
and verification remain in `research-teach`; ideation remains proposal-only;
formal scientific design, submission, analysis and archive remain in their
existing DFT skills.
