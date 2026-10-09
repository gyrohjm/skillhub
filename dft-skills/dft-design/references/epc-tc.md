# EPC 与 Tc 设计契约

在设计超导电子–声子耦合（EPC）和临界温度 `Tc` 任务时，先区分
“生成 EPC 数据”和“用已有 EPC 数据求 Tc”。普通声子频率或声子 DOS
本身不能替代电子–声子矩阵元。

## 先做输入判定

| 已有证据 | 允许的下一步 |
|---|---|
| 已有与当前结构、SCF、k/q 网格和展宽匹配的完整 `α²F(ω)`，并且 `λ`、`ω_log` 可复核 | 直接做 Allen–Dynes 或标量 Eliashberg 后处理；不再运行 `ph.x` |
| 只有普通 SCF，或只有普通声子/声子 DOS | 先设计 EPC-enabled DFPT；这些文件不能直接给出 Tc |
| 有 SCF 且有匹配、非空的 QE `*.a2Fsave`，但没有完整 q 点 EPC 输出 | 复用该 SCF 中间文件，继续完成 EPC q 网格和 `α²F(ω)` |
| 目标是各向异性 Eliashberg | 设计 EPW/Wannier 或等价的 k/q 分辨电子–声子矩阵元流程；标量 `α²F` 不足 |

文件存在不等于可以复用。必须核对 `prefix`、`outdir`、赝势、结构、
电子占据、k/q 网格、展宽和 QE 版本；任何一项不匹配都应创建新的兼容
上游任务，而不是在后处理阶段修补。

## 推荐阶段图

```text
兼容 SCF
  -> （QE interpolated 路线）密 k 网格 SCF/NSCF + pw.x la2f=.true.
  -> ph.x：每个 q 的 DFPT + electron_phonon='interpolated'
  -> q2r.x / matdyn.x：力常数、声子谱和 α²F
  -> 标量 Tc 后处理（μ* 扫描、Allen–Dynes / 标量 Eliashberg）
```

## 任务树与分支关系

新任务使用项目的 composition-first 计算树，不在结构目录外另建 EPC/Tc
数据树：

```text
calculations/<composition>/<structure>/
├── p2_scf/                 # 兼容的电子 SCF 来源
├── p3_phonon/              # 普通声子稳定性/基线，可选验证分支
├── p4_epc_tc/              # EPC q 网格、q2r/matdyn 和 Tc 后处理
└── analysis/               # 只放派生数据、图和报告
```

`p4_epc_tc` 从 `p2_scf` 分支，不把 `p3_phonon` 伪装成 EPC 前置任务。
每个可执行 task/variant leaf 只保留一个 `README.md` 和一个
`workflow.json`；q 点分组、输入模板和后处理脚本是否拆成子目录，应在
设计矩阵中明确其是否为独立 executable leaf。既有 legacy 目录不因本规范
自动移动或重命名。

普通声子基线（完整 q 网格、声子 DOS、虚频检查）是强烈推荐的独立
验证分支，但不是“已有完整 EPC 数据后再求 Tc”的计算前置条件。它不能
替代 EPC q 计算，也不能因为声子基线完成就宣称 Tc 已经可得。

对于 QE `electron_phonon='interpolated'` 路线，密 k 网格的 `pw.x`
SCF 或 NSCF 必须按该版本文档启用 `la2f = .true.`，并覆盖后续 EPC 所需
的全部 k 与 k+q 点；通常使用未移位网格。普通 SCF 没有生成匹配的
`a2Fsave` 时，仅修改 `ph.x` 或 `matdyn.x` 不能补救，必须补做兼容的
密网格 SCF/NSCF。`matdyn.x` 中的 `la2F = .true.` 是后续插值电子–声子
系数的开关，两者不是同一个阶段的输入。

## 设计时必须固定的量

- 上游 SCF/密网格 SCF（或 NSCF）的唯一来源、`prefix/outdir` 和复用文件；
- EPC q 网格、电子 k 网格、`electron_phonon` 路线、`el_ph_sigma`/
  `el_ph_nsigma`、`tr2_ph` 和是否使用 2D 边界条件；
- `q2r.x`、`matdyn.x`、`la2F` 及频率网格设置；
- `μ*` 的主值和敏感性值，例如 `0.10` 与 `0.13`，以及 Tc 的报告方法；
- q/k/展宽收敛量、`α²F` 有限性、`λ` 独立积分一致性和声子稳定性门槛；
- 标量结果与各向异性结果的证据等级，不把两者混写成同一个 Tc。
- `p2_scf -> p4_epc_tc` 的直接依赖、`p3_phonon` 的验证属性、每个 task
  leaf 的 `README.md`/`workflow.json` 位置，以及 `analysis/` 的派生数据
  位置。

## 设计边界

`Tc` 后处理可以是零次新的 `ph.x`，但只有在 `α²F(ω)` 已完整且可追溯
时才成立。若目标是从 SCF 开始得到 Tc，EPC-enabled `ph.x` 仍是必要的
声子响应计算。各向异性 Eliashberg 还需要比普通 DFPT/`α²F` 更丰富的
矩阵元数据，默认应作为 EPC 标量基线通过后的独立矩阵项。

参考：

- [QE 7.0 PHonon 用户指南](https://www.quantum-espresso.org/wp-content/uploads/2022/03/ph_user_guide.pdf)
- [QE `ph.x` 输入说明](https://www.quantum-espresso.org/Doc/INPUT_PH.html)
- [QE `matdyn.x` 输入说明](https://www.quantum-espresso.org/Doc/INPUT_MATDYN.html)
