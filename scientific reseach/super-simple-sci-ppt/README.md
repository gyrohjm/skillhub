# super-simple-sci-ppt

面向科研组会、文献阅读和项目汇报的极简制作 skill，同时支持可编辑 PPTX 和 Beamer。公开版由 `research-reporting` 整理而来，保留制作规则与工具，不包含私人汇报、聊天记录或本机安装状态。

## 安装与调用

将完整的 `super-simple-sci-ppt` 目录复制到 Codex 的 skills 目录：设置了 `CODEX_HOME` 时为其下的 `skills/`，否则为用户目录下的 `.codex/skills/`。也可以让代理直接读取本目录的 `SKILL.md`。更新时替换这一个目录，不需要安装旧版 skill。

示例请求：

> 使用 $super-simple-sci-ppt，根据这些论文和图片制作 10 分钟中文组会汇报，交付 PPTX 和 PDF。

> 使用 $super-simple-sci-ppt，只修改这份 Beamer 的结果部分，保留模板、原图和其余内容。

新作默认 PPTX；续作沿原格式。明确的用户要求和已有人工修改优先于本包默认风格。与仓库里的 `simple-sci-ppt` 独立使用，不要求加载它。

## 运行依赖

| 用途 | 依赖 |
|---|---|
| 格式选择、工程清单、文字及 OOXML 检查、测试 | Python 3.10+，仅标准库 |
| PPTX 制作 | Codex Presentations skill、其提供的 Node.js 与 `@oai/artifact-tool` 运行时 |
| PPTX 转 PDF | Windows PowerPoint（可通过 PowerShell COM 调用），或 PATH 中的 LibreOffice `soffice` |
| PDF 转页面 PNG | PyMuPDF，或 PATH 中的 Poppler `pdftoppm` |
| 拼接检查图 | Pillow |
| 默认 PPTX 字体 | SimHei、Arial、Times New Roman；采用其他字体时按实际要求另行核验 |
| Beamer | XeLaTeX、latexmk、Metropolis、ctex 及模板引用的标准 TeX 包；Windows 可使用 WSL |

**PPTX 制作依赖 Codex 提供的专用运行时，本包不包含该运行时，也不把它当成可从公开 npm 安装的依赖。** 在 Codex 中先通过 `load_workspace_dependencies` 定位运行时，并按安装的 Presentations 文档操作。没有该能力的环境仍可使用 Beamer 分支及 Python 检查工具，但不能宣称支持本包的 PPTX 制作流程。

需要本地 Python 渲染组件时，可在自己的环境运行：

```text
python -m pip install -r <skill>/requirements-render.txt
```

这只安装 Pillow 和 PyMuPDF，不安装 Office、TeX、字体或制作引擎。缺少导出器、字体或渲染器时，应报告缺少的具体依赖；不得把未渲染的文件标为验收通过。

## 常用命令

以下 `<skill>` 替换为本目录的绝对路径，路径有空格时用引号包裹。命令不依赖当前工作目录或作者机器。

```text
python <skill>/scripts/skill_runtime.py
python <skill>/scripts/select_workflow.py
python <skill>/scripts/select_workflow.py --format beamer
python <skill>/scripts/select_workflow.py --existing <existing.pptx>
python <skill>/scripts/project_manifest.py <new-project-dir>
python <skill>/scripts/project_manifest.py <new-project-dir> --existing <existing.tex>
python <skill>/scripts/visible_payload.py <content.json> --output <visible.json>
python <skill>/scripts/visible_text_lint.py <deck.pptx>
python <skill>/scripts/render_and_check.py <deck.pptx> --output-dir <qa-dir>
python <skill>/scripts/render_and_check.py <deck.pptx> --output-dir <qa-dir> --review <qa-dir>/visual-review.json
python -m unittest discover -s <skill>/tests -v
```

第一次渲染生成待填写的逐页检查记录；查看全部 PNG 后据实填写，再用 `--review` 复核。工具的首次零退出码只代表渲染及机械检查完成，`rendered-pending-review` 仍未通过视觉验收。当前 `render_and_check.py` 的 32/24/16 pt 与黑色文字检查只适用于默认风格；指定模板的其他样式应按实际标准验收。

PPTX 起始模块在 `assets/pptx-starter.mjs`。复制到汇报的工作工程后使用，使模块能解析该工程配置的运行时包；不要在 skill 目录写入 `node_modules` 或构建产物。模板中的数字 fontSize/几何值使用像素，显式 `pt` 字符串使用点。

Beamer 从入口所在目录运行：

```text
latexmk -xelatex -interaction=nonstopmode -file-line-error -outdir=build -auxdir=build main.tex
```

生成结果还需要按 [验收规范](references/validation.md) 检查。空白模板不预设封面、目录或固定页数，应加入任务实际需要的 frame。

## 维护与分发

本目录为独立公开包。运行检查验证必要文件和本地文档链接，并输出当前内容指纹；该指纹用于记录模板版本，**不是数字签名，也不证明包来源可信**。运行前不要求联网、原维护项目或安装回执。

只维护实际依赖的源码、模板、说明和测试。分发时排除 Python 缓存、`node_modules`、本机配置、凭据、安装回执及生成的预览。保留自己的已有工程和原始素材，不将它们加入公开 skill 包。
