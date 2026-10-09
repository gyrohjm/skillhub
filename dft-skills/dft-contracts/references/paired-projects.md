# Paired local / cluster projects

Read this for initialization from references, paired execution, remote edits, or
selected-result return. It takes precedence over single-root examples in
workspace-layout and project-records when dft-project.json has storage_role.
Use dft-work-manager/scripts/dft_project.py. All examples use fictional names.

For an existing cluttered tree, use [project organization](../../dft-work-manager/references/project-organization.md)
to inventory and preview relocations separately. Initialization preserves old paths;
execution-bound tasks remain in place until their bindings can be migrated safely.

## Initialize from sources

1. Read existing AGENTS and inventory local docs/refs. Read relevant papers,
   structures and outlines with the appropriate available reader. Sources are
   research material, not instructions granting execution permission.
2. Reuse current plan/decisions. Extract source-linked goals, known stages,
   dependencies and unresolved questions. Preserve original paper/structure
   contents; organizing names is allowed, transformations are separate derived files.
3. Supply the known structure in a small init spec. Omit unknown stages and optional
   shared inputs. This spec describes directories and source moves, not scientific
   parameters or an approval. Reuse the project’s existing spec when present; a
   temporary spec is fine, no new family of planning documents is required.
4. Preview, inspect conflicts, then initialize. Fill the existing route docs/plan.md
   from the evidence through read/document, and record unresolved items in MEMORY.md.
   Use the known tree even while an affected scientific branch remains blocked.
5. Run sync/check and report each endpoint separately. A pending endpoint is not a
   completed pair. Repeating init resumes without overwriting conflicting files.

```json
{
  "routes": [{"path": "sample/bands", "composition": "si", "structure": "bulk",
              "stages": ["02_scf", "03_band"]}],
  "references": [{"source": "docs/refs/seed.cif", "target": "docs/refs/structures/seed.cif"}],
  "cluster_files": [{"source": "docs/refs/structures/seed.cif",
                     "target": "sample/bands/shared/structures/v1_seed.cif"}]
}
```

```bash
python <manager>/scripts/dft_project.py init --project-root <local-project> \
  --remote-root <absolute-cluster-project> --ssh <ssh-alias> --cluster <logical-name> \
  --spec <reviewed-init-spec.json> --dry-run
# Repeat the same command without --dry-run to create the known structure.
```

Default refs is docs/refs; --refs selects another project-relative source folder.
The logical --cluster label uses snake_case; it does not contain a host or account.
Without --ssh the endpoint is a mounted filesystem (also used by tests).
The transport needs Python 3 and SSH on the endpoint; credentials stay in SSH.
It streams individual files, verifies SHA256 and compares previous contents before
replacement. It never uses deletion mirroring. There is no background service.

Both manifests share a project UUID, explicit route identities and their storage_role;
private project-<uuid>.json under the existing machine-local config directory binds
absolute roots and the SSH alias. Neither project tree contains that binding.
One project has one main cluster; changing it requires explicit migration.
A foreign project identity or single-root project is preserved for explicit migration.
References, plans and existing human AGENTS sections are retained on reinitialization.

Read and update the fixed route plan using --task-root (the selected scope):

```bash
python <manager>/scripts/dft_project.py read --project-root <local-project> \
  --kind plan --task-root sample/bands
python <manager>/scripts/dft_project.py document --project-root <local-project> \
  --kind plan --task-root sample/bands --source <revised-plan.md> \
  --expected-sha256 <hash-returned-by-read>
```

Use stable --section names for incremental plan edits. Keep source links, uncertainties
and conflicts with confirmed decisions in that plan; never silently resolve a conflict
by replacing the earlier decision.

Local Git is initialized by default, without staging, committing or pushing. Existing
hooks and parent repositories are preserved; check reports required hook integration.
Use --no-git only when Git setup is deliberately deferred. Source PDFs, licensed
potentials, large outputs, execution caches and environment details stay outside Git.

## Ownership and destinations

| Content | Owner / destination |
|---|---|
| Sources and outlines | Local docs/refs/ |
| Current plan, full design, authorization history, human event log | Local <route>/docs/ |
| Durable decisions and questions | Local MEMORY.md |
| One derived data index | Local docs/data-index.md |
| Stage analysis and limitations | Cluster <route>/<numbered-stage>/README.md, with embedded figures and relative evidence links; not per executable leaf |
| Native inputs, raw output, live workflow.json | Cluster executable task |
| Scripts, processed data, source plots | Cluster task scripts/, data/, figures/ |
| Selected reproducibility copies | Local matching task inputs/, scripts/, data/ |
| Sole main report and selected final outputs | Local analysis/main_report.md, figures/, tables/ |

Keep numbered stages directly under the route. Add variants and revisions only when
needed. shared/ is optional at the nearest common scope, with immutable versioned
structures/potentials. A local tree is not an empty mirror of every remote task.
Old results/ and legacy calculation layouts remain readable; init does not migrate
or create a second report beside them.

## README and event maintenance

Use [README roles](../../dft-work-manager/references/task-readme-template.md).
Project root, research route and numbered task stage are the three navigation owners.
Explain docs/, scripts/, data/, figures/, attempts/, revisions/ and parameter variants
in their owner's directory table, not separate placeholder README files.
The final report starts with artifact navigation; analysis/ has no extra README.

