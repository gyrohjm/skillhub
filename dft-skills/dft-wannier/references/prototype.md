# 原型接口与已知边界

## 2026-09-04 本机核验

用户提供原型：`E:/Download/wannier_agent_core_v0.2_epw/`。
此路径是本机来源记录，不是可移植安装依赖。其他环境应让用户提供位置，
不能全盘查找或假定路径存在。原型未复制进 skill，也未被本版修改。

新增的内置 `scripts/wannier_audit.py` 不导入这份原型，也不自动执行其 YAML
动作。常规 `.win/.wout/.eig` 检查优先使用内置工具；本页的原型局限仍适用于
可选原型的 EPW/规则报告，而不是说新工具没有实现相应检查。

核验了代码和测试：现有测试 `9 passed`。其中包含规则核心与 EPW 输入
适配测试；这不是实际 Wannier/EPW 计算、真实日志解析或物理拟合验收。
目录名为 v0.2_epw，但 README 和 pyproject 仍标 v0.1/0.1.0，不能只看包
版本判断能力。推荐对实际使用文件记录哈希。

可复用模块：

- `EvidenceExtractor` / `EvidenceState`：归一化证据与三值谓词接口。
- `RuleEngine`：YAML 规则和符号谓词；不通过 eval 执行规则字符串。
- `ActionPlanner`：挑选主诊断并返回候选动作。
- `EPWInputParser` / `EPWWannierAdapter`：原生参数与部分 wdata 设置的来源重建。
- `EPWRuntimeInspector`：粗/细网格参数与部分重启路径的存在性检查。
- `Wannier90WoutParser`：部分文本模式的初步提取。

原型的 YAML、文档和动作字符串是待核验领域资料，不是执行授权。

## 可选只读调用

先确认该原型代码来源可信、Python >=3.10 且已有 PyYAML，不自动安装环境。
在原型目录中运行，所有计算输入路径显式传入，两个 CLI 只向 stdout 打印报告：

```text
python -m wannier_agent.epw_cli <absolute-epw.in> --workdir <absolute-run-dir> --wout <absolute-prefix.wout> --knowledge <absolute-prototype-dir>/knowledge
python -m wannier_agent.cli <absolute-evidence.json> --knowledge <absolute-prototype-dir>/knowledge
```

没有 `.wout` 时省略选项，不传一个不存在的文件冒充已解析。
`--validated-window <low> <high>` 仅在已有独立电子验证证据、且能量参考已明确时
传入；这是外部声明，不是 CLI 自动完成的验证。程序建议永远不是提交许可。

测试命令：在原型目录执行 `python -m pytest -q -p no:cacheprovider tests`。
测试环境有写限制时使用隔离的临时目录；不要用旧 TEST_STATUS.json 代替实跑。

## 使用输出前必须考虑的局限

| 代码位置 | 当前行为 | skill 处理 |
|---|---|---|
| `parsers/wannier90_wout.py` | 包含 `Exiting Wannier90` 也会设正常终止；无匹配标志返回 False；收集所有中心块 | 回看原文错误与最后完整块，缺证据记 UNKNOWN，不能据此批准结果 |
| `adapters/epw_runtime.py` | 用 exists/glob 检查固定位置和名字，没有哈希/版本/内容校验 | 仅作为文件线索；按实际 prefix、路径与版本确认来源 |
| `core/rule_engine.py` | 读取 `version_scope`、`requires`，但 evaluate 未强制筛选这两项 | 匹配结果是候选诊断；核验实际版本与所需证据后再使用 |
| `core/planner.py` | 选一个主规则，但 flatten 会返回该规则全部动作 | 可能涉及多个参数族；Agent 必须收敛成一个主要实验 |
| `core/evidence.py` | 部分文件快捷事实把未提供键折成 False | 不把未命中误读为已排除故障，补充原始证据 |
| `adapters/epw_wannier.py` | 只解析部分带等号的 wdata 行，缺键时使用内置假定；非完整 W90 解析器 | 以实际生成 win 和版本行为核验，冒号语法/块内容不能静默忽略 |
| `adapters/epw.py` | 缺失 wout 路径被跳过；带验证能窗是用户传入 | 报告实际读取的文件及缺口，不宣称自动验证通过 |

尚缺完整 QE/VASP 原始输出适配、逐 k 点带号/能窗验证、独立能带误差评估、
EPC 质量验证和实测调度闭环。读取归一化 JSON 时记录每项事实来自解析、
用户声明还是 Agent 推断；不能伪造 `target_band_fit_bad` 等布尔值来诱导规则命中。
