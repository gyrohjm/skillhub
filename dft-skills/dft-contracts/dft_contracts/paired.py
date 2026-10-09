"""Local planning and cluster execution projects, joined by portable identities."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
from uuid import uuid4, UUID

from .layout import PROJECT_FILE, project_role, project_routes, stage_root, discover_workspace, route_for, STAGE_RE
from .local_config import read_private_json, preserve_private_files, config_dir
from .project_transport import Endpoint, digest, info
from . import project as p

AUTO_LIMIT = 1_000_000_000
STATE = '.dft/pair-state.json'
REMOTE_STATE = '.dft/remote-state.json'


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode()


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def read_json(path, default=None):
    return json.loads(path.read_text()) if path.is_file() else default


def write_json(path, value):
    p._write(path, encoded(value).decode())


def local_root(root):
    root = discover_workspace(root)
    if project_role(root) != 'local':
        raise ValueError('Select the local side of a paired project')
    p._safe(root, '.dft')
    return root


def endpoint_for(root):
    root = local_root(root)
    identifier = json.loads((root / PROJECT_FILE).read_text())['project_id']
    UUID(identifier)
    binding = read_private_json(f'project-{identifier}.json')
    if not isinstance(binding, dict) or binding.get('local_root') != str(root):
        raise ValueError('Private project binding missing or belongs to another local root')
    return Endpoint(binding['remote_root'], binding.get('ssh'))


def check_remote(root, endpoint):
    local = read_json(root / PROJECT_FILE)
    remote = endpoint.json(PROJECT_FILE)
    if not remote or remote.get('project_id') != local.get('project_id') or remote.get('storage_role') != 'cluster':
        raise ValueError('Cluster project identity mismatch')
    if remote.get('routes') != local.get('routes'):
        raise ValueError('Route manifests differ; rerun paired initialization before transfer')


def _route_specs(spec):
    if not isinstance(spec, dict) or set(spec) - {'routes', 'references', 'cluster_files'}:
        raise ValueError('Initialization spec accepts routes, references and cluster_files')
    routes, stages = [], []
    for entry in spec.get('routes', []):
        if not isinstance(entry, dict) or set(entry) - {'path', 'composition', 'structure', 'stages'}:
            raise ValueError('Invalid initialization route')
        relative = Path(entry['path'])
        if not relative.parts or relative.is_absolute() or any(not p.NAME.fullmatch(x) for x in relative.parts):
            raise ValueError('Route must use safe relative names')
        if relative.parts[0] in {'docs', 'analysis', 'results', 'shared', 'archive', 'code'}:
            raise ValueError('Reserved route path')
        route = {k: entry[k] for k in ('path', 'composition', 'structure')}
        p._name(route['composition']); p._name(route['structure'])
        for old in routes:
            other = Path(old['path'])
            if relative == other or relative in other.parents or other in relative.parents:
                raise ValueError('Overlapping routes')
        routes.append(route)
        for stage in entry.get('stages', []):
            if not isinstance(stage, str) or not STAGE_RE.fullmatch(stage):
                raise ValueError('Initialization stages are numbered stage names, not invented variants')
            stages.append((relative / stage).as_posix())
    return routes, sorted(set(stages))


def reference_inventory(root, refs='docs/refs'):
    directory = p._safe(root, refs)
    entries = []
    if directory.exists():
        if not directory.is_dir():
            raise ValueError('Reference entry must be a directory')
        for item in sorted(directory.rglob('*')):
            p._safe(root, item.relative_to(root))
            if item.is_file():
                entries.append({'path': item.relative_to(root).as_posix(), **info(item)})
    return entries


def _reference_moves(root, spec, refs, previous):
    actions, destinations = [], set()
    base = p._safe(root, refs)
    for item in spec.get('references', []):
        if not isinstance(item, dict) or set(item) != {'source', 'target'}:
            raise ValueError('Reference moves require source and target')
        source, target = p._safe(root, item['source']), p._safe(root, item['target'])
        if base not in source.parents or base not in target.parents:
            raise ValueError('Organize references only inside the declared refs directory')
        if target in destinations:
            raise ValueError('Reference destinations overlap')
        destinations.add(target)
        if source.is_file():
            metadata = info(source)
        else:
            old = next((r for r in previous if r['source'] == item['source'] and r['target'] == item['target']), None)
            if not old or info(target) != old['content']:
                raise ValueError('Reference source missing or changed since organization')
            metadata = old['content']
        if target.exists() and info(target) != metadata:
            raise ValueError('Reference destination conflict; originals preserved')
        actions.append({**item, 'content': metadata})
    sources = {p._safe(root, a['source']) for a in actions}
    if any(p._safe(root, a['target']) in sources and a['target'] != a['source'] for a in actions):
        raise ValueError('Reference rename chains/cycles need separate reviewed operations')
    return actions


def _rules(role):
    common = '''Use the project/route/task-stage README templates. Explain scripts/, data/, figures/,
attempts/ and revisions/ in their owner's directory table; no container READMEs.
Update existing managed sections after meaningful operations; show current facts,
last verification and the latest three relevant events. Preserve human text. At handoff
refresh observations and check. Offline observations remain explicitly stale.
Initialization, a Git commit, references and historical authorization grant no new
permission to calculate. Preserve completed/running input snapshots and old evidence.
Private connection and absolute-root bindings stay outside every Git worktree.
'''
    if role == 'local':
        return '''## Local DFT project

Read docs/refs as research material and record sources and unresolved questions in
the existing route docs/plan.md. Retain original paper/structure contents when organizing
names. Keep the full design, authorization history, project synthesis and route docs/log.md
here. Stage analysis belongs to the cluster numbered-stage README. MEMORY.md holds durable decisions. docs/data-index.md is the one derived data index.
analysis/main_report.md is the only main report; figures/ and tables/ contain selected
final copies. Task inputs/, scripts/ and data/ hold selected reproduction copies.
Cluster scripts are authoritative; do not edit local copies independently. Review remote
parameter differences against the local plan before the affected new execution.
Select only against recorded acceptance criteria; unresolved selection needs user input.
Copy a selected task version's reproduction bundle automatically up to 1 GB; larger
bundles require an explicit reviewed scope. Preserve cluster sources. Initialize local
Git without adding, committing or pushing. Read dft-work-manager's paired-project reference
for init/deploy/refresh/reconcile/publish commands and dft-workflow for execution.
''' + common
    return '''## Cluster DFT project

Keep native inputs, raw outputs and workflow.json with each executable task. Maintain
task scripts/, data/ and figures/ here. Shared structures/potentials are optional, versioned,
and pinned by their consumers. Numbered-stage README owns stage analysis, limitations,
embedded figures and relative links to raw data, plot data and scripts. Do not write
separate reports for calculation variants. Root/route README provides navigation.
Plans, human logs and the sole formal main report belong to the paired local project.
After recorded convergence/acceptance, return selected conclusions and artifacts with
source paths, task identity and hashes; keep source evidence here. Use only the deployed minimal execution snapshot to run;
changed inputs require local reconciliation and a newly bound snapshot before submission.
Report factual execution events to the local project; never create local planning files
on this endpoint. Use dft-workflow's canonical submission and dependency checks.
''' + common


def init_pair(project_root, remote_root, *, ssh=None, cluster='primary', spec=None,
              refs='docs/refs', dry_run=False, git=True):
    root = Path(project_root).expanduser().resolve()
    endpoint = Endpoint(remote_root, ssh)
    if not ssh:
        remote = Path(remote_root).resolve()
        if root == remote or root in remote.parents or remote in root.parents:
            raise ValueError('Local and cluster roots must be separate trees')
    private = config_dir()
    if private == root or root in private.parents or (not ssh and (private == remote or remote in private.parents)):
        raise ValueError('Private project bindings must stay outside both project trees')
    p._name(cluster)
    spec = spec or {}
    routes, stages = _route_specs(spec)
    old = read_json(root / PROJECT_FILE)
    if old and old.get('storage_role') != 'local':
        raise ValueError('Existing single-root project preserved; pairing requires explicit migration')
    if not old and ((root / 'results/main_report.md').exists() or (root / 'calculations').exists()):
        raise ValueError('Existing project needs explicit migration; no second main report created')
    identifier = old['project_id'] if old else str(uuid4())
    UUID(identifier)
    existing_routes = old.get('routes', []) if old else []
    for old_route in existing_routes:
        if old_route not in routes:
            routes.append(old_route)
    # Validate the merged graph, not only the requested additions.
    _route_specs({'routes': routes})
    local_manifest = {'schema_version': 1, 'project_id': identifier, 'storage_role': 'local', 'routes': routes,
                      'planned_stages': sorted(set(stages + (old.get('planned_stages', []) if old else [])))}
    remote_manifest = dict(local_manifest, storage_role='cluster')
    remote_available = True
    try:
        remote_blob = endpoint.read(PROJECT_FILE, optional=True)
    except (OSError, RuntimeError):
        remote_available, remote_blob = False, None
    remote_old = json.loads(remote_blob) if remote_blob else None
    if remote_old and (remote_old.get('project_id') != identifier or remote_old.get('storage_role') != 'cluster'):
        raise ValueError('Existing cluster project has a different identity; preserved')
    binding = {'local_root': str(root), 'remote_root': endpoint.root, 'ssh': ssh, 'cluster': cluster}
    old_binding = read_private_json(f'project-{identifier}.json')
    if old_binding is not None and old_binding != binding:
        raise ValueError('One project has one main cluster; rebinding requires explicit migration')
    state = read_json(root / STATE, {'reference_moves': [], 'uploads': {}})
    inventory = reference_inventory(root, refs)
    moves = _reference_moves(root, spec, refs, state['reference_moves'])
    uploads = []
    for item in spec.get('cluster_files', []):
        if not isinstance(item, dict) or set(item) != {'source', 'target'}:
            raise ValueError('cluster_files entries require source and target')
        source = p._safe(root, item['source'])
        target = Path(item['target'])
        shared_scope = Path(*target.parts[:target.parts.index('shared')]) if 'shared' in target.parts else None
        if shared_scope is None or not any(shared_scope == Path('.') or shared_scope == Path(r['path'])
                or shared_scope in Path(r['path']).parents or Path(r['path']) in shared_scope.parents for r in routes):
            raise ValueError('Initialization uploads only explicitly selected shared inputs')
        p._safe(root, target)
        if not source.is_file():
            move = next((m for m in moves if m['target'] == item['source']), None)
            if move:
                source = p._safe(root, move['source'])
        metadata = info(source)
        if metadata is None:
            raise ValueError('Selected shared input missing')
        remote_info = endpoint.stat(target) if remote_available else None
        if remote_info and remote_info != metadata:
            raise ValueError('Shared input version conflict; publish a new version without overwriting')
        uploads.append((item, metadata))
    # Preflight managed block syntax before modifying either endpoint.
    remote_docs = {}
    for relative in ['AGENTS.md', 'README.md', *(r['path'] + '/README.md' for r in routes), *(s + '/README.md' for s in stages)]:
        content = endpoint.read(relative, optional=True) if remote_available else None
        if content is not None:
            p._block(content.decode(), 'preview', '<!-- dft-view:start -->', '<!-- dft-view:end -->')
        remote_docs[relative] = content
    for relative in ['AGENTS.md', 'README.md']:
        path = p._safe(root, relative)
        if path.exists():
            p._block(path.read_text(), 'preview')
    preview = {'mode': 'paired', 'routes': routes, 'cluster_stages': stages,
               'references': inventory, 'reference_moves': moves,
               'shared_uploads': [item for item, _ in uploads],
               'unresolved': 'Agent reads sources and supplies only known stages; no scientific approval is created.'}
    if dry_run:
        return preview
    root.mkdir(parents=True, exist_ok=True)
    preserve_private_files({f'project-{identifier}.json': encoded(binding)})
    with p._lock(root):
        state['initialization'] = 'pending'
        write_json(root / STATE, state)
        write_json(root / PROJECT_FILE, local_manifest)
        for name, body in {'AGENTS.md': _rules('local'), 'README.md': '## Project navigation\n\nLocal planning, analysis and selected reproduction copies.',
                           'MEMORY.md': '## Decisions and next actions\n\nRecord verified decisions and unresolved questions with evidence.'}.items():
            path = p._safe(root, name)
            p._write(path, p._block(path.read_text() if path.exists() else f'# {Path(name).stem}\n', body))
        p._safe(root, refs).mkdir(parents=True, exist_ok=True)
        for action in moves:
            source, target = p._safe(root, action['source']), p._safe(root, action['target'])
            if source != target and source.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                if not target.exists():
                    shutil.copy2(source, target)
                if info(target) != action['content'] or info(source) != action['content']:
                    raise ValueError('Reference verification failed; source retained')
                # Save provenance before removing the original, so interruption is resumable.
                if action not in state['reference_moves']:
                    state['reference_moves'].append(action)
                write_json(root / STATE, state)
                source.unlink()
            elif action not in state['reference_moves']:
                state['reference_moves'].append(action)
        for route in routes:
            p.register_route(root, route['path'], route['composition'], route['structure'], locked=True)
        report = p._safe(root, 'analysis/main_report.md')
        if not report.exists():
            p._write(report, '# Main report\n\n<!-- dft-role:main_report -->\n\n## Findings\n\nNo conclusions adopted yet.\n')
        ignore = p._safe(root, '.gitignore')
        content = ignore.read_text() if ignore.exists() else ''
        for rule in ('.dft/', '*.local.*', '/docs/project-resources.md', '/docs/refs/**/*.pdf', 'POTCAR', '*.UPF', '*.upf', '*.out', '*.wfc*', 'WAVECAR', 'CHGCAR', 'workflow.json', 'job.sh', 'attempts/'):
            if rule not in content.splitlines():
                content = content.rstrip() + '\n' + rule + '\n'
        p._write(ignore, content)
        if remote_available:
            endpoint.write(PROJECT_FILE, encoded(remote_manifest), expected=hashlib.sha256(remote_blob).hexdigest() if remote_blob else None)
            for relative, before in remote_docs.items():
                if relative == 'AGENTS.md':
                    after = p._block(before.decode() if before else '# Cluster instructions\n', _rules('cluster'))
                elif before is None:
                    after = '# ' + str(Path(relative).parent) + '\n\n## Purpose\n\nCluster operational directory.\n\n## Files and use\n\nDescribe input/output entrypoints and execution/reproduction commands.\n'
                else:
                    continue
                endpoint.write(relative, after.encode(), expected=hashlib.sha256(before).hexdigest() if before else None)
            for item, metadata in uploads:
                endpoint.put(item['target'], p._safe(root, item['source']))
                state['uploads'][item['target']] = metadata
        state.update(initialization='complete' if remote_available else 'pending', references=reference_inventory(root, refs), cluster_stages=sorted(set(stages + state.get('cluster_stages', []))))
        write_json(root / STATE, state)
    if git:
        from .project_git import init_git
        try:
            init_git(root)
            state['git_check'] = 'installed'
        except ValueError as error:
            # Existing hooks/parent repositories are preserved; report the integration gap.
            state['git_check'] = 'requires_existing_hook_integration'
            preview['git_notice'] = str(error)
        write_json(root / STATE, state)
    if remote_available:
        sync_pair(root, endpoint=endpoint)
    else:
        cached = dict(read_json(root / REMOTE_STATE, {'tasks': []}), stale=True)
        write_json(root / REMOTE_STATE, cached)
        _refresh_views(root, cached)
    return dict(preview, status=state['initialization'], git_check=state.get('git_check', 'not_requested'))


def _record(relative, workflow, observed):
    # The record is deliberately portable and contains no resource/connection fields.
    return {'path': relative, 'task_uuid': workflow.get('task_uuid'), 'engine': workflow.get('engine'),
            'status': workflow.get('status', 'unknown'), 'completion': workflow.get('completion', {}),
            'management': workflow.get('management', {}),
            'dependencies': workflow.get('dependencies', []), 'lineage': workflow.get('lineage', {}),
            'task_slug': workflow.get('task_slug'), 'stage': workflow.get('stage'),
            'matrix_id': workflow.get('design', {}).get('matrix_id'),
            'submission': {key: workflow.get('submission', {}).get(key) for key in ('state', 'scheduler_state', 'job_id')},
            'history': [{key: event[key] for key in ('at', 'status') if key in event} for event in workflow.get('history', [])],
            'design_revision': workflow.get('design', {}).get('revision'),
            'verified_at': observed, 'workflow_sha256': hashlib.sha256(encoded(workflow)).hexdigest()}


def sync_pair(project_root, *, endpoint=None):
    root = local_root(project_root)
    endpoint = endpoint or endpoint_for(root)
    old = read_json(root / REMOTE_STATE, {'tasks': [], 'stale': True})
    records = []
    try:
        check_remote(root, endpoint)
        for route in project_routes(root):
            for relative in endpoint.workflows(route['path']):
                workflow_blob = endpoint.read(relative)
                workflow = json.loads(workflow_blob)
                record = _record(str(Path(relative).parent), workflow, now())
                record['observed_sha256'] = hashlib.sha256(workflow_blob).hexdigest()
                previous = next((r for r in old['tasks'] if r['path'] == record['path']), None)
                if previous and previous['workflow_sha256'] == record['workflow_sha256']:
                    record['verified_at'] = previous['verified_at']
                accepted = all(workflow.get('completion', {}).get(k) is True for k in ('scheduler_complete', 'artifact_complete', 'scientifically_accepted'))
                disposition = workflow.get('management', {}).get('disposition')
                record['category'] = ('selected' if accepted and disposition == 'selected' else disposition
                                      if disposition in {'terminated', 'superseded', 'archived', 'recoverable'} else 'needs_review')
                records.append(record)
        invalid = []
        for target, publication in read_json(root / '.dft/publications.json', {}).items():
            record = next((r for r in records if r['path'] == publication['task']), None)
            if (not record or record['category'] != 'selected' or record['task_uuid'] != publication['task_uuid']
                    or record['workflow_sha256'] != publication['workflow_sha256']
                    or any(endpoint.stat(name) != metadata for name, metadata in publication['sources'].items())):
                invalid.append(target)
        value = {'tasks': records, 'stale': False, 'invalid_publications': invalid}
    except (OSError, RuntimeError, ValueError, KeyError, TypeError) as error:
        value = dict(old, stale=True)
        write_json(root / REMOTE_STATE, value)
        _refresh_views(root, value)
        raise RuntimeError('Cluster refresh incomplete; local observations marked stale') from error
    write_json(root / REMOTE_STATE, value)
    for record in records:
        previous = next((r for r in old['tasks'] if r['path'] == record['path']), {})
        facts = {key: record.get(key) for key in ('task_uuid', 'status', 'completion', 'submission')}
        if facts != {key: previous.get(key) for key in facts}:
            event = 'observed_' + hashlib.sha256(encoded(dict(path=record['path'], **facts))).hexdigest()[:20]
            p.append_event(root, root / record['path'], event,
                f"Observed execution: {record['path']} — {record['status']}; acceptance gates: "
                + json.dumps(record['completion'], sort_keys=True), [])
    _refresh_views(root, value)
    refresh_cluster_views(root, endpoint, records)
    return root / 'docs/data-index.md'


def _refresh_views(root, value):
    with p._lock(root):
        return _refresh_views_locked(root, value)


def _refresh_views_locked(root, value):
    from .readmes import refresh
    lines = ['# Data index', '', 'Derived from cluster task and selection records; not a second execution ledger.', '',
             'Freshness: **not refreshed / unavailable**' if value['stale'] else 'Freshness: last verified observation', '',
             '| Task / purpose | UUID / design version | Execution | Screening/use | Evidence | Verified |', '|---|---|---|---|---|---|']
    for record in value['tasks']:
        evidence = ', '.join('`' + e + '`' for e in record.get('management', {}).get('evidence', [])) or 'not selected'
        lines.append(f"| `{record['path']}` / {record.get('stage', 'unknown')} | `{record['task_uuid']}` / {record.get('design_revision')} | {record['status']} | {record['category']} | {evidence} | {record['verified_at']} |")
    manifest = read_json(root / '.dft/publications.json', {})
    warnings = []
    lines += ['', '## Selected data and reproduction', '', '| Artifact | Source / SHA256 | State | Reproduction |', '|---|---|---|---|']
    for target, item in manifest.items():
        record = next((r for r in value['tasks'] if r['path'] == item['task']), None)
        invalid = (target in value.get('invalid_publications', []) or value['stale'] or not record or record['category'] != 'selected'
                   or record['task_uuid'] != item['task_uuid']
                   or record['workflow_sha256'] != item['workflow_sha256'])
        state = 'needs_review' if invalid else 'selected'
        if invalid:
            warnings.append(target)
        lines.append(f"| `{target}` | `{item['source']}` / `{item['source_sha256']}` | {state} | `{item['task']}/scripts/` and `data/` |")
    p._write(root / 'docs/data-index.md', '\n'.join(lines) + '\n')
    report = root / 'analysis/main_report.md'
    if report.exists():
        body = '## Artifact navigation and evidence freshness\n\n'
        body += '\n'.join(f'- [{Path(t).name}]({Path(t).relative_to("analysis")})' for t in manifest) or 'No final artifacts yet.'
        if warnings:
            body += '\n\nReview affected figures and report conclusions: ' + ', '.join(f'`{x}`' for x in warnings)
        start, end = '<!-- dft-publications:start -->', '<!-- dft-publications:end -->'
        text = p._block(report.read_text(), body, start, end)
        before, rest = text.split(start)
        block, after = rest.split(end)
        prose = (before.rstrip() + '\n\n' + after.lstrip()).strip()
        # Navigation belongs before scientific sections, while all human prose stays intact.
        title, separator, remaining = prose.partition('\n')
        p._write(report, title + '\n\n' + start + block + end + '\n\n' + remaining.lstrip() + '\n')
    refresh(root, value['tasks'], stale=value['stale'], locked=True)


def _publish_pair(project_root, task, source, kind, topic, evidence, *, endpoint=None,
                 max_bytes=AUTO_LIMIT, expected_sha256=None, dry_run=False):
    """Fetch a selected reproduction bundle; publish its manifest only after verification."""
    root = local_root(project_root)
    endpoint = endpoint or endpoint_for(root)
    check_remote(root, endpoint)
    p._name(topic)
    task = Path(task).as_posix()
    p._safe(root, task)
    if not stage_root(root / task):
        raise ValueError('Select a registered task')
    if kind not in {'figure', 'table'} or type(max_bytes) is not int or max_bytes < 1:
        raise ValueError('Publication needs figure/table and a positive transfer limit')
    blob = endpoint.read(task + '/workflow.json')
    workflow = json.loads(blob)
    if workflow.get('management', {}).get('disposition') != 'selected' or not all(
        workflow.get('completion', {}).get(k) is True for k in ('scheduler_complete', 'artifact_complete', 'scientifically_accepted')):
        raise ValueError('Publish only a selected, scientifically accepted task')
    source = Path(source).as_posix()
    relative_source = Path(source).relative_to(task)
    if relative_source.parts[0] not in {'figures', 'data'}:
        raise ValueError('Publish a task-owned figure or processed table')
    suffixes = p.EXTENSIONS['figure'] if kind == 'figure' else {'.csv', '.dat', '.md', '.tsv'}
    if Path(source).suffix not in suffixes:
        raise ValueError('Unsupported final artifact format')
    mapping = {}
    categories = set()
    for name in evidence:
        part = Path(name).relative_to(task)
        p._safe(root, name)
        if not part.parts or part.parts[0] not in {'scripts', 'data'}:
            raise ValueError('Reproduction evidence must be task-owned scripts/ or data/')
        categories.add(part.parts[0])
        mapping[Path(name).as_posix()] = Path(name).as_posix()
    if categories != {'scripts', 'data'}:
        raise ValueError('Reproduction requires both plotting data and an actual script')
    omitted_inputs = {}
    for item in workflow.get('inputs', {}).get('files', []):
        name = item.get('path', item.get('name'))
        if not isinstance(name, str) or item.get('base', 'task_root') != 'task_root':
            continue
        remote_name = (Path(task) / name).as_posix()
        p._safe(root, remote_name)
        if Path(name).name in {'POTCAR', 'WAVECAR', 'CHGCAR'} or Path(name).suffix.lower() == '.upf':
            metadata = endpoint.stat(remote_name)
            omitted_inputs[name] = metadata
        elif Path(name).name in {'INCAR', 'POSCAR', 'KPOINTS'} or Path(name).suffix.lower() in {'.in', '.win'}:
            mapping[remote_name] = (Path(task) / 'inputs' / name).as_posix()
    target = f'analysis/{"figures" if kind == "figure" else "tables"}/{topic}{Path(source).suffix}'
    mapping[source] = target
    sources = {name: endpoint.stat(name) for name in mapping}
    if any(value is None for value in sources.values()):
        raise ValueError('Required reproduction source missing')
    prior = read_json(root / '.dft/publications.json', {})
    cumulative = {(name, value['sha256']): value['size'] for publication in prior.values()
                  if publication['task_uuid'] == workflow['task_uuid']
                  for name, value in publication['sources'].items()}
    cumulative.update({(name, value['sha256']): value['size'] for name, value in sources.items()})
    total = sum(cumulative.values())
    inventory = {'task': task, 'bytes': total, 'files': sources, 'omitted_inputs': omitted_inputs,
                 'necessity': {name: ('final artifact' if name == source else 'native input' if '/inputs/' in mapping[name]
                                     else 'plotting script' if '/scripts/' in name else 'plotting data') for name in sources},
                 'status': 'needs_scope_approval' if total > max_bytes else 'ready'}
    if total > max_bytes or dry_run:
        return inventory
    # Validation before the first copy catches local edits and same-name collisions.
    copies_path = root / '.dft/copies.json'
    copies = read_json(copies_path, {})
    manifest_path = root / '.dft/publications.json'
    manifest = read_json(manifest_path, {})
    for name, relative in mapping.items():
        destination = p._safe(root, relative)
        current = info(destination)
        previous = copies.get(relative)
        wanted = sources[name]['sha256']
        if relative == target and current and current['sha256'] != wanted and current['sha256'] != expected_sha256:
            raise ValueError('Final artifact changed; review it and supply its expected SHA256')
        if current and current['sha256'] not in {previous, wanted}:
            raise ValueError('Local reproduction copy was edited; reconcile both versions')
    package = {'task_uuid': workflow['task_uuid'], 'sources': sources, 'mapping': mapping}
    package_hash = hashlib.sha256(encoded(package)).hexdigest()
    transfer_path = root / '.dft/transfers' / (package_hash + '.json')
    transfer = read_json(transfer_path, dict(package, status='pending', verified=[]))
    write_json(transfer_path, transfer)
    for name, relative in mapping.items():
        destination = p._safe(root, relative)
        current = info(destination)
        if current and current['sha256'] != sources[name]['sha256']:
            # Retain replaced reproduction bytes even if no Git commit was made.
            retained = p._safe(root, '.dft/retained/' + current['sha256'])
            retained.parent.mkdir(parents=True, exist_ok=True)
            if not retained.exists():
                shutil.copy2(destination, retained)
        endpoint.fetch(name, destination, sources[name], expected=current['sha256'] if current else None)
        copies[relative] = sources[name]['sha256']
        write_json(copies_path, copies)
        if name not in transfer['verified']:
            transfer['verified'].append(name)
        write_json(transfer_path, transfer)
    if endpoint.read(task + '/workflow.json') != blob or any(endpoint.stat(name) != metadata for name, metadata in sources.items()):
        raise ValueError('Cluster evidence changed during transfer; bundle remains pending')
    record = {'task': task, 'task_uuid': workflow['task_uuid'], 'source': source, 'sources': sources,
              'copies': mapping, 'source_sha256': sources[source]['sha256'],
              'workflow_sha256': hashlib.sha256(encoded(workflow)).hexdigest(),
              'design_revision': workflow.get('design', {}).get('revision'), 'omitted_inputs': omitted_inputs,
              'package_sha256': package_hash}
    manifest[target] = record
    write_json(manifest_path, manifest)
    transfer['status'] = 'complete'; write_json(transfer_path, transfer)
    return dict(inventory, status='published', target=target, package_sha256=package_hash)


def publish_pair(project_root, task, source, kind, topic, evidence, **kwargs):
    root = local_root(project_root)
    if kwargs.get('dry_run'):
        return _publish_pair(root, task, source, kind, topic, evidence, **kwargs)
    with p._lock(root):
        result = _publish_pair(root, task, source, kind, topic, evidence, **kwargs)
    if result['status'] == 'published':
        p.append_event(root, route_for(root / task)[0], 'publish_' + result['package_sha256'][:20],
                       f'Selected reproduction bundle published for {task}.', [result['target']])
        sync_pair(root, endpoint=kwargs.get('endpoint'))
    return result


def check_pair(project_root):
    root = local_root(project_root)
    from .organization import pending_issues
    issues = pending_issues(root)
    state = read_json(root / STATE, {})
    if state.get('initialization') != 'complete':
        issues.append('Paired initialization incomplete; repeat it to resume')
    if state.get('git_check') == 'requires_existing_hook_integration':
        issues.append('Existing Git hook preserved; integrate the project staged-content check')
    remote = read_json(root / REMOTE_STATE, {'stale': True, 'tasks': []})
    if remote['stale']:
        issues.append('Cluster observations are stale; refresh before selecting or publishing')
    if (root / '.git').exists():
        from .project_git import check_index
        issues.extend(check_index(root))
    for name in ('AGENTS.md', 'README.md', 'MEMORY.md', 'docs/data-index.md', 'analysis/main_report.md'):
        if not p._safe(root, name).is_file():
            issues.append(f'{name}: missing required local document')
    for route in project_routes(root):
        for name in ('README.md', 'docs/plan.md', 'docs/log.md'):
            if not p._safe(root, Path(route['path']) / name).is_file():
                issues.append(f'{route["path"]}/{name}: missing local route record')
    copies = read_json(root / '.dft/copies.json', {})
    for relative, sha in copies.items():
        path = p._safe(root, relative)
        if not path.is_file() or digest(path) != sha:
            issues.append(f'{relative}: reproduction copy changed or missing')
    for path in (root / '.dft/transfers').glob('*.json'):
        if read_json(path).get('status') != 'complete':
            issues.append(f'{path.name}: transfer pending; publication incomplete')
    for task, deployment in read_json(root / '.dft/deployments.json', {}).items():
        if deployment.get('state') != 'complete':
            issues.append(f'{task}: deployment pending; repeat deploy to resume verified files')
    for target in remote.get('invalid_publications', []):
        issues.append(f'{target}: source/selection changed; review affected report conclusions')
    for path in p.managed_files(root):
        relative = path.relative_to(root)
        if relative.parts[0] == 'analysis' and path.name not in {'README.md', 'main_report.md'} and (
                len(relative.parts) < 3 or relative.parts[1] not in {'figures', 'tables'}):
            issues.append(f'{relative}: analysis contains only the main report and final figures/tables')
        if path.suffix == '.md' and (b'<!-- dft-role:main_report -->' in path.read_bytes()
                or re.search(r'main_report|final_report|report_final|project_summary', path.stem, re.I)):
            if path != root / 'analysis/main_report.md':
                issues.append(f'{path.relative_to(root)}: duplicate main report')
    return issues


def mark_pair(project_root, task, disposition, reason, evidence, key=None, *, endpoint=None):
    from .lifecycle import validate_management
    root = local_root(project_root)
    endpoint = endpoint or endpoint_for(root)
    if disposition not in {'selected', 'recoverable', 'terminated', 'superseded', 'archived'}:
        raise ValueError('Unknown disposition')
    if not reason.strip() or not evidence:
        raise ValueError('Selection/retirement needs a reason and evidence')
    if p.findings((reason + '\n' + '\n'.join(evidence)).encode(), p.markers()):
        raise ValueError('Keep private environment values outside public decisions')
    for name in evidence:
        p._safe(root, name)
        if endpoint.stat(name) is None:
            raise ValueError('Cluster decision evidence missing')
    sync_pair(root, endpoint=endpoint)
    observed = read_json(root / REMOTE_STATE)['tasks']
    blob = endpoint.read(task + '/workflow.json')
    workflow = json.loads(blob)
    key = p._name(key or workflow['task_slug'])
    validate_management(root, root / task, workflow, observed, disposition, key)
    event = 'selection_' + hashlib.sha256(encoded({'task': task, 'disposition': disposition, 'reason': reason,
                                                  'evidence': evidence, 'key': key})).hexdigest()[:20]
    workflow['management'] = {'disposition': disposition, 'selection_key': key,
                              'reason': 'Local decision: ' + event, 'evidence': evidence}
    guards = {r['path'] + '/workflow.json': r['observed_sha256'] for r in observed}
    endpoint.write(task + '/workflow.json', encoded(workflow), expected=hashlib.sha256(blob).hexdigest(), guards=guards)
    route = route_for(root / task)[0]
    p.append_event(root, route, event, f'{task}: {disposition}. {reason}', [])
    sync_pair(root, endpoint=endpoint)
    return {'task': task, 'disposition': disposition}


def refresh_cluster_views(root, endpoint, records):
    """Render the same templates locally, then CAS only operational README blocks."""
    import tempfile
    from .readmes import refresh
    with tempfile.TemporaryDirectory(prefix='dft-readmes-') as temporary:
        shadow = Path(temporary).resolve()
        manifest = dict(read_json(root / PROJECT_FILE), storage_role='cluster')
        write_json(shadow / PROJECT_FILE, manifest)
        scopes = {'.', *(r['path'] for r in manifest['routes'])}
        scopes.update(read_json(root / STATE, {}).get('cluster_stages', []))
        for record in records:
            stage = stage_root(root / record['path'])
            if stage:
                scopes.add(stage.relative_to(root).as_posix())
        previous = {}
        for scope in scopes:
            relative = (Path(scope) / 'README.md').as_posix()
            content = endpoint.read(relative, optional=True)
            previous[relative] = content
            folder = p._safe(shadow, scope)
            folder.mkdir(parents=True, exist_ok=True)
            if content:
                p._write(folder / 'README.md', content.decode())
            for name in endpoint.dirs(scope):
                p._safe(shadow, Path(scope) / name).mkdir(exist_ok=True)
        refresh(shadow, records)
        for relative, content in previous.items():
            path = p._safe(shadow, relative)
            if path.exists():
                endpoint.write(relative, path.read_bytes(), expected=hashlib.sha256(content).hexdigest() if content else None)
