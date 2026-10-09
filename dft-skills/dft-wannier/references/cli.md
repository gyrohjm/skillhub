# 可执行诊断接口

## 范围与运行环境

`scripts/wannier_audit.py` 支持 Python 3.10+，仅用标准库。无需安装原型、
Wannier90、QE 或额外 pip 包即可分析已有文件。输出使用 UTF-8。
源码在 `wannier_io.py`（文本提取）、`wannier_bands.py`（对照指标）和
`wannier_audit.py`（检查/报告/CLI）。

所有命令只读计算输入、输出和元数据，不调用引擎/调度器、不修改 workflow.json。
参数变更和执行仍由专业 Agent 与已有工作流处理。

## inspect

```text
python <skill-dir>/scripts/wannier_audit.py inspect --win <absolute-seed.win> --eig <absolute-seed.eig> --wout <absolute-seed.wout> --output-dir <new-report-directory>
```

`--win` 必需，另两个输入可省略，省略/不存在均报告证据缺口；不猜路径。
不指定 `--output-dir` 时只向 stdout 输出 JSON。

- `.win`：支持常用 `=`、`:`、空格赋值、大小写、引号外注释、D 指数、
  块结构、带空格和倒序的排除能带区间；重复排除带报错。保留投影块，
  但不推测展开后的轨道数。支持原生零迭代控制及 `conv_window=-1`。
  冲突重复参数、非有限数、坏块等不能悄悄被覆盖。
- `.eig`：按 `band_index k_index energy_ev` 读取，检查重复与完整性。
  每个 k 点必须具有预期的全部输入带；预期 k 数来自 `.win`，不能用
  实际读到的行数证明文件完整。
- `.wout`：支持常见 W90 3.x `DIS/CONV` 表及终止/收敛标志。没有证据返回
  null/UNKNOWN；`Exiting Wannier90` 本身不代表成功，原生 `Exiting.......`
  及其后诊断按致命错误处理。最后运行及最后 Final State
  独立处理；迭代数到顶和收敛状态分开。输出单位保留，不擅自将 Bohr² 当 Å²。
- 能窗：普通能量解纠缠下检查每 k 点 `n_frozen <= num_wann <= n_outer`。
  外窗缺省取有效输入本征值极值；冻结窗上下限均未给时不启用冻结窗，
  仅给 `dis_froz_min` 而不提供 `dis_froz_max` 则报错；所有
  缺省的来源在报告中标明。无解纠缠的等维子空间单独标记。
- 投影可解纠缠、k 依赖球区域、对称性相关模式不按普通能窗验收，返回 UNKNOWN。
  这不是这些功能不可用，而是本检查器尚未实现其必要证据路径。

### 排除能带约定

`num_bands` 在本工具中表示传入 Wannier90 的有效带数，不会再减一次排除数。

- 没有排除能带：默认把 `.eig` 看作有效空间，带号为 `1..num_bands`。
- 有 `exclude_bands` 且未指定空间：UNKNOWN，等待用户/Agent 核实上游接口。
- `--band-space effective`：输入已由接口处理过排除，不能再次剔除。
- `--band-space original`：输入须包含完整原始 DFT 带集合，带数是有效带数加
  唯一排除数；先验证完整集合，再剔除并报告原始→有效映射。

不支持“部分排除但未重编号”的混合空间。路径、SHA256、大小和参数行号随报告
保存；哈希只表示读取了哪些文件，不证明文件来自同一次计算。

能窗能量与 `.eig` 必须使用同一 eV 参考零点；程序不自动读取/减去费米能，
不实施能量平移。其 PASS 只是这些声明成立时的必要数值条件，不证明原始
k 点坐标、矩阵顺序、投影、自旋或数据来源兼容。

## compare

```text
python <skill-dir>/scripts/wannier_audit.py compare --reference <dft.json> --candidate <wannier.json> --target-window -1 1 --mae-threshold-mev 20 --max-threshold-mev 50 --output-dir <new-report-directory>
```

两份 JSON 都使用下面的数据形状。示例是人工构造的接口数据，不是真实材料：

```json
{
  "schema_version": 1,
  "units": "eV",
  "energy_reference": "shared-scf-fermi-reference-id",
  "system_id": "shared-structure-spin-pseudopotential-id",
  "kpoint_basis": "fractional",
  "sampling": "independent",
  "matching": "explicit_band_ids",
  "band_ids": ["band-a", "band-b"],
  "kpoints": [[0, 0, 0], [0.25, 0, 0]],
  "energies": [[-1, 1], [-0.5, 2]]
}
```

生成数据时记录真实来源。相同的 system_id/energy_reference 是外部声明，
不是本工具验证过结构、自旋和参考零点的证明。报告对此明确标记。

- 每行对应一个 k 点，每列对应一个 band_id；ID 表示已建立的物理对应关系。
  候选可换列顺序，但 ID 集合必须相同。未知交叉/简并处映射时先专业判断，
  不能凭相同整数带号就捏造对应关系。
- 两侧 k 点必须已经按同一顺序、同一倒格矢基底对齐，逐坐标容差为 1e-8。
  工具不进行周期等价点重排或近邻插值。
- 不接受非有限能量、缺列、丢带、重复 ID、不同单位或不同零点标签。
- target-window 使用参考数据的能量做掩码；候选能量移出能窗不会使该点
  被移出误差统计。没有目标样本时指标为 null，不能算作零误差。
- 报告全体/目标能区 MAE、RMSE、最大误差与逐点带号误差 CSV。
  未给出完整阈值对时 threshold_check 为 UNKNOWN。
- sampling 为 `independent`、`high_symmetry_path` 或 `training_grid`。
  只有双方声明 independent 才标记该声明成立；仍需核实真正独立于训练数据。
- `PASS_ON_SUPPLIED_DATA` 只说明所给数据满足所给阈值；不证明整个 BZ、
  费米面拓扑、轨道角色或 EPC 质量。scientifically_accepted 始终为 null。

## 报告与退出码

输出 `report.json`、`report.md`；compare 另有 `errors.csv`。
新目录以排他创建保留，已有目录报错，不覆盖既有内容。

- 退出 0：成功生成诊断报告，包括报告发现 BLOCKED、FAIL 或 UNKNOWN 的情况。
- 退出 2：命令参数、比较数据约定、报告写入或运行层面的错误。

自动消费者必须读 JSON 中 decision 和各层状态，不得用退出码 0 作为提交门。
当前没有向 dft-workflow 自动注册门判断；没有新建第二个活跃状态账本。

## 回归测试

从 SkillHub 仓库执行：

```text
python -X utf8 -m pytest -q dft-wannier/tests --basetemp .pytest-wannier -p no:cacheprovider -W error
```

pytest 仅是开发测试依赖，不是运行依赖。测试基于手工构造的正常/对抗样例及
官方格式，不是实际 VASP/QE/W90 引擎计算。发布为全自动闭环前仍需收集不同
版本真实日志、原始对照数据与安全执行测试。

格式参考：[W90 文件说明](https://wannier90.readthedocs.io/en/latest/user_guide/wannier90/files/)、
[eig 接口](https://wannier90.readthedocs.io/en/latest/user_guide/wannier90/postproc/#seednameeig-file)、
[W90 3.1.0 局域化输出源码](https://github.com/wannier-developers/wannier90/blob/v3.1.0/src/wannierise.F90)、
[参数与区间解析](https://github.com/wannier-developers/wannier90/blob/v3.1.0/src/parameters.F90)、
[原生退出格式](https://github.com/wannier-developers/wannier90/blob/v3.1.0/src/io.F90)。
