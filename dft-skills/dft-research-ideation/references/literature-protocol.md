# DFT Literature Protocol

## Search design

Build queries from four blocks:

1. system: composition, phase, dimensionality, surface, interface, defect,
   adsorbate or charge state;
2. phenomenon: stability, bonding, electronic, magnetic, vibrational,
   transport, optical, catalytic or migration behavior;
3. method: DFT synonyms plus engine/method variants when relevant;
4. discriminator: mechanism, controversy, benchmark, convergence, correction,
   uncertainty, reference state or failure.

Use at least one broad scholarly index, one citation/metadata source and
publisher/primary pages. Confirm a project-specific head-journal list with the
user; do not hard-code journal prestige as a substitute for relevance or
method quality. Search reviews for vocabulary and citation trails, then verify
critical claims in primary sources.

For each candidate, screen title, keywords, abstract, year, document type,
journal fit, method relevance and likely evidentiary value before downloading.
Use Research/Teaching/Both/Reject and record the exclusion reason. Follow
`research-teach` for authenticated access and batch confirmation.

## Evidence cards

Each card in `idea_portfolio.json.evidence` must answer:

- what exact claim or method choice is supported;
- where it appears: page, section, equation, figure, table or supplementary
  item;
- whether it is primary evidence, method context, contradiction or teaching;
- DOI/URL or local result fingerprint/hash;
- whether full text and the cited passage were verified.

An abstract-only reading can guide search but should remain `pending` for
quantitative claims. A local result needs a stable source hash or calculation
fingerprint.

## Gap extraction

Prefer DFT-addressable gaps:

- two papers disagree under apparently comparable conditions;
- a claimed mechanism lacks a discriminating observable;
- a baseline, reference phase, charge state or magnetic order is missing;
- a conclusion is sensitive to finite size, k mesh, vacuum, functional, +U,
  SOC, dispersion or correction choice;
- a regime is unexplored but physically motivated;
- an experimental trend can be decomposed into competing atomistic mechanisms;
- existing local results contradict or refine the literature picture.

Do not label “few papers found” as a gap until synonyms, citation trails and
closest-overlap searches have been checked.

## Novelty protocol

For each idea record at least:

1. exact material + mechanism + observable;
2. synonyms and neighboring compositions/structures;
3. closest known paper and its forward/backward citation neighborhood;
4. method-specific overlap, including preprints and recent accepted work.

Classify overlap as `none_found`, `partial`, `high`, or `unknown`. `none_found`
means only that the recorded search did not find overlap; phrase novelty claims
accordingly.
