# DFT Engine Contract

## Canonical v2 envelope

Use schema-v2 `engine_stage_envelopes` to separate scientific intent from an
engine's file syntax. Every matrix item has exactly one envelope and every
execution-plan task points to its matrix envelope.

```json
{
  "matrix_id": "M1",
  "engine": "quantum-espresso",
  "structure_source": "approved MgB2 structure",
  "parameter_policy": "exact reviewed settings; no hidden defaults",
  "kpoints_policy": "reciprocal-spacing estimate followed by convergence",
  "pseudopotential_policy": "one fixed PBE UPF family",
  "pseudopotential_registry_ids": ["private-pbe-mg-b-v1"],
  "resource_profile": "phoenix_cpu",
  "completion_gates": {"scf": "declared energy and charge thresholds"},
  "parameter_selection": {
    "basis_cutoff": {
      "status": "validated",
      "method": "UPF recommendations plus observable convergence",
      "source_metadata": {"upf_labels": ["Mg.upf", "B.upf"]},
      "candidate_values": [70, 80, 90],
      "units": "Ry",
      "fixed_conditions": ["same structure, k mesh, occupations and UPFs"],
      "target_observable_ids": ["O1"],
      "acceptance_rule": "target change below the declared threshold",
      "selected_value": 80,
      "evidence_refs": ["CV1"]
    },
    "occupations": {
      "status": "validated",
      "method": "metallic stage policy plus width convergence",
      "source_metadata": {"material_class": "metal", "stage": "scf"},
      "candidate_values": ["marzari-vanderbilt:0.01_Ry", "marzari-vanderbilt:0.02_Ry"],
      "units": "Ry",
      "fixed_conditions": ["same structure, cutoff, k mesh and UPFs"],
      "target_observable_ids": ["O1"],
      "acceptance_rule": "energy ordering and target observable remain stable",
      "selected_value": "marzari-vanderbilt:0.02_Ry",
      "evidence_refs": ["CV2"]
    },
    "kpoints": {
      "status": "validated",
      "method": "2*pi reciprocal vectors plus convergence",
      "source_metadata": {"target_spacing_per_A": 0.12, "centering": "gamma"},
      "candidate_values": ["12x12x12", "16x16x16", "20x20x20"],
      "units": "1/angstrom",
      "fixed_conditions": ["same structure, cutoff, occupations and UPFs"],
      "target_observable_ids": ["O1"],
      "acceptance_rule": "target change below the declared threshold",
      "selected_value": "16x16x16",
      "evidence_refs": ["CV3"]
    }
  },
  "engine_parameters": {
    "ecutwfc_Ry": 80,
    "ecutrho_Ry": 640,
    "occupations": "smearing",
    "smearing": "marzari-vanderbilt",
    "degauss_Ry": 0.02,
    "k_mesh": [16, 16, 16],
    "k_shift": [0, 0, 0]
  }
}
```

Known engine identifiers are `vasp`, `quantum-espresso`, `cp2k`, `abinit`,
`gpaw`, and `other`. An identifier means only that the design is expressible;
workflow verifies the operational backend and approved project resource
profile before initialization or submission.

Keep these concepts engine-neutral in common fields:

- basis representation and cutoff policy;
- exchange-correlation functional and dispersion correction;
- pseudopotential/PAW family, version, labels, and approved identity hashes;
- reciprocal-space or real-space sampling policy;
- spin, magnetism, charge, relativistic treatment, and occupations;
- electronic and ionic convergence gates;
- structure source and transformations;
- resource and completion envelopes.

Place exact VASP tags, Quantum ESPRESSO namelists, or CP2K sections under
`engine_parameters`. Never translate settings by tag-name substitution alone:
compare physical meaning, units, defaults, and algorithms. An empty object may
be used during exploration but cannot pass research-mode production approval.
In `design_mode: task`, exact `user_specified` parameters may execute without convergence
evidence; record their source and do not label their accuracy validated.

Current on-disk inputs are authoritative when the envelope is materialized.
Hash mismatch triggers reconciliation, not re-approval. The adapter classifies
the semantic change; it does not rewrite a user-owned input or silently change
the scientific model.

## Compatibility only

Schema-v1 `vasp_stage_envelopes` remains readable for compatibility. New or
revised designs use schema v2. Private registry metadata may identify a licensed
dataset, but it never authorizes publishing or copying its contents.
