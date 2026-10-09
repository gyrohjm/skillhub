# EPC 与 Tc 分析门

本参考用于 QE EPC/Tc 输出的完成判定、数值提取和下一步分流。它不把
普通声子 DOS 当作电子–声子谱，也不直接修改输入或提交重算。

## 先判定数据是否足够

| 输入证据 | 分析结论 |
|---|---|
| 完整且匹配的 `α²F(ω)`，`λ`/`ω_log` 可复核 | 可进入 Allen–Dynes 或标量 Eliashberg Tc 后处理 |
| 只有普通声子频率、`dyn*` 或 phonon DOS | 只能分析动力学/声子基线；Tc 为 `inconclusive` |
| 只有部分 q 点、空/截断 `a2Fsave` 或不完整 `a2F.dos*` | EPC 任务 `failed`/`inconclusive`；保留诊断，不释放 Tc |
| 标量 `α²F(ω)` 已完成 | 可报告标量 Tc；不能据此宣称完成各向异性 Eliashberg |
| 有 EPW/Wannier 的 k/q 分辨矩阵元和各向异性求解输出 | 按独立各向异性门分析，并与标量基线分开报告 |

`workflow.json` 完成、Slurm 成功、QE 正常终止、q 点覆盖和关键文件非空
必须同时满足。任何一个缺失都只能是 `inconclusive`。

## 数值产品

原始 QE 输出必须留在对应执行叶，例如：

```text
calculations/<composition>/<structure>/p4_epc_tc/
├── README.md
├── workflow.json
├── prep/
├── q_inputs/
├── post/
├── *.out
├── a2F.dos*
├── lambda
└── tmp/                         # 原始运行状态，不复制到 analysis/
```

分析产物统一写到结构级 `analysis/`，而不是 task-local 或平行的
`raw_data/`：

```text
calculations/<composition>/<structure>/analysis/
├── README.md
├── plot_data/
│   ├── epc_alpha2f.dat
│   ├── epc_lambda.dat
│   └── tc_table.dat
├── figures/
└── reports/
    ├── epc_tc.md
    └── design_change_request.json   # 仅在需要设计变更时
```

`.dat` 只引用源 task 的原始文件；不要把未改变的 `a2F.dos*`、`dyn*` 或
`*.save` 复制到 `analysis/`。每个可执行 leaf 仍只保留一个
`README.md` 和一个 `workflow.json`，分析报告更新源 leaf 的结果引用，
但不另建平行状态 JSON。

在任务的 `analysis/data/` 中保留（旧项目继续使用已有路径）可再生成的文本数据，并在
头部写明引擎、源文件、单位、列、转换和解析器，例如：

```text
# dftplot_dat_version = 1
# engine = quantum-espresso
# source = <task-relative>:a2F.dos1,lambda
# units = frequency:<source-unit> alpha2F:<source-unit>
# columns = frequency alpha2F
```

至少记录：

- `α²F(ω)` 及其频率网格、q 点覆盖和展宽；
- 由谱积分得到的 `λ`、`ω_log`，并与 QE 输出的值交叉核对；
- Allen–Dynes 与标量 Eliashberg 的 Tc（明确 `μ*`，例如 `0.10` 和 `0.13`）；
- k/q 网格、`sigma`/`degauss`、频率截断和代码版本带来的不确定性。

Tc 报告必须说明是 Allen–Dynes 估计还是数值 Eliashberg 解；不能只给一个
没有 `μ*` 和输入谱的温度数字。`α²F`、`λ` 或 `ω_log` 为非有限、明显截断
或 q 点不全时，不生成正式 Tc 结论。

## 推荐的分析顺序

```text
完成门
  -> α²F/λ/ω_log 提取与单位核对
  -> 谱积分和独立一致性检查
  -> μ* 扫描的 AD / 标量 Eliashberg
  -> 与普通声子基线比较
  -> supported / falsified / inconclusive + 下一步
```

普通声子基线主要用于检查频率、虚频和谱形是否合理；它不能单独决定
EPC 强弱。至少对电子 k 网格、EPC q 网格和展宽做有界收敛检查，并在报告
中区分数值不确定性与模型不确定性（例如 `μ*`）。

## 各向异性分流

各向异性 Eliashberg 需要费米面分辨的电子–声子矩阵元、电子能量和声子
模信息，通常来自 Wannier/EPW 插值及密 k/q 网格。普通 QE `α²F(ω)`、
`lambda` 或 phonon DOS 只能支撑标量模型，不能直接输入为各向异性矩阵。
若这些数据不存在，生成一个指向 `dft-design` 的 design-change request，
不要把标量 Tc 改名为各向异性 Tc。

## 失败证据

对 `a2Fsave` EOF、缺失 q 点、`JOB DONE` 缺失或 QE fatal error，分别引用
调度器、QE 输出、输入/依赖和文件门证据，使用既有失败分类。报告中写明
`submission_authorized: false`；重算参数、并行策略或 EPW 范围交给
`dft-design` 与 `dft-workflow`。

参考：[QE PHonon 用户指南](https://www.quantum-espresso.org/Doc/ph_user_guide/node10.html)。
