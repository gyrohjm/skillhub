# Project Specification Schema

Write a UTF-8 JSON file. Content should be bilingual Chinese/English by default; keys remain English.

## Required Fields

```json
{
  "project_name": "中文名称 / English name",
  "project_slug": "english_lowercase_snake_case",
  "mode": "generic | experimental | computational | hybrid",
  "domain": "research domain",
  "summary": "One-sentence project goal / 一句话目标",
  "research_questions": ["Q1 ..."],
  "hypotheses": [
    {
      "id": "H1",
      "statement": "Testable statement / 可检验陈述",
      "falsification": "Observation that would reject it / 否证条件"
    }
  ],
  "objectives": [
    {
      "id": "O1",
      "description": "Executable objective / 可执行目标",
      "success_criteria": "Measurable acceptance criterion / 可测验收标准"
    }
  ]
}
```

## Optional Fields

```json
{
  "background": "Current scientific and project context",
  "deliverables": ["paper figure", "validated dataset"],
  "constraints": ["instrument time", "cluster allocation"],
  "experiment_plan": {
    "variables": [],
    "controls": [],
    "measurements": [],
    "replication": "",
    "analysis": "",
    "stop_conditions": []
  },
  "computation_plan": {
    "models": [],
    "methods": [],
    "parameter_matrix": [],
    "vasp_workflow_envelope": [
      {
        "system_slug": "sic_bulk",
        "case_slug": "pbe_static_chain",
        "stages": ["relax", "scf", "band", "dos"],
        "incar_inheritance": "SCF/band/DOS inherit reviewed relax electronic settings unless overridden here",
        "stage_overrides": {
          "scf": {"IBRION": -1, "NSW": 0, "LWAVE": ".TRUE.", "LCHARG": ".TRUE."}
        },
        "kpoints_policy": "relax/scf/dos meshes and band path to be listed before production",
        "potcar_labels": {"Si": "Si", "C": "C"},
        "cluster_profile": "nmg | phoenix | phoenix-gpu-a100 | phoenix-gpu-g3 | generic",
        "restart_link_policy": "link SCF CHGCAR/WAVECAR into downstream tasks with ln -s"
      }
    ],
    "convergence": [],
    "validation": [],
    "resource_budget": "",
    "stop_conditions": []
  },
  "systems": [
    {
      "system_slug": "sic_bulk",
      "case_slugs": ["relax_pbe", "scf_pbe"]
    }
  ],
  "milestones": [
    {"id": "M1", "description": "", "acceptance": "", "target_date": ""}
  ],
  "risks": [
    {"risk": "", "likelihood": "", "impact": "", "mitigation": ""}
  ],
  "evidence": {
    "external_search_approved": false,
    "sources": [],
    "pending_validation": []
  },
  "terminology": {"term": "definition"}
}
```

## Validation Rules

- `project_slug` must match `^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$`.
- Do not transliterate a Chinese project name mechanically. Propose an English slug and ask the user to confirm it.
- `mode` controls optional experimental and calculation directories.
- `systems` is optional. When present, `system_slug` and every `case_slug` must
  use English `lowercase_snake_case`; the initializer pre-creates
  `raw_data/calculations/<system_slug>/<case_slug>/` and
  `formal_data/structures/<system_slug>/`.
- If `systems` is absent, create only `raw_data/calculations/` and add system
  directories later using the same naming rule.
- Every hypothesis needs a falsification condition.
- Every objective needs measurable success criteria.
- For VASP projects, `computation_plan.vasp_workflow_envelope` should be filled
  before production. It defines which downstream stages can reuse the initial
  workflow approval and which changes require a new review.
- Unknown values remain explicit `TBD` items; do not fabricate them.
