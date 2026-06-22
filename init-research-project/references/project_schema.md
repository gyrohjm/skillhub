# 项目规范 Schema

写入 UTF-8 JSON。JSON key、枚举、slug 和专业参数名保持英文；面向人的字段值默认
使用中文，不重复提供英文翻译。

## 必填字段

```json
{
  "project_name": "中文项目名称",
  "project_slug": "english_lowercase_snake_case",
  "mode": "generic | experimental | computational | hybrid",
  "domain": "研究领域",
  "summary": "一句话项目目标",
  "research_questions": ["Q1 ..."],
  "hypotheses": [
    {
      "id": "H1",
      "statement": "可检验陈述",
      "falsification": "能够否证该假设的观察结果"
    }
  ],
  "objectives": [
    {
      "id": "O1",
      "description": "可执行目标",
      "success_criteria": "可测量的验收标准"
    }
  ]
}
```

## 可选字段

```json
{
  "background": "当前科学背景和项目上下文",
  "deliverables": ["论文图", "验证后的数据集"],
  "constraints": ["仪器时间", "集群额度"],
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
        "incar_inheritance": "SCF/band/DOS 继承已审核的 relax 电子参数，除非在此处 override",
        "stage_overrides": {
          "scf": {"IBRION": -1, "NSW": 0, "LWAVE": ".TRUE.", "LCHARG": ".TRUE."}
        },
        "kpoints_policy": "生产前明确 relax/scf/dos mesh 与 band path",
        "potcar_labels": {"Si": "Si", "C": "C"},
        "cluster_profile": "nmg | phoenix | phoenix-gpu-a100 | phoenix-gpu-g3 | generic",
        "restart_link_policy": "下游任务通过 ln -s 复用 SCF CHGCAR/WAVECAR"
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
  "terminology": {"term": "定义"}
}
```

## 校验规则

- `project_slug` 必须匹配 `^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$`。
- 不得机械音译中文项目名；提出简短英文 slug 并请用户确认。
- `mode` 控制可选实验和计算目录。
- `systems` 可选。提供时，`system_slug` 和每个 `case_slug` 必须使用英文
  `lowercase_snake_case`；初始化器会预创建
  `raw_data/calculations/<system_slug>/<case_slug>/` 和
  `formal_data/structures/<system_slug>/`。
- 未提供 `systems` 时只创建 `raw_data/calculations/`，后续按同一命名规则新增体系。
- 每个 hypothesis 必须有 falsification condition。
- 每个 objective 必须有可测量的 success criteria。
- VASP 项目生产前应填写 `computation_plan.vasp_workflow_envelope`。初始化器会将其
  转为 `docs/plans/calculation_design.json` 草案，再由 `computation-design` 补全
  hypothesis、observable、control、收敛/验证、evidence、误差和批准 scope。
- 未知内容使用“待补充”明确标记，不得编造。
