# Document Conversion Policy

## Routing

| Document type | MinerU API | Local OpenDataLoader |
|---|---:|---:|
| `reference` | Allowed automatically | Fallback |
| `project_document` | Per-file approval or safe-directory rule | Default without approval |
| `confidential` | Forbidden | Required |
| Unknown | Treat as `project_document` | Default |

Configure MinerU with:

```bash
python3 <skill>/scripts/research_teach.py configure-mineru
python3 <skill>/scripts/research_teach.py mineru-config
```

The command writes `~/.config/research-teach/mineru.env` with mode `0600`. Override the location with `RESEARCH_TEACH_ENV_FILE` or `--env-file`. A process-level `MINERU_API_TOKEN` or `MINERU_BASE_URL` overrides the file. Never write tokens into project files, plugin source, prompts, or command-line arguments.

## Cache

Use a content-addressed cache based on source SHA-256, engine, version, and conversion parameters:

```text
.research/cache/<cache-key>/
├── raw/
├── extracted/
├── quality-report.json
└── manifest.json
```

The cache is disposable. Formal outputs are not:

- source Markdown: `knowledge/Sources/Inbox/`
- figures, tables, formula images, and embedded resources: `knowledge/Assets/<source-slug>/`
- original files: `papers/` or their existing project location

## Quality gate

Fail conversion when:

- no Markdown is produced,
- extracted text is effectively empty,
- the output is clearly an error page,
- required assets referenced by Markdown are missing.

Mark failure explicitly and do not use the document for concept extraction or teaching.

## OpenDataLoader fallback

Detect `opendataloader-pdf` on `PATH`, then the user-level isolated environment at:

```text
~/.local/share/research-teach/opendataloader/
```

If missing, obtain explicit approval before using `convert --install-fallback`. OpenDataLoader requires Java 11+ and Python 3.10+.

## Upload review

Before approving a project document for upload, show:

- absolute path,
- file type and size,
- whether the path is covered by a safe-directory rule,
- detected secret or personal-data warnings,
- the remote service and intended purpose.
