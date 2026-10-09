# Organize an existing DFT project

Use this branch for taking over a cluttered project, renaming or nesting directories,
and repairing their references. It extends the existing manager; initialization remains
an additive operation. Run commands through `dft-work-manager/scripts/dft_project.py`.

## Inventory before rearranging

1. Read the existing AGENTS, project manifest and README. Establish each endpoint's
   role and existing route identities. Keep meaningful names and add depth only for
   actual stages, parameter variants or revisions; use optional shared/ at the nearest
   common scope. See [workspace layout](../../dft-contracts/references/workspace-layout.md).
2. Inventory the explicitly selected project root, including an unregistered tree:

   ```bash
   python <manager>/scripts/dft_project.py organize-inventory --project-root <project>
   ```

   Review native inputs/outputs, scripts, documents, ledgers and reference findings.
   The inventory returns JSON to stdout without writing files; it does not create
   workflow.json for legacy outputs.
3. Distinguish observed execution state, artifact completeness, scientific acceptance
   and adopted results. Use existing screen for registered tasks; use dft-analysis to
   examine convergence and acceptance evidence. Unknown is needs_review, not failure.
   A completed scheduler job alone does not identify the correct scientific result.
4. Update existing fixed plans, logs and the sole report through read/document with
   expected hashes. Consolidate useful prose with source links and unresolved conflicts;
   retain original documents until their disposition is explicitly included in the
   organization scope. Record one concise event per real change. Use the established
   README roles and data index, not a second family of migration plans or reports.

The inventory stage is complete when each proposed relocation has an owner, purpose,
known state and evidence, and remaining uncertainty is recorded in existing documents.
Indexing and explaining preserved directories is useful progress even when relocation
is blocked.

## Preview a concrete scope

The agent interprets the inventory and chooses paths; the script performs deterministic
checks and file operations. Reuse one operation ID and spec for each bounded scope.
All source/target/evidence paths in the spec are project-relative. Keep the spec
outside the project or in ignored .dft/ so its original path mappings are not mistaken
for live references. A fictional document-only example is:

```json
{
  "id": "organize_route_notes",
  "moves": [
    {"source": "old_notes", "target": "docs/refs/legacy/old_notes"}
  ],
  "edits": [
    {"path": "README.md", "old": "old_notes/outline.md",
     "new": "docs/refs/legacy/old_notes/outline.md",
     "sha256": "<SHA256 of the original README bytes>"}
  ],
  "inactive": []
}
```

An edit names the original path even if its containing directory is also being moved.
Its exact old text and original content hash bind the intended replacement. Semantic
document merging belongs in read/document; these edits only repair reviewed references.

```bash
python <manager>/scripts/dft_project.py organize-preview --project-root <project> \
  --spec <organization-spec.json>
```

Preview returns read-only JSON and a preview SHA256. Inspect source/target mappings, file/byte counts, conflicts,
and reference findings. Resolve a blocked subset or reduce the spec to the eligible
scope; do not present a partial proposal as an executable whole. The preview hash
binds the exact source checksums; per-file checksums are kept in the applied private journal.

Before moving calculation payloads, obtain a fresh scheduler observation for the exact
task scope. Every calculation relocation, including legacy tasks without ledgers, needs an `inactive` entry naming the task path,
the project-relative evidence file and its SHA256:

```json
{"path": "old/task", "evidence": ".dft/scheduler-observation.json",
 "sha256": "<SHA256 of the observation bytes>"}
```

The evidence file has this shape, populated from an actual check:

```json
{
  "observed_at": "<ISO8601 timestamp with timezone>",
  "tasks": {
    "old/task": {"scheduler_active": false,
                 "source": "<command and scope used to establish inactivity>"}
  }
}
```

The check must be no more than one hour old at apply. Never manufacture
an observation from filenames, a presumed old job or an unavailable connection.
Uncertain or stale observations leave the task in place. Running workflow state always
blocks relocation, even if an inactivity assertion says otherwise.

The preflight also blocks unresolved references, symlinks and unsupported path-bearing
native inputs. Its scanner covers common text documents and scripts; it cannot prove
that arbitrary generated shell/Python paths are safe. Examine scanner limits and
incoming dependencies for the chosen scope. Generic edits cannot change engine inputs,
workflow ledgers, execution snapshots, approval records or history.

Path-sensitive workflow records and paired execution bindings can block relocation;
the generic organizer does not rewrite these bindings. Preserve bound paused or completed
tasks in place until a separate binding-aware migration is available; arrange their
navigation and safe surrounding files instead. Organization never implicitly converts
a legacy project into a paired project.

## Apply and verify

Apply uses the exact SHA256 returned by the reviewed preview:

```bash
python <manager>/scripts/dft_project.py organize-apply --project-root <project> \
  --spec <organization-spec.json> --expected-sha256 <preview-sha256>
python <manager>/scripts/dft_project.py organize-check --project-root <project> \
  --key organize_route_notes
```

Changed source bytes or findings require a new preview. Apply copies and verifies
contents before preserving original bytes under the operation's private
`.dft/organization/<id>/originals/<action-index>` and installing the targets. The journal
maps those retained originals back to their source and destination. The ignored/private
operation journal lives alongside these originals. This retained source and
mapping enable inspection and continuation; they are not a public archive or a new
human log. The operation does not discard source bytes or modify Git history.

Resume with the original preview hash and unchanged moves/edits. Refresh expired
inactivity observations and their `inactive` entries after checking the scheduler
again; the resumed operation permits that evidence refresh without changing the move
scope. Inspect the journal before choosing a new scope. Conflicting destination bytes stop the affected operation rather
than being overwritten by modification time. Automatic rollback is not implemented;
restoration from retained originals requires a separately reviewed operation.

A mixed proposal can apply eligible items and report preserved items as needs_review.
After resolving those blockers, use a new operation ID for the newly reviewed remaining
scope; an already completed subset is not repeated. Interrupted eligible work uses the
same ID. Root/route navigation and local route log finalization are also resumable.

For two endpoints, run the corresponding inventory/preview/apply/check on each root
with its own spec and journal. This command is not a cross-endpoint transport or an
atomic two-root transaction. Keep the shared identities and local/cluster ownership
rules from [paired projects](../../dft-contracts/references/paired-projects.md).
Cluster evidence contains operational facts; full planning and human summaries remain
local. Use the existing verified result-return/export paths for transfers.

The helper updates registered root/route README navigation and the existing local route
log. Moved stage files remain byte-bound to the preview, including their existing README
unless an explicit edit was specified. After checking the filesystem, update the owning
stage README and fixed local index with the mapping, actual analysis and pending work. Recheck moved scripts'
documented invocation paths without submitting calculations. For registered projects,
finish with sync/check as well as organize-check.

Completion means every applied item passes the journal's integrity checks, supported
references are resolved, and navigation points to the verified locations. Report
preserved tasks, manual reference checks and remaining blockers explicitly. Partial
or interrupted work stays pending. The organization operation grants no calculation,
cancellation, cleanup, Git commit or push authorization.
