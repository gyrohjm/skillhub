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
    "convergence": [],
    "validation": [],
    "resource_budget": "",
    "stop_conditions": []
  },
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
- Every hypothesis needs a falsification condition.
- Every objective needs measurable success criteria.
- Unknown values remain explicit `TBD` items; do not fabricate them.
