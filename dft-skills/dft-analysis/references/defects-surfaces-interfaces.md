# Defects, Surfaces, And Interfaces Analysis

本文件约束分析输出，不负责提交、归档或新增生产任务。所有 `.dat` 必须先通过
`dftplot_dat.py validate`，再把生命周期事件交给 `dft-work-manager` 写入结构级
日志；数据本身不由 manager 提取或解释。

## Output Families

首版支持这些结果族：

```text
formation_energy.dat
surface_energy.dat
adsorption_energy.dat
interface_adhesion.dat
work_function.dat
bader_charge.dat
charge_density_difference.dat
```

每个结果都需要中文 Markdown 报告，报告中保留字段名：

- `analysis_type`
- `hypothesis_verdict`: `supported`、`falsified`、`inconclusive`
- reference case 和 variant case
- 使用的 total energy、面积、chemical potential、charge correction 或 dipole
  correction 假设
- `.dat` 路径、figure 路径、源 VASP 输出路径

## Decision Boundary

如果 reference/control 不完整、收敛误差覆盖目标效应、chemical potential 未锁定、
charged defect correction 不明确，报告必须给出 `inconclusive`，并写
`analysis/reports/design_change_request.json`。不要把未审查的新计算直接交给
`dft-workflow`。

## Helper

`scripts/domain_dsi.py` 可把已验证的标量或表格结果写成标准 `.dat` 和中文报告。
它不从 OUTCAR 自动推导科学公式；公式和引用关系必须来自已批准设计或用户确认。