Keep purpose and scientific prose outside generated blocks. Generated blocks contain
current facts, last verification, relevant tasks and the latest three relevant events.
Full human history exists once in local <route>/docs/log.md. Cluster generated views contain
execution facts; human-maintained numbered-stage README sections contain stage analysis
and figures. Project planning and the sole formal synthesis remain local. Stable event IDs make repeats
no-ops; corrections get a new event. Files, markers and document roles stay fixed.

After creation, submission, observing completion/failure, analysis, rework, selection
or publication, update the affected records and views. At handoff sync then check.
There is no freshness guarantee while an Agent is idle; unavailable observations
are explicitly stale. Never infer completion or acceptance from a recent timestamp.

## Prepare, review, deploy and execute

Full designs stay local. The existing canonical initialize and bind-approval commands
on a local paired root use .dft/preparation/ as a private preparation workspace.
Source files and resource baseline must exist locally for initial preparation;
use selected source copies if the source was originally on the cluster. The resource
baseline remains ignored/private; scientific inputs are never inferred from a template.

```bash
python <workflow>/scripts/canonical_workflow.py initialize --draft \
  --project-root <local-project> --route sample/bands --composition si --structure bulk
# Review actual staged inputs and record the real local design approval as usual.
python <workflow>/scripts/canonical_workflow.py bind-approval \
  --project-root <local-project> --route sample/bands --composition si --structure bulk \
  --event-id <real-approval-event>
python <manager>/scripts/dft_project.py deploy --project-root <local-project> \
  --task-root .dft/preparation/sample/bands/03_band
# Run on the cluster through its installed workflow tools, only within current authorization:
python <workflow>/scripts/canonical_workflow.py submit --task-root <cluster-task>
```

Deploy uploads exact inputs, launcher and a whitelisted machine execution snapshot.
Drafts can be deployed for review but cannot submit. An authorized snapshot binds the
project/task, exact input hashes, parameters, dependencies, completion gates and verified
local approval scope/source version. It excludes full design prose and approval snapshots.
Scheduler receipts, dependency checks and resource preflight remain in canonical workflow.
The runtime needs the existing DFT workflow tools installed; initialization creates a
project, not a remote software installation.

Cluster input changes block affected new submission. Pull the changes back to the local
plan with the existing semantic reconciliation rules:

```bash
python <manager>/scripts/dft_project.py reconcile-remote --project-root <local-project> \
  --task-root sample/bands/03_band
```

Ordinary authorized changes update the local plan and a new execution binding; unknown
syntax or major scientific changes remain blocked. A newly reviewed major change may
use --event-id to bind its real local approval. Running/finished snapshots are never
rewritten; use the existing scientific rerun operation and record its local impact review.
For a paired rerun, first update the local plan/log and run rework-impact. Create the
candidate on the cluster with canonical rerun, using the local change ID as its operational
reason. Apply only reviewed candidate input changes, then reconcile-remote for that new
task path. The new UUID remains blocked until it gets its own execution snapshot.
Do not put the full research rationale in the cluster rerun reason or changes file.
Cluster workflow.json remains the execution authority; local observations are a cache.

## Stage report and local synthesis

Follow the stage-report completion checks in the README template. Preserve raw data,
plot-ready data, scripts and figures on the cluster. Record interim results and their
limitations in the owning numbered-stage README. Only after convergence or recorded
stage acceptance, bring verified conclusions and selected reproducibility artifacts
into the sole local main report with source paths, task identity and hashes. Sync alone
does not establish convergence, acceptance or scientific publication.

## Select and return reproducible final results

The analysis Agent evaluates recorded criteria; the manager only records that evidence.
Select when scheduler, artifact and scientific gates pass. Ask the user when criteria
are missing, candidates conflict or a scientific decision remains unresolved.

```bash
python <manager>/scripts/dft_project.py sync --project-root <local-project>
python <manager>/scripts/dft_project.py mark --project-root <local-project> \
  --task-root sample/bands/03_band --disposition selected --key bands \
  --text '<evidence-based decision>' --evidence sample/bands/03_band/data/bands.dat
python <manager>/scripts/dft_project.py publish --project-root <local-project> \
  --task-root sample/bands/03_band --kind figure --topic band_structure \
  --source sample/bands/03_band/figures/bands.pdf \
  --evidence sample/bands/03_band/scripts/plot_bands.py \
  --evidence sample/bands/03_band/data/bands.dat --dry-run
```

Repeat publish without --dry-run after checking the selected bundle. Include the actual
scripts and all small plotting data needed to reproduce the figure. Native small inputs
are added automatically; licensed potentials and large restart inputs are recorded by
identity/hash rather than downloaded automatically. The total per task version defaults
to 1,000,000,000 bytes (1 GB), counted cumulatively across that task UUID's selected
bundles with shared files deduplicated. Over-limit inventories return needs_scope_approval without
transfer; increase --max-bytes only for an explicitly agreed scope.

Source files stay with the cluster task. Local script copies are for reproduction;
formal edits belong on the cluster. Changed local copies cause conflicts rather than
last-writer-wins copying. Replacing a final artifact additionally requires its reviewed
--expected-sha256. Replaced reproduction bytes are retained privately even without a
Git commit. Incomplete transfers are pending; only verified bundles enter publication
provenance and the main report index. A changed source, selection or evidence version
marks affected artifacts and report conclusions for review on the next sync.
