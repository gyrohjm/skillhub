"""Three README roles. Facts and recent events are projections, never a second log."""
from __future__ import annotations

import json
from pathlib import Path
import re

from .layout import PROJECT_FILE, project_role, project_routes, stage_root, final_directory

DESCRIPTIONS = {
    'docs': 'Plan and event log (local only).', 'refs': 'Source papers, structures and outlines.',
    'scripts': 'Task-owned preparation, processing and plotting code; pin the version used.',
    'inputs': 'Selected input copies for traceability.', 'data': 'Processed data; record units and source outputs.',
    'figures': 'Plots produced from recorded data and scripts.', 'tables': 'Selected summary tables.',
    'shared': 'Versioned common structures/potentials; preserve versions used by calculations.',
    'attempts': 'Technical retry evidence.', 'revisions': 'Scientific reruns with distinct identities.',
    'analysis': 'Final local report and selected figures/tables.',
}


def owners(root, directory):
    """Only root, registered route and first numbered stage own navigation documents."""
    result = [root]
    for item in project_routes(root):
        route = root / item['path']
        if directory == route or route in directory.parents:
            result.append(route)
            stage = stage_root(directory)
            if stage:
                result.append(stage)
    return result


def ensure(root, directory):
    from .project import _safe, _write
    for folder in owners(root, directory):
        # Local stage prose is created by a real analysis write, not by a cache/backup.
        if project_role(root) == 'local' and stage_root(folder) == folder:
            continue
        path = _safe(root, folder.relative_to(root) / 'README.md')
        if not path.exists():
            label = 'Project' if folder == root else ('Task stage' if stage_root(folder) == folder else 'Research route')
            body = (f'# {folder.name}\n\n## Purpose\n\n{label}; describe its concrete purpose here.\n\n'
                    '## Files and use\n\nRecord entrypoints and reproduction commands for this scope.\n')
            _write(path, body)


def events(root):
    values = []
    for route in project_routes(root):
        path = root / route['path'] / 'docs/log.md'
        if not path.is_file():
            continue
        for key, body in re.findall(r'<!-- dft-event:([^:]+):start -->\n(.*?)\n<!-- dft-event:[^:]+:end -->', path.read_text(), re.S):
            lines = body.splitlines()
            timestamp = next((x[10:] for x in lines if x.startswith('Recorded: ')), '')
            scope = next((x[7:] for x in lines if x.startswith('Scope: ')), route['path'])
            summary = next((x for x in lines if x and not x.startswith(('Recorded:', 'Scope:', 'Evidence:'))), key)
            values.append({'id': key, 'at': timestamp, 'scope': scope, 'summary': summary[:240]})
    return sorted(values, key=lambda x: (x['at'], x['id']))


