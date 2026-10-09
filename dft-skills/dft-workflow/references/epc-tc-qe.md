# QE EPC/Tc 工作流

本参考只处理已获科学设计批准的 Quantum ESPRESSO EPC/Tc 任务。它补充
`backend-qe.md`，不替代设计审批、资源预检或提交审查。

## 路由规则

先检查上游数据，再决定是否生成新任务：

1. 若已有完整、匹配且可验证的 `α²F(ω)`、`λ` 和 `ω_log`，创建后处理叶；
   不为“求 Tc”重复运行 `ph.x`。
2. 若只有普通 SCF 或普通声子输出，准备 EPC-enabled 的 QE 阶段。普通
   `dyn*`、声子 DOS 或 `matdyn` 频率不能作为 EPC 数据替代品。
3. 若已有匹配的密网格 SCF/NSCF 和非空 `*.a2Fsave`，可复用它；仍需完成
   所有 EPC q 点、力常数和 `α²F` 后处理。
4. 若走 `electron_phonon='interpolated'` 且 `a2Fsave` 缺失或损坏，准备
   新的密 k 网格 `pw.x` SCF/NSCF，并启用 `la2f = .true.`。不要把缺失的
   SCF 中间文件当成 `ph.x` 的并行问题，也不要只修改 `matdyn.x`。

## 阶段与文件门

典型链为：

```text
兼容 SCF
  -> 密 k 网格 pw.x SCF/NSCF（interpolated 路线需要 la2f=.true.）
  -> ph.x EPC q 点（electron_phonon='interpolated'）
  -> q2r.x
  -> matdyn.x（需要插值 EPC 时启用 la2F=.true.）
  -> dft-analysis 的 Tc 后处理
```

每一阶段都要在叶 README 和 `workflow.json` 中记录来源、版本、输入哈希
和输出门：

- 上游电子阶段：正常终止；`data-file-schema.xml` 非空；若走
  `interpolated`，匹配的 `a2Fsave` 非空且网格覆盖后续 k 与 k+q 点；
- EPC q 阶段：所有批准的不可约 q 点均完成；每个 `dyn`/响应文件非空；
  输出没有 fatal error；
- `q2r`/`matdyn`：正常终止；力常数、频率/模式、`α²F` 和 `lambda` 文件
  均通过非空与数值有限性检查；
- Tc 阶段：只记录为后处理结果，不把后处理脚本的退出码当成 EPC 物理
  收敛。

## 推荐文件结构

新布局应落在动态发现的 workspace `calculations/` 根下。共享 `a2Fsave`
或 `tmp` 的 EPC 链默认使用一个 orchestrator leaf，避免把同一累积状态
误登记成多个独立任务：

```text
calculations/<composition>/<structure>/
├── p2_scf/
│   ├── README.md
│   ├── workflow.json
│   ├── scf.in
│   ├── job.sh
│   └── tmp/<prefix>.save/          # 原始 SCF 数据，按批准关系复用
├── p3_phonon/                      # 可选普通声子基线
│   ├── README.md
│   ├── workflow.json
│   ├── ph.in
│   ├── q2r.in
│   ├── matdyn.in
│   ├── job.sh
│   └── tmp/
├── p4_epc_tc/                      # 一个共享 a2Fsave 的执行叶
│   ├── README.md
│   ├── workflow.json
│   ├── prep/                       # q-map/准备阶段输入和输出
│   ├── q_inputs/                   # ph_q01.in ... ph_qNN.in
│   ├── post/                       # q2r.in、matdyn.in、Tc 脚本
│   ├── job.sh
│   └── tmp/                        # 只允许本叶独占写入
└── analysis/
    ├── README.md
    ├── plot_data/
    ├── figures/
    └── reports/
```

结构规则：

- `p4_epc_tc` 内的 `prep/`、`q_inputs/`、`post/` 是同一 orchestrator leaf
  的内部目录，不在其中重复创建 `workflow.json`；只有真正独立提交的
  task/variant leaf 才有自己的 `README.md` 与 `workflow.json`。
- 如果 q 点必须拆成独立 leaf，则每个 q leaf 使用隔离的 `outdir`、自己的
  记录和输出；合并任务另设 leaf，并明确其输入清单和合并门。不能让多个
  leaf 同时写同一 `tmp`、`*.save` 或 `a2Fsave`。
- 大型、只读的上游 SCF 数据可以用相对符号链接复用；链接目标、相对路径、
  hash 和兼容性检查写入 `workflow.json`。可变运行目录不得作为并发共享
  链接目标。
- 原始 `*.out`、`dyn*`、`a2F.dos*`、`lambda` 和重启文件留在执行叶；
  `analysis/` 只保存可再生成的 `.dat`、图和报告，不复制一份 raw data。
- `p3_phonon` 是 `p2_scf` 的验证分支，`p4_epc_tc` 是 EPC/Tc 分支；不应
  通过目录排序暗示 p3 是 p4 的强制计算依赖。现有 legacy 目录不自动移动。

## 并行和复用不变量

- 普通声子 q 点若只生成独立动力学矩阵，可以在隔离输出目录中并行。
- EPC q 点是否能并行取决于 QE 版本、共享 `outdir` 和 `a2Fsave` 的写入/累积
  语义。默认把共享累积文件视为串行资源；只有在每组拥有隔离的完整
  `outdir`、并且存在经过验证的合并步骤时才允许分组并行。
- 不允许多个 `ph.x` 同时写同一个 `tmp`、`*.save` 或 `a2Fsave`；这会造成
  截断、EOF、不可复现的累积结果，而不是可靠的加速。
- 复用 SCF 时必须保持 `prefix`、`outdir`、赝势、结构、占据、k/q 网格、
  展宽和编译版本兼容。符号链接可以减少复制，但不能掩盖不兼容的输入。

## 普通声子基线

独立的普通声子任务用于检查动力学稳定性、声子 DOS 和力常数质量。它是
EPC/Tc 的推荐验证分支，但不是已有完整 `α²F` 后求 Tc 的强制计算依赖，
也不能替代 EPC-enabled `ph.x`。

## 交接

工作流只负责准备、资源审查、提交、监控和完成门。完成后把原始输出交给
`dft-analysis`，由其生成 `α²F`/`λ`/`ω_log` 的可追溯数据和 Tc 报告。若
`a2Fsave` EOF、缺 q 点、文件截断或 `α²F` 不完整，标记失败/不充分并保留
证据；不要释放 Tc 结论，也不要在工作流阶段直接修改旧叶。
