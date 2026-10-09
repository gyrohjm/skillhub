# Defects, Surfaces, And Interfaces

面向人的计划正文使用中文；字段名、路径名、DFT engine 参数和 JSON key 保持英文。
这个 domain pack 只负责科学设计，不生成 engine 输入、不提交、不分析、不归档。

## 适用范围

在 `calculation_design.json` 中设置：

```json
{
  "domain_pack": "defects-surfaces-interfaces",
  "domain_metadata": {}
}
```

适用于：

- `point_defect`、`vacancy`、`substitution`
- `slab`、`surface`
- `adsorption`
- `interface`

不在首版范围内：NEB、AIMD、Wannier、LOBSTER 专项配方、完整 phonon 热力学。

## 必须锁定的生产参数

进入 production 审批前，在 `domain_metadata.production_lock` 中明确：

```json
{
  "supercell_size": "2x2x2",
  "slab_size": "4 layers",
  "vacuum": "18 Angstrom",
  "k_mesh": "3x3x1",
  "ENCUT": 520,
  "smearing": "ISMEAR=0 SIGMA=0.05",
  "dipole_correction": "LDIPOL=.TRUE. IDIPOL=3",
  "charge_state": 0,
  "chemical_potential": "Si-rich from bulk Si reference",
  "finite_size_correction": "not needed for neutral defect",
  "reference_structure": "bulk_reference M_bulk"
}
```

如果某项物理上不适用，写明 `not_applicable` 和原因；不要留空。

## 对照和参考

必须定义可比较的 reference case：

- 缺陷：无缺陷 bulk/supercell reference，必要时包括不同 charge state 的修正方案。
- 表面：相同 functional、ENCUT、smearing、k-mesh 策略下的 bulk reference 和 clean slab。
- 吸附：clean slab、isolated adsorbate 或用户批准的化学势参考。
- 界面：两个分离表面或 bulk references，说明应变分配和界面面积。

`domain_metadata.reference_cases` 推荐使用 object：

```json
{
  "bulk_reference": "M_bulk",
  "clean_slab": "M_slab_clean",
  "isolated_adsorbate": "M_adsorbate"
}
```

## 变量矩阵

每个 matrix entry 只能改变能解释科学问题的变量，例如：

- `defect_site`、`defect_type`、`charge_state`
- `surface_miller_index`、`termination`
- `adsorbate`、`coverage`、`adsorption_site`
- `interface_pair`、`strain_state`、`registry`

把 `ENCUT`、`k_mesh`、`vacuum`、`slab_size`、`supercell_size` 作为收敛或固定参数，
不要和物理变量混在一起。

## 收敛与停止条件

生产前至少检查：

- `ENCUT`
- `k_mesh`
- `smearing`
- defect/supercell 任务的 `supercell_size`
- surface/adsorption/interface 任务的 `slab_size` 和 `vacuum`

收敛目标必须绑定到科学 observable，例如 formation energy、surface energy、
adsorption energy、work function、interface adhesion，而不是只看 total energy。

停止条件应包含：

- reference/control 失败时停止生产解释。
- 关键能量差的不确定度低于阈值时停止扩展矩阵。
- charge correction、dipole correction 或 chemical potential 无法确定时停止生产审批。

## Workflow 交接

把可执行 stage 写入 matrix `stages`：

```text
bulk_reference
defect_relax
surface_relax
adsorption_relax
interface_relax
static_energy
charge_density
locpot
bader
```

`dft-workflow` 只准备这些 stage 的 engine 输入和提交 review。formation energy、
surface energy、adsorption energy、interface adhesion、work function、Bader
charge、charge density difference 的解释交给 `dft-analysis`。
