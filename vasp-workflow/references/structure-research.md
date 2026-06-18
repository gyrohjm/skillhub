# Structure Research

Use this reference when the user asks for a POSCAR but does not know the exact
phase, prototype, lattice, database ID, slab orientation, defect model, or
magnetic/ordering state. Do not create a production POSCAR from formula alone.

## Required Flow

1. Clarify the calculation intent: bulk, surface/slab, interface, defect,
   doped/alloyed structure, molecule, adsorption, strained cell, or phonon
   reference.
2. Search reliable structure sources available in the environment: Materials
   Project, OQMD, AFLOW, COD, ICSD/local licensed data, user-provided CIF/POSCAR,
   prior project folders, or papers. Use live web/API/search when the source is
   not already present locally.
3. Present candidate structures before writing POSCAR. Include at least:
   source/database ID, formula, phase/prototype, space group, cell type
   (primitive/conventional/supercell), lattice parameters, atom count, magnetic
   or ordering notes, energy/stability if available, and citation/source link.
4. Ask the user to choose the intended structure or narrow the target. If the
   candidates imply different science (for example 3C/4H/6H SiC, rutile/anatase
   TiO2, graphite/diamond/graphene), do not pick one silently.
5. Generate `structure/POSCAR.initial` only after the chosen structure/model is
   explicit. Save provenance in `structure/metadata.json`; save the downloaded
   source file when allowed (for example `structure/source.cif`).
6. Continue with normal input review, relax preparation, and submit review.

## Candidate Review Format

Use a compact table like:

```text
candidate_id | source | phase/prototype | space_group | cell | lattice | atoms | notes
mp-...       | MP     | 3C-SiC/zincblende | F-43m ...   | primitive | a=... | 2 | bulk cubic
cod-...      | COD    | 4H-SiC            | P63mc ...   | conventional | a=..., c=... | 8 | hexagonal
```

Then state the tradeoff in plain language: which candidate matches the user's
request, what assumptions remain, and what would change for relax/phonon/band
path generation.

## Questions To Ask

Ask only the questions needed to prevent a wrong structure:

- Which phase/prototype should be used?
- Primitive cell or conventional cell?
- Bulk, slab/surface orientation, interface, defect, dopant, or adsorption?
- Any fixed atoms/selective dynamics required?
- Any magnetic order, charge state, spin polarization, or site ordering?
- Should symmetry be preserved, standardized, or deliberately broken?

If the user is unsure, propose 2-4 plausible candidates and explain why they
are distinct calculation targets.

## POSCAR Generation Rules

- Prefer direct conversion from CIF/POSCAR/database object with `pymatgen` or
  `ase` when available. If neither is available, ask the user before manually
  constructing anything nontrivial.
- State whether the POSCAR is primitive, conventional, supercell, slab, defect,
  or transformed from a parent structure.
- Preserve physically meaningful site labels/order when needed. Otherwise sort
  generated atoms by descending `z`, then ascending `x`, then ascending `y`.
- Record coordinate mode (`Direct` or `Cartesian`), lattice vectors/lengths,
  element order/counts, and selective-dynamics flags.
- For slabs/interfaces, record vacuum thickness, surface orientation, layer
  count, termination, fixed layers, dipole direction, and any passivation.
- For defects/dopants, record parent structure ID, supercell matrix, replaced or
  removed site, defect charge/magnetic assumptions, and final composition.
- For phonon reference structures, use the relaxed bulk/constrained structure
  chosen for the phonon calculation, not an unreviewed database geometry.

## Metadata

Write `structure/metadata.json` with enough information to reproduce the choice:

```json
{
  "schema_version": 1,
  "created_by": "agent",
  "created_at": "UTC timestamp",
  "user_request": "original structure request",
  "chosen_candidate": {
    "source": "Materials Project / COD / paper / user file / local project",
    "source_id": "database id or file path",
    "phase": "phase or prototype",
    "space_group": "symbol and number when known",
    "cell_type": "primitive / conventional / supercell / slab / defect",
    "formula": "reduced and full formula",
    "lattice": "a,b,c,alpha,beta,gamma or vector lengths"
  },
  "candidates_reviewed": [
    {
      "source": "database or literature source",
      "source_id": "id/path/DOI",
      "phase": "phase/prototype",
      "space_group": "symbol/number",
      "reason_not_chosen": "short reason"
    }
  ],
  "transformations": [
    "standardized primitive cell",
    "made 2x2x1 supercell",
    "sorted atoms by z desc, x asc, y asc"
  ],
  "user_confirmation": "what the user approved"
}
```

Do not store licensed database payloads or POTCAR contents in public repos.

## Red Lines

- Do not choose a phase only because it is the first search result.
- Do not mix structures from different sources without saying so.
- Do not replace experimental lattice constants with relaxed/database values
  without review.
- Do not use unstable/metastable candidates as production defaults unless the
  user explicitly wants that phase.
- Do not assume a band path until the final lattice/prototype is chosen.
- Do not proceed to `sbatch` until the POSCAR source and transformations appear
  in `submission_review.dat` and the user approves them.
