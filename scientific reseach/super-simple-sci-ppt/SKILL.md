---
name: super-simple-sci-ppt
description: Create, revise and verify minimal scientific presentations in editable PowerPoint or Beamer. Use for research group meetings, literature talks and project reports that need restrained academic styling, source fidelity and preservation of existing edits. PPTX authoring requires Codex Presentations and its artifact-tool runtime. Does not cover long-form reports or scientific calculations.
---

# 极简科研汇报

讲清研究对象、方法和已有结果，保留决定结论的证据。新作采用朴素学术排版，续作尊重已有底稿与人工修改。

## 先确定任务

1. 读取可编辑底稿、资料和本次修改范围。只补问影响制作的缺失信息，例如听众、时长或实际底稿；不要从文件名、助手交付或未修改页面推断用户认可。
2. 运行 `python <skill>/scripts/select_workflow.py`。明确格式用 `--format pptx` 或 `--format beamer`；续作用 `--existing <源文件>`。`<skill>` 是本目录的绝对路径，命令可从其他目录调用。
3. 本次明确指定的格式优先，续作沿已有格式，全新汇报默认可编辑 PPTX。仅在用户要求时同时制作两种格式。PDF 本身不能确定可编辑源格式；旧 `.ppt` 先用 PowerPoint 或 LibreOffice 转为 `.pptx` 工作副本。
4. 根据格式读取 [PowerPoint 规范](references/pptx.md) 或 [Beamer 规范](references/beamer.md)，依赖与安装见 [使用说明](README.md)。入口只校验当前包和记录指纹，不会安装软件或查找作者的私人工作区。

## 规则优先级

**本次明确要求 > 当前工程已核实的人工修改 > 用户提供且适用范围匹配的偏好 > 本 skill 默认值 > 历史稿 > 参考材料。**

- 同范围的新要求可以替代旧要求；局部返修、个别已确认页面与他人参考不能扩成所有汇报的规则。
- 白底黑字、32/24/16 pt 只用于未指定模板的新建 PPTX。保留续作底稿的配色、字号和人工调整，不据默认值重新排整份旧稿。
- 只有可核实的用户取舍才构成采用证据；科学事实、真实数据和本次任务始终优先于工具默认值。
- 本 skill 与 `simple-sci-ppt` 是独立制作方案，不同时叠加两者的版式与备注规则。若提供 `talk_plan.md`，可直接采用其中的听众、时长、论证和素材优先级，不要求先运行其他 skill。

## 内容与表达

- 标题直接说主题，正文自然交代对象、做法和结果。精简重复说明，不删除必要公式、科学条件与决定结论的证据，也不把完整术语压成单字口号。
- 保留用户已有取舍、图表组织和合作署名。只修改指定范围；不要擅自恢复删除内容，或把删掉的文字移到大量备份页。
- 已有图和图例默认保留。先调整摆放、尺寸及无信息空白；仅在授权或任务确需重新制图时，根据真实数据重绘并核对结果。
- 相关图、表、公式可以同页。不要把并列证据画成因果链；保留轴、单位、图例、比例尺、色标和必要误差说明。
- 不强制固定页数、目录、章节过渡、结论框或每页 takeaway。不额外添加纠错、免责、制作过程小字；影响科学含义的条件放进正常正文。
- 区分文献引文、数据来源和计算条件。单篇文献在首页集中介绍文章信息；多来源页面保留必要短引文。素材详细出处留在源码或来源清单，内部材料不强制每页来源脚注。
- 只陈述有证据的已完成工作，结论不越过数据范围。不为补齐汇报擅自启动新计算，也不把计划测试写成已跑通的结果。
- PPTX 默认不新增演讲者备注。用户明确要求时才新增；续作已有备注按修改范围保留，编辑过的备注须与页面一致。可以另附按页对应的 UTF-8 TXT 讲稿，但不强制交付，也不自动写入备注。

## 制作与交付

1. 保留原件，在独立工作工程中制作。用 `scripts/project_manifest.py` 初始化 `project.json`，记录实际底稿、格式和模板指纹，详见[工程创建与来源](references/project-lifecycle.md)。
2. 先确定内容和来源，再排版。PPTX 使用 Codex Presentations 的 `@oai/artifact-tool` JavaScript ES module 流程；Beamer 使用本包模板或用户已有工程。缺少引擎时报告具体依赖，不静默更换制作后端。
3. PPTX 用 `scripts/visible_payload.py` 分离观众可见文字与内部规划信息；不要把整个规划对象转成页面文字。独立讲稿与备注分别处理。
4. 导出后重读结构、渲染全部页面，并逐页检查科学内容和视觉效果。自动检查通过不等于人工验收通过，见[验收规范](references/validation.md)。
5. 默认交付可编辑源（PPTX 或完整 Beamer 工程）及 PDF 预览。保留必要素材和简洁来源说明；临时研究、委派通信和无用草稿不进入工程。
6. 简短说明实际交付文件和影响使用的限制，不把内部 QA 日志变成汇报内容。

## 工具入口

`scripts/skill_runtime.py` 检查当前包并计算文件树指纹；`select_workflow.py` 选择格式；`project_manifest.py` 建立工程来源清单。`visible_payload.py`、`visible_text_lint.py`、`pptx_slide_order.py` 和 `render_and_check.py` 分别处理文字输入、语义筛查、实际页序及渲染验收。字号与配色检查只适用于采用本包默认值的新稿，不能据此改写用户的既有模板。
