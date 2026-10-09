# Project records, documents and lifecycle

For storage_role local/cluster, use [paired projects](paired-projects.md): init with
--remote-root, local reference-driven planning, deploy/reconcile-remote and publication
into the sole local analysis/main_report.md. The single-root paths below remain compatible.

Use dft-work-manager/scripts/dft_project.py. Python standard library and local Git;
no database, daemon or replacement workflow engine. Resolve the installed skill path.

## Initialize and resume

```bash
python <manager>/scripts/dft_project.py init --project-root <project>
python <manager>/scripts/dft_project.py route --project-root <project> \
  --route material/anharmonic --composition example --structure reference
python <manager>/scripts/dft_project.py context --project-root <project>
```

New projects use registered routes. Existing calculations/ projects keep their legacy
format unless explicitly migrated. init preserves human text and creates project
memory, instructions and a minimal results/ entry; route creates only its README and
docs. Neither action creates shared/, scientific stages or fake workflow records.
Read AGENTS.md, MEMORY.md, route README, plan and live context on resume. Context and
screen are read-only. Only current workflow.json records supply execution status.

## Fixed document identities

| Role | Route-project destination |
|---|---|
| main_report | results/main_report.md, unique for the entire project |
| plan | selected route's docs/plan.md |
| log | selected route's docs/log.md |
| readme | selected directory's README.md |
| report (.md) | selected task's analysis/README.md, stable sections |
| report (.json), data | selected task's analysis/data/<topic>.<ext> |
| figure | selected task's analysis/figures/<topic>.<ext> |

Stage conclusions, intermediate plots/data and dedicated scripts stay in the task.
README describes purpose, reading order, dependencies, sources and limitations;
the main report synthesizes across tasks. A new topic becomes a section when the
existing document already serves that purpose. Folder/filename changes cannot be used
to evade update conflicts. Engine-native names remain unchanged.

```bash
python <manager>/scripts/dft_project.py read --project-root <project> --kind main_report
python <manager>/scripts/dft_project.py document --project-root <project> \
  --kind main_report --section phonon_validation --source <draft.md> \
  --expected-sha256 <hash-returned-by-read>
```

Read returns path, content and SHA256. Update requires the hash for an existing route
document. A mismatch means reread/merge; it never authorizes a new filename. --section
replaces only its stable managed block and preserves other sections/human text. Read
hashes are concurrency checks, not scientific approvals. For a first write, path is
read-only and document creates its destination plus explanatory directory READMEs.
Legacy --replace remains compatibility-only; it does not bypass route document checks.

```bash
python <manager>/scripts/dft_project.py event --project-root <project> \
  --task-root <route-or-task> --key cutoff_review_001 \
  --text 'Recorded cutoff review; see the evidence for its scope.' --evidence <relative-file>
python <manager>/scripts/dft_project.py remember --project-root <project> \
  --kind finding --key cutoff_convergence --text 'Recorded conclusion and limitations.' \
  --evidence <relative-file>
```

Event IDs are append-once: exact repetition is a no-op; changed content under the same
ID fails. Use a correction event instead. Memory keys update in place; findings and
decisions require existing evidence. Neither memory nor historical authorization
creates permission for another calculation.

## Screen, select and retire

```bash
python <manager>/scripts/dft_project.py screen --project-root <project>
python <manager>/scripts/dft_project.py mark --project-root <project> \
  --task-root <task> --disposition selected --key harmonic_reference \
  --text 'Chosen after recorded validation.' --evidence <relative-validation-file>
```

Screen classifies selected, needs_review, active, recoverable, terminated, superseded,
archived and unidentified; shows dependents, unresolved references and archive blockers.
Completion alone is never selection. Mark requires reason/evidence and preserves
execution facts; selected requires all three completion gates. A selection key names
one purpose within a route, with only one selected task. Retire an old selection only
when its scope is superseded or evidence invalidates it, not merely because a new run exists.

