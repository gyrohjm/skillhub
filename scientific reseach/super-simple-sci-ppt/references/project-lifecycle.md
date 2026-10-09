# 工程创建与来源

保留原件，在新目录初始化工作工程。以下 `<skill>` 是本 skill 的绝对路径，命令可以从其他目录运行。初始化只写入 `project.json`，不会复制底稿或生成演示文件。

```text
python <skill>/scripts/project_manifest.py <new-project-dir>
python <skill>/scripts/project_manifest.py <new-project-dir> --format beamer
python <skill>/scripts/project_manifest.py <new-project-dir> --existing <editable-source>
```

续作初始化后，将源文件及实际依赖复制到工作工程。Beamer 包含递归 `input/include`、图片、bib 和局部样式，不能只复制入口。公共包不依赖作者的私人资料库或导入脚本。

| 字段 | 含义 |
|---|---|
| `project_id` | 稳定工程名称，默认取目标目录名 |
| `format` | `pptx` 或 `beamer`；明确要求优先，否则沿源格式 |
| `created_from` | 新作为 `new`，续作记录实际源文件；可用 `--created-from` 指定来源标识 |
| `source_entries` | 可选的用户自有资料条目标识，通过 `--source-entry` 逐项传入；默认空列表 |
| `template_version` | 新稿记录本包当前 SHA-256；沿原格式续作记录源文件指纹 |
| `status` | 初建为 `draft`；技术验收可记为 `validated`，用户采用需要另有明确证据 |

素材级的页码、图像身份、数据和用途保存在工程自己的来源清单中，不用备注代替索引，也不把引用某张图写成继承整份汇报。

重复运行相同初始化请求不覆盖原清单，也不会因 skill 更新而改写工程的模板指纹。不同来源或格式的冲突请求应失败；无清单的非空目录也拒绝初始化，避免覆盖已有工作。明确更换模板时，在确认后维护工程清单并重新验收。
