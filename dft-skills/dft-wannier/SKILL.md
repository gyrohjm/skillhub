---
name: dft-wannier
description: "Assist Wannier90 fitting with read-only win/wout/eig parsing, per-k-point energy-window checks, explicit-band-mapping error metrics, and evidence-based projection/disentanglement/localization advice. Use for poor fits, nonconvergence, unexpected centres/spreads, or assessing a Wannier electronic model for EPW. Does not own general DFT design, scheduler submission, or EPC/Tc scientific acceptance."
---

# DFT Wannier

For DFT project work, read the applicable AGENTS.md and project storage_role; MEMORY.md belongs to the local planning side.
Before saving documents or handing off decisions, follow
[project records](../dft-contracts/references/project-records.md) for fixed paths,
names and evidence-linked memory. Environment details stay in private local profiles.

For paired local/cluster projects, read [paired projects](../dft-contracts/references/paired-projects.md) before preparing inputs, writing analysis or transferring results.



帮助用户得到适合目标物理问题的 Wannier 子空间和插值模型，而不仅是让
Wannier90 正常退出或 spread 变小。先程序提取证据、检查确定性约束；程序
无法判断的部分由专业 Agent 推理，并明确不确定性。

## 能力与边界

本版提供可执行的只读诊断和能带比较工具，不是自动搜索/提交平台。Python
3.10+ 标准库即可运行，不依赖原型目录或第三方 Python 包。若要执行计算迭代，
仍需明确执行请求、可用引擎及有限迭代范围。没有真实能带对照不能宣布拟合成功。

- 独立 Wannier90：内置 `.win/.wout/.eig` 提取和普通能量解纠缠容量检查。
  `.amn/.mmn` 内容、原始 VASP/QE 输出和轨道投影仍需补充解析或专业核验。
- EPW：内置工具可检查实际生成的 `.win/.eig/.wout`；EPW 原生参数、`proj(i)`、
  `wdata(i)` 的端到端一致性仍需专业核验或可选原型辅助。
- 可选原型 `wannier_agent_core_v0.2_epw` 用作候选诊断来源。使用前读
  [原型接口与限制](references/prototype.md)。没有原型时仍可进行有证据的人工
  检查，不伪造程序结果。
- 具体拟合/验收时读 [拟合闭环](references/fitting-loop.md)。

## 内置工具

运行前读 [CLI 接口与数据约定](references/cli.md)，路径从本 skill 的位置解析：

```text
python <skill-dir>/scripts/wannier_audit.py inspect --win <seed.win> --eig <seed.eig> --wout <seed.wout>
python <skill-dir>/scripts/wannier_audit.py compare --reference <dft.json> --candidate <wannier.json> --target-window -1 1 --mae-threshold-mev 20 --max-threshold-mev 50
```

阈值数字仅展示语法，不是推荐的通用验收标准。默认只输出 UTF-8 JSON；
`--output-dir <new-directory>` 可新建 Markdown/JSON 报告及比较误差 CSV。
已有目录拒绝覆盖。命令成功退出仅表示报告生成，不表示模型验收或允许提交。

有 `exclude_bands` 时先核实 `.eig` 带号空间，再给 `--band-space effective`
或 `original`，不能猜测或重复剔除。特殊解纠缠模式返回 UNKNOWN，不能用普通
能窗 PASS 替代其真实约束。比较器只接受已显式对齐的数据，不执行能量平移、
近邻 k 点匹配或自动丢带。

## 工作入口

1. 确定请求属于只读诊断、设计初始模型、比较候选，还是执行有界迭代。
   只读请求不授权改输入、重算、提交或删除重启数据。
2. 从现有设计和输入提取：目标物性、拟合能区及能量零点、DFT/W90/EPW
   版本、结构和自旋模式、目标轨道/模型维度、源均匀 k 网格、误差目标。
   能从文件获得的不要反复问用户；缺失时列最小补充证据。
3. 读取当前磁盘输入并与上次尝试快照做语义比较。用户修改优先于旧计划：
   普通变更更新方案并记录来源，不还原旧值、不因哈希变化再次要求批准。
   未能识别的差异先由 Agent 核验，不自动升级为重大冲突。
4. 执行可证明的约束检查，再诊断基组、能窗、解纠缠、局域化或上游数据问题。
   每一项标明证据文件/位置、参数来源、已知/未知和受影响任务。
5. 给出下一次最小实验：一个主要参数族、精确差异、物理理由、复用/重建
   的上游数据、验收指标及停止条件。若一个原型规则返回多个参数族，不能
   直接整体执行；选择最小实验，必要的联动约束一并解释。
6. 比较新旧模型使用同一参考集、能量约定和目标能区。原型未命中规则或
   `stop=false` 不代表通过；证据不全时报告待补证据。

## 迭代权限与结果保护

- 首次用户审查目标参数及允许探索范围后，范围内调参和后续任务提交不重复
  请求审核。若没有约定迭代上限，先给下一次候选，不启动无限搜索。
- 只有改变目标物理模型、超出授权范围、需要破坏结果或出现不可调和输入
  冲突时才提醒用户；仅暂停受影响分支。`num_wann`/投影的变化是否重大取决
  于已批准的模型探索范围，不把所有拟合改参都当重大冲突。
- 技术故障：在同一任务叶修复，先保存将被替换的输入、输出、日志和快照。
- 计算正常完成但拟合不合格：保留源结果，新建非覆盖的 `rerun_NNN` 候选；
  记录 `derived_from`。选回旧候选是选择引用，不是覆盖文件的“rollback”。
- 运行中的输入快照不可变。用户新改动只用于下一次尝试；改动后重新判断
  旧 `.amn/.mmn/.eig`、旋转矩阵和 EPW 重启数据是否仍适用。

## 与 DFT 系列协作

- 本 skill 提供 Wannier 科学诊断、参数候选和验收证据。
- 如果项目使用 `dft-workflow`，由它负责目录、依赖、唯一活跃 `workflow.json`、
  原地重试/重算分支、提交回执和资源缓存；提交模板、资源分配与启动规范由
  可用的 `dft-submit` skill 统一提供。本 skill 不另建状态机、不重复资源检查，
  不假定新 Wannier 字段已经接入其 schema。
- 已知计算和验证任务应在首次设计时准备好目录及可确定输入；依赖未生成的
  上游数据用明确 recipe 表达。探索性候选通过既有分支机制建立，不编造结果。
- 不依赖系列 skills 时可独立输出诊断与候选，但不能声称完成调度集成。
- EPC 或 Tc 的物理验收交给对应分析流程，电子插值验收不能替代它。

## 输出

默认给一份简明拟合报告。需要落盘时，在项目输出目录下新建不覆盖的
`wannier-report-<unique-id>.md`，包含：

1. 本次模型/尝试身份、输入路径与哈希、版本和用户覆盖参数；
2. 数值收敛、电子拟合、目标物理三个层次的结论及证据缺口；
3. DFT 对照指标/图表，注明参考集、单位、能量零点及能带映射；
4. 下一步参数差异、理由、依赖重建范围及验证/停止条件。

确有用途时附可追溯的提取证据 JSON 和误差 CSV；它们是结果快照，不是另一个
活跃工作流账本。不要生成没有数据支撑的零误差或占位“通过”。