def refresh(root, records=None, *, stale=False, locked=False, scopes=None):
    from .project import _block, _safe, _write, _lock, task_records
    if not locked:
        with _lock(root):
            return refresh(root, records, stale=stale, locked=True, scopes=scopes)
    role = project_role(root)
    if records is None:
        records = task_records(root)
    current_events = events(root) if role != 'cluster' else []
    if role == 'cluster':
        for record in records:
            workflow_path = _safe(root, Path(record['path']) / 'workflow.json')
            workflow = json.loads(workflow_path.read_text()) if workflow_path.is_file() else record
            if workflow:
                for item in workflow.get('history', []):
                    if not isinstance(item, dict):
                        continue
                    # Free-form notes may be research prose; remote views use only execution facts.
                    state = item.get('status', 'unknown')
                    if state not in {'planned', 'prepared', 'awaiting_upstream', 'submitted', 'running', 'completed', 'failed', 'inconclusive', 'superseded'}:
                        state = 'unknown'
                    current_events.append({'id': str(item.get('at', '')), 'at': str(item.get('at', '')),
                                           'scope': record['path'], 'summary': f'Execution: {state}'})
    current_events.sort(key=lambda x: (x['at'], x['id']))
    directories = {root, *(root / item['path'] for item in project_routes(root))}
    for item in project_routes(root):
        base = root / item['path']
        if base.exists():
            for directory in base.iterdir():
                if directory.is_dir() and not directory.is_symlink() and stage_root(directory) == directory:
                    if role != 'local' or (directory / 'README.md').is_file():
                        directories.add(directory)
    for directory in sorted(directories):
        if scopes is not None and directory not in scopes:
            continue
        ensure(root, directory)
        readme = _safe(root, directory.relative_to(root) / 'README.md')
        if not readme.exists():
            continue
        relative = directory.relative_to(root).as_posix()
        within = lambda path: relative == '.' or path == relative or path.startswith(relative + '/')
        selected = [r for r in records if within(r['path'])]
        relevant_events = [e for e in current_events if within(e['scope'])][-3:]
        observed = max((str(r.get('verified_at', '')) for r in selected), default='')
        rows = ['## Current snapshot', '', f'- Last verified: {observed or "not yet verified"}',
                '- Freshness: not refreshed; connection unavailable' if stale else '- Freshness: last recorded observation; no background monitor', '']
        if directory == root:
            if role != 'cluster':
                report = final_directory(root).relative_to(root) / 'main_report.md'
                rows += [f'[Main report]({report}) · [Data index](docs/data-index.md)' if role == 'local' else f'[Main report]({report})', '']
            rows += ['## Research routes', ''] + [f"- [{r['path']}]({r['path']}/README.md)" for r in project_routes(root)]
        elif stage_root(directory) != directory and role != 'cluster':
            rows += ['[Current plan](docs/plan.md) · [Full event log](docs/log.md)', '']
        rows += ['## Directory guide', '', '| Directory | Purpose |', '|---|---|']
        for child in sorted(directory.iterdir()):
            if child.is_dir() and not child.name.startswith('.') and not child.is_symlink():
                rows.append(f'| `{child.name}/` | {DESCRIPTIONS.get(child.name, "Stage or grouping; see task index.")} |')
        rows += ['', '## Tasks', '', '| Task | Execution | Acceptance gates | Use | Upstream / lineage |', '|---|---|---|---|---|']
        for record in selected:
            path = record['path'] if relative == '.' else str(Path(record['path']).relative_to(relative))
            gates = record.get('completion', {})
            gate_text = ', '.join(f'{key.removesuffix("_complete").removesuffix("_accepted")}: {gates.get(key, "unknown")}'
                                  for key in ('scheduler_complete', 'artifact_complete', 'scientifically_accepted'))
            upstream = [str(d.get('task_ref', 'unknown')) for d in record.get('dependencies', []) if isinstance(d, dict)]
            if record.get('lineage', {}).get('derived_from'):
                upstream.append('derived_from: ' + record['lineage']['derived_from'])
            use = record.get('category', record.get('management', {}).get('disposition', 'needs_review'))
            rows.append(f"| `{path}` | {record.get('status', 'unknown')} | {gate_text} | {use} | {', '.join(upstream) or 'none recorded'} |")
        rows += ['', '## Recent changes', '']
        rows += [f"- {e['at']} — {e['summary']}" for e in relevant_events] or ['No recorded changes.']
        _write(readme, _block(readme.read_text(), '\n'.join(rows), '<!-- dft-view:start -->', '<!-- dft-view:end -->'))


def after_operation(task):
    """A derived view failure must never turn a scheduler receipt into a retry."""
    from .layout import discover_workspace
    from .project import _write
    try:
        root = discover_workspace(task)
    except ValueError:
        return
    if not (root / PROJECT_FILE).exists():
        return
    pending = root / '.dft/readme-refresh-required'
    try:
        refresh(root)
        if pending.exists():
            pending.unlink()
    except (OSError, ValueError):
        _write(pending, 'Refresh derived README blocks; execution records remain authoritative.\n')
