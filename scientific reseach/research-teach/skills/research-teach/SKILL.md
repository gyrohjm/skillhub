---
name: research-teach
description: Run a local-first research and teaching workflow that plans literature searches with the user, screens and downloads papers through an authenticated browser, converts PDFs to traceable Markdown, builds an Obsidian knowledge graph, and teaches through dialogue using a user-approved learner profile. Use for research-teach init/init-global, literature screening and download, PDF or webpage ingestion, evidence verification, concept mapping, controversy mapping, progressive learning documents, personalized explanation, and learner-profile proposals.
---

# Research Teach

Build project-local, traceable research knowledge while keeping the learner profile in a separate approved global context. Treat project Markdown as the source of truth; graphs and HTML are derived artifacts.

## Select a mode

- `init`: initialize the current project.
- `research`: diagnose the goal, plan and screen literature, then download approved candidates.
- `build`: convert documents, verify sources, create concept/controversy notes, and rebuild the graph.
- `teach`: explain from verified project sources and approved learner context.
- `full`: run `research`, `build`, and `teach` in order.

Run the CLI with:

```bash
python3 <this-skill-directory>/scripts/research_teach.py <command>
```

Resolve `<this-skill-directory>` from the loaded `SKILL.md` path. Do not copy the script into the project.

## Initialize

For first use on the machine:

```bash
python3 <this-skill-directory>/scripts/research_teach.py configure-mineru

python3 <this-skill-directory>/scripts/research_teach.py init-global \
  --agent-context "/absolute/path/to/Global Vault/AgentContext"
```

`configure-mineru` prompts for the API token without echoing it and writes a private `0600` environment file under `~/.config/research-teach/mineru.env`. Never place the real key in the plugin source, project, prompt, or shell command line.

For a project:

```bash
python3 <this-skill-directory>/scripts/research_teach.py init \
  --project "$PWD" \
  --global-context "/absolute/path/to/Global Vault/AgentContext"
```

Initialization creates `.research/config.yaml`, private/cache directories, source and learning folders, and a project-local `.research/global` symlink. The symlink is read-only by workflow: write only through approved proposals.

## Enforce the three confirmation gates

Do not bypass these gates in `research` or `full` mode:

1. Confirm the learner diagnosis, research question, scope, and Tier 1/Tier 2 core-journal list.
2. Confirm the screened download list. Classify each candidate as `Research`, `Teaching`, `Both`, or `Reject`; download at most 20 per batch.
3. Confirm the learning mission, progressive document outline, and first section.

Read [workflow.md](references/workflow.md) before research or full mode.

## Research and download

Search metadata before downloading. Screen title, abstract, keywords, year, document type, journal tier, relevance, and evidence quality. Peer-reviewed evidence supports research claims; textbooks, reviews, and authoritative pages may be teaching-only.

Use Codex Computer Use to operate the user's already-authenticated browser. Pause for the user if authentication expires or a CAPTCHA appears. Never read or store credentials, export cookies, bypass access controls, or bulk-download beyond the confirmed batch.

Store original papers under `papers/` and record source URL, DOI, access date, access type, and screening decision.

## Convert and verify

Read [conversion.md](references/conversion.md) before converting documents.

Use:

```bash
python3 <this-skill-directory>/scripts/research_teach.py convert path/to/file.pdf \
  --document-type reference
```

Policy:

- `reference`: MinerU API upload is allowed.
- `project_document`: require explicit `--approve-upload` for each file or a configured safe-directory rule.
- `confidential`: never upload; use local OpenDataLoader.
- If MinerU fails or fails the quality gate, use local OpenDataLoader.
- If OpenDataLoader is absent, ask before rerunning with `--install-fallback`.
- Never promote a failed or unverified conversion into teaching.

Keep formal Markdown and embedded assets under `knowledge/`; keep raw responses and intermediate extraction under `.research/cache/`.

## Build the knowledge base

Use two layers:

- `knowledge/Sources/`: faithful, traceable source notes.
- `knowledge/Concepts/` and `knowledge/Maps/`: atomic concepts, prerequisites, disputes, and evidence links.

Use `Inbox` for converted but unverified sources and `Verified` only after checking metadata, document integrity, and cited passages. Core teaching claims must use Verified sources.

Read [schemas.md](references/schemas.md) before authoring notes. Mark extracted relations `proposed`; mark them `verified` only after source checking or user confirmation.

Rebuild the offline graph:

```bash
python3 <this-skill-directory>/scripts/research_teach.py build-graph
python3 <this-skill-directory>/scripts/research_teach.py serve
```

## Teach through dialogue

Generate a short overview plus progressively deeper Markdown:

- `00-overview.md`
- `01-foundations/`
- `02-core/`
- `03-deep-dive/`

Adjust the structure when the topic requires it. Use the learner's mission, confirmed prior knowledge, preferences, and demonstrated understanding. Explain and answer questions in conversation; do not build complex courseware or automatic review reminders.

When understanding breaks down:

1. Identify missing prerequisite, misconception, or application failure.
2. Follow the graph to the relevant prerequisite.
3. Re-explain with a different representation.
4. Give progressively stronger hints.
5. Check understanding with a new free-recall or application prompt.

Do not treat exposure as mastery. Record durable learning only when the user demonstrates it.

## Update the learner profile safely

Never edit `.research/global` directly. Create a proposal:

```bash
python3 <this-skill-directory>/scripts/research_teach.py propose \
  --target preferences.md \
  --title "Prefers worked examples before abstractions" \
  --content "Confirmed during the current project." \
  --rationale "This should shape future explanations."
```

Preview and accept only after explicit user approval:

```bash
python3 <this-skill-directory>/scripts/research_teach.py preview-proposal path/to/proposal.json
python3 <this-skill-directory>/scripts/research_teach.py accept-proposal path/to/proposal.json
```

Conversation-derived explanations or conclusions are not written back automatically. Propose a change only when it is source-traceable and has durable value.