Archive candidates still require a fresh scheduler check and script/path dependency
review. The tool performs no move, deletion, cancellation or submission. Logical
archived means recorded retirement in place; use the existing explicit verified export
procedure for physical archival. Retain failure causes, inputs, outputs and recovery data.

## Rework

```bash
python <manager>/scripts/dft_project.py rework-impact --project-root <project> --task-root <task>
python <workflow>/scripts/canonical_workflow.py rerun --task-root <terminal-task> \
  --reason '<reason linked to the plan>' --changes <parameter-changes.json>
```

1. Revise the existing plan: stable change ID, trigger/evidence, old/new values, scope,
   acceptance criteria and retry/resource stopping bound. Ordinary authorized changes
   do not need repeated approval; larger conflicts affect only the relevant branch.
2. rework-impact finds recorded downstream tasks. Classify each as reusable, recompute
   or compatibility unresolved, with evidence. The tool cannot prove scientific reuse
   or discover arbitrary references embedded in scripts. Unknown means blocked reuse.
3. Preserve running/finished snapshots. Same-input technical recovery uses attempts/;
   scientific changes create a new UUID in revisions/rerun_NNN/. rerun copies inputs
   into a candidate; it does not apply requested values or submit. Edit/reconcile the
   candidate against the revised plan before execution. Submission checks each recorded
   new value against parsed inputs; missing, unrecognized or mismatched changes block
   submission until the candidate and change record agree.
4. Validate new results against the recorded criteria; explicitly select only after
   acceptance. An old result may remain valid for old conditions or be invalidated by
   evidence. Latest directory, Git commit or scheduler COMPLETED is not a selection rule.
5. Update the existing plan, analysis README, selection and log. Refresh affected main
   report sections/final artifacts, then sync/check. Preserve unresolved conclusions.

## Publish selected final artifacts

```bash
python <manager>/scripts/dft_project.py publish --project-root <project> \
  --task-root <selected-task> --kind figure --topic example_dispersion \
  --source <task>/analysis/figures/dispersion.pdf \
  --evidence <relative-data-file> --evidence <relative-script>
```

Publish accepts explicitly selected, scientifically accepted task artifacts only.
Final copies live in results/figures or results/tables; the derived manifest records
source task/UUID, design revision and content/evidence hashes. Replace a changed final
artifact with its expected SHA256. Keep stable names and regenerate from sources.
The results README is updated in place. Publication does not create another report.

## Git and handoff

```bash
python <manager>/scripts/dft_project.py git-init --project-root <project>
python <manager>/scripts/dft_project.py git-check --project-root <project>
python <manager>/scripts/dft_project.py sync --project-root <project>
python <manager>/scripts/dft_project.py check --project-root <project>
```

Use git-init when project Git setup is in scope. It initializes a local repository and
installs a local pre-commit check; no staging, commit, remote, push or history rewrite.
An unrelated existing hook is preserved and requires explicit integration. Git-check
reads actual staged blobs, including uncommitted partial staging, and rejects duplicate
main reports/document copies, private data and runtime/large inputs. Keep .gitignore;
a hook can be bypassed and does not inspect old commits. Private markers stay outside Git.

Git versions the one plan/main report, small tables and code. Use exact commit plus
file path for a reviewed plan, and immutable input hashes for the executed calculation;
Git history is not a replacement for raw calculation backups. Commit only within
existing authorization, after checking the intended diff, never git add everything.
No automatic commit/push is enabled by this skill update.

At handoff, sync refreshes marked indexes without overwriting human descriptions;
check verifies document roles, names, workflow identity and published provenance.
Resolve newly introduced issues and explain pre-existing unknowns. A user may still
bypass tools with direct file writes; these checks detect supported violations, not
arbitrary semantic duplication. No agent-wide filesystem interception is claimed.

## Compatibility only

Legacy plans/<composition>/<structure>/{README.md,calculation_design.json,history.jsonl},
logs/<composition>/<structure>.md and structure-level analysis paths remain readable.
Route-specific paths are selected from the registered scope, not guessed from aliases.
Legacy tasks lacking UUID remain readable and require an explicit identity migration.
