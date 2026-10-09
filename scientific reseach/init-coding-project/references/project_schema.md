# Project Specification Schema

Write UTF-8 JSON. Keep keys, enum values, slugs, paths, commands, and technical identifiers in English. Human-facing values follow the user's language. Do not duplicate all prose in two languages.

## Required shape

```json
{
  "schema_version": 1,
  "project_name": "项目名称",
  "project_slug": "example-project",
  "summary": "一句话项目目标",
  "documentation_language": "zh-CN",
  "project_types": ["service", "cli"],
  "problem": "用户或运营者面临的问题",
  "target_users": ["目标用户"],
  "goals": [
    {
      "id": "G1",
      "description": "可执行目标",
      "success_criteria": ["可测量验收条件"]
    }
  ],
  "scope": {
    "in": ["本期范围"],
    "out": ["明确不做"]
  },
  "stack": {
    "languages": [],
    "runtimes": [],
    "frameworks": [],
    "package_manager": null,
    "evidence": []
  },
  "architecture": {
    "style": "pending",
    "modules": [],
    "external_dependencies": [],
    "pending_decisions": []
  },
  "quality": {
    "commands": {
      "setup": null,
      "dev": null,
      "test": null,
      "lint": null,
      "typecheck": null,
      "build": null
    },
    "testing_strategy": "pending",
    "test_seams": [],
    "ci_required": [],
    "non_functional_requirements": [],
    "definition_of_done": []
  },
  "deliverables": [],
  "constraints": [],
  "milestones": [],
  "risks": []
}
```

Every goal requires a non-empty `success_criteria` list. A command may be a string or `null`; never insert a guessed command.

## Optional initialization controls

```json
{
  "documentation": {
    "reports": false,
    "presentations": false,
    "assets": false,
    "deliverables": false
  },
  "agent_instructions": {
    "create_agents_md": true
  },
  "scaffold": {
    "directories": ["src", "tests"],
    "planned_commands": [
      {
        "command": "example-generator ...",
        "purpose": "待用户另行批准的框架脚手架",
        "status": "proposed"
      }
    ]
  },
  "external_operations": {
    "web_research_approved": false,
    "issue_tracker_sync": "disabled",
    "remote_repository": "disabled"
  },
  "assumptions": [],
  "open_questions": []
}
```

`scaffold.planned_commands` is documentation only. The initializer must never execute it.

## Validation rules

- `schema_version` must equal `1`.
- `project_slug` must match `^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$`.
- `project_types` must be a non-empty unique subset of `application`, `service`, `library`, `cli`, `automation`, `data`, `infrastructure`, and `monorepo`.
- `problem`, `summary`, `goals`, and `scope` must be explicit. Unknown details use `pending` or `null`, not invented content.
- Each scaffold directory must be a normalized relative POSIX path. Absolute paths, empty segments, `.`, and `..` are forbidden.
- Planned commands must have `status: proposed`; apply and Git approval never authorize them.
- Existing files always win. The initializer preserves them byte-for-byte.
- `documentation` booleans control optional directories. Empty optional directories are not created otherwise.
- Package/module naming follows the chosen ecosystem and is not inferred from `project_slug`.

