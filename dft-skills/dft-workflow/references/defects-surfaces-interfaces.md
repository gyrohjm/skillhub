# Defects, Surfaces, And Interfaces Workflow

本文件只约束 `dft-workflow` 的运行期行为。科学问题、对照、收敛、
`chemical_potential`、`charge_state`、`dipole_correction`、
`finite_size_correction` 和停止条件必须先由 `dft-design` 审批。

## Task Mapping

把 domain task 映射到项目自己的 `pN[_name]` 顺序，并在结构 README 中记录；
不要使用固定的 `structure/energy/charge` 分类树。例如：

```text
bulk_reference      -> p0_bulk_ref/
defect_relax        -> p1_relax/defect_q0/
surface_relax       -> p1_relax/surface_a/
static_energy       -> p2_scf/
charge_density      -> p3_charge/
locpot              -> p4_locpot/
bader               -> p5_bader/
```

这里只是命名示例；approved design 和项目 README 决定真实编号。

`defect_relax`、`surface_relax`、`adsorption_relax`、`interface_relax` 使用
relax-like 输入规则，必须保留 `POSCAR-ini`。`bulk_reference`、`static_energy`、
`charge_density`、`locpot`、`bader` 使用 static-like 输入规则；除
`bulk_reference` 外，从 `workflow.json` 指定的已接受 relax leaf 获取结构；
不要依赖固定路径或最新时间戳。`charge_density`、`locpot` 和 `bader` 需要复用
SCF `CHGCAR` 或 `WAVECAR` 时，使用 symlink，并记录相对目标。

## Required Review Context

提交前 review 必须显示：

- `domain_pack`
- matrix purpose、variables、fixed parameters
- reference cases 和 control IDs
- structure source、POTCAR components、关键 INCAR/KPOINTS 参数
- `chemical_potential`
- `dipole_correction`
- `charge_state`
- `finite_size_correction`

这些字段用于发现 reference/variant 不可比、slab dipole 漏设、charged defect
correction 未定义等问题。review 只负责阻塞风险，不负责重新设计科学矩阵。

## Handoff Rules

- formation energy、surface energy、adsorption energy、interface adhesion/work
  of separation、work function、Bader charge、charge density difference 交给
  `dft-analysis`。
- 仅在用户明确要求 transfer/archive 时，把 reference case、variant case、
  design approval、analysis products 交给 `dft-work-manager`。
- 如果需要新增 coverage、charge state、termination 或 interface registry，
  写 `design_change_request.json`，回到 `dft-design` 增加 revision。
