"""Explicit, resumable organization of old trees; scientific decisions stay with the Agent."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import sys

from . import project as p
from .layout import PROJECT_FILE, project_role, project_routes, route_for
from .lifecycle import active
from .project_transport import digest

TEXT_SUFFIXES = {'.md', '.rst', '.txt', '.sh', '.py', '.json', '.jsonl', '.yaml', '.yml', '.toml', '.ini', '.cfg', '.in', '.win', '.sbatch'}
NATIVE = {'INCAR', 'KPOINTS', 'POSCAR', 'CONTCAR', 'POTCAR', 'OUTCAR', 'WAVECAR', 'CHGCAR', 'DOSCAR', 'EIGENVAL'}
IMMUTABLE = NATIVE | {PROJECT_FILE, 'workflow.json', 'history.jsonl', 'calculation_design.json', 'task_spec.json', 'state.json', 'job.sh', 'qe.sh', 'vasp.sh'}
EXCLUDED = {'.git', '.dft', '__pycache__', '.pytest_cache'}
TEXT_LIMIT = 2 * 1024 * 1024


def _encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode()


def _hash(value):
    return hashlib.sha256(_encoded(value)).hexdigest()


def _root(value):
    root = Path(value).expanduser().absolute()
    if not root.is_dir() or any(x.is_symlink() for x in (root, *root.parents)):
        raise ValueError('Select a real project directory without symlink ancestors')
    return root.resolve()


def _path(root, value):
    if not isinstance(value, (str, Path)):
        raise ValueError('Organization paths must be relative strings')
    relative = Path(value)
    if not relative.parts or relative.parts[0] in EXCLUDED:
        raise ValueError('Organization paths must be explicit and outside Git/private metadata')
    return p._safe(root, relative)


def _walk(root):
    for folder, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in EXCLUDED)
        for name in sorted(files + [d for d in dirs if (Path(folder) / d).is_symlink()]):
            yield Path(folder) / name
        dirs[:] = [d for d in dirs if not (Path(folder) / d).is_symlink()]


def _text(path):
    if path.is_symlink() or not path.is_file() or (path.suffix.lower() not in TEXT_SUFFIXES and path.name not in NATIVE):
        return None
    if path.stat().st_size > TEXT_LIMIT:
        return None
    try:
        text = path.read_text()
        return text if '\0' not in text else None
    except UnicodeError:
        return None


def inventory(project_root):
    """Read arbitrary old trees, including tasks that canonical discovery cannot see."""
    root = _root(project_root)
    tasks, documents, links, skipped = {}, [], [], []
    count = size = 0
    for path in _walk(root):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            links.append(relative)
            continue
        if not path.is_file():
            skipped.append(relative)
            continue
        count += 1; size += path.stat().st_size
        folder = path.parent.relative_to(root).as_posix()
        candidate = path.name in NATIVE | {'workflow.json', 'task_spec.json', 'state.json'}
        if path.suffix.lower() == '.in':
            content = _text(path) or ''
            candidate = bool(re.search(r'(?im)^\s*&(control|system|inputph)\b', content))
        if candidate and not any(part in {'attempts', 'docs', 'refs', 'shared'} for part in path.relative_to(root).parts):
            task = tasks.setdefault(folder, {'path': folder, 'state': 'unknown', 'scientific_acceptance': 'unverified', 'evidence': []})
            task['evidence'].append(relative)
            if path.name == 'workflow.json':
                try:
                    workflow = json.loads(path.read_text())
                    if not isinstance(workflow, dict) or any(not isinstance(workflow.get(key, {}), dict)
                            for key in ('inputs', 'job', 'lineage', 'submission', 'completion')):
                        raise ValueError('Malformed task record')
                    if (not isinstance(workflow.get('dependencies', []), list)
                            or not isinstance(workflow.get('inputs', {}).get('files', []), list)
                            or any(not isinstance(item, dict) for item in workflow.get('inputs', {}).get('files', []))):
                        raise ValueError('Malformed task references')
                    task.update(state='active' if active(workflow) else 'recorded_' + str(workflow.get('status', 'unknown')),
                                task_uuid=workflow.get('task_uuid'), execution_bound=bool(workflow.get('execution')))
                except (ValueError, AttributeError):
                    task['state'] = 'invalid_record'
        if path.suffix.lower() in {'.md', '.rst', '.txt'} and _text(path) is not None:
            documents.append({'path': relative, 'sha256': digest(path), 'bytes': path.stat().st_size})
        elif path.suffix.lower() in TEXT_SUFFIXES and path.stat().st_size > TEXT_LIMIT:
            skipped.append(relative)
    duplicates = {}
    for document in documents:
        duplicates.setdefault(document['sha256'], []).append(document['path'])
    return {'tasks': list(tasks.values()), 'documents': documents,
            'identical_documents': [paths for paths in duplicates.values() if len(paths) > 1],
            'symlinks': links, 'uninspected': skipped, 'files': count, 'bytes': size,
            'note': 'Recorded state is not a fresh scheduler observation or scientific acceptance.'}


def _manifest(path):
    if path.is_symlink() or not path.exists():
        raise ValueError('Source missing or contains symlinks')
    entries = {}
    paths = [path] if path.is_file() else [path, *sorted(path.rglob('*'))]
    for item in paths:
        name = '.' if item == path else item.relative_to(path).as_posix()
        mode = item.lstat().st_mode
        if stat.S_ISLNK(mode) or not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)):
            raise ValueError('Symlinks and special files require separate review')
        if any(part in {'.git', '.dft'} for part in Path(name).parts):
            raise ValueError('Nested repositories/private records require separate review')
        entries[name] = {'kind': 'directory' if item.is_dir() else 'file', 'mode': stat.S_IMODE(mode)}
        if item.is_file():
            entries[name].update(size=item.stat().st_size, sha256=digest(item))
    return entries


def _inside(path, scope):
    return path == scope or scope in path.parents


def _mapped(path, moves):
    for move in moves:
        source = Path(move['source'])
        if _inside(path, source):
            return Path(move['target']) / path.relative_to(source)
    return path


def _immutable(path):
    return path.name in IMMUTABLE or path.suffix.lower() in {'.in', '.win', '.upf', '.out', '.sbatch'} or any(
        part in {'attempts', '.dft'} for part in path.parts)


def _spec(root, spec):
    if not isinstance(spec, dict) or set(spec) - {'id', 'moves', 'edits', 'inactive'}:
        raise ValueError('Organization spec accepts id, moves, edits and inactive')
    p._name(spec.get('id'))
    moves, edits = spec.get('moves', []), spec.get('edits', [])
    if not isinstance(spec.get('inactive', []), list) or any(not isinstance(item, dict)
            or set(item) != {'path', 'evidence', 'sha256'} for item in spec.get('inactive', [])):
        raise ValueError('Inactivity observations require path, evidence and sha256')
    if not isinstance(moves, list) or not isinstance(edits, list) or not moves and not edits:
        raise ValueError('Provide explicit moves or edits')
    for move in moves:
        if not isinstance(move, dict) or set(move) != {'source', 'target'}:
            raise ValueError('Each move requires source and target')
        source, target = _path(root, move['source']), _path(root, move['target'])
        if source == target or _inside(target, source) or _inside(source, target):
            raise ValueError('Source and target must be distinct, non-nested paths')
        if source.name in {PROJECT_FILE, 'AGENTS.md', 'MEMORY.md'} or source.name == 'main_report.md':
            raise ValueError('Maintain fixed project documents in place')
        if any(not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', part) for part in Path(move['target']).parts):
            raise ValueError('Use portable normalized target names')
    scopes = [Path(m[key]) for m in moves for key in ('source', 'target')]
    for index, one in enumerate(scopes):
        if any(_inside(one, other) or _inside(other, one) for other in scopes[:index]):
            raise ValueError('Move sources and destinations must not overlap; use sequential operations')
    for edit in edits:
        if not isinstance(edit, dict) or set(edit) != {'path', 'old', 'new', 'sha256'}:
            raise ValueError('Each edit requires path, old, new and sha256')
        path = _path(root, edit['path'])
        if _immutable(path) or not isinstance(edit['old'], str) or not edit['old'] or not isinstance(edit['new'], str):
            raise ValueError('Edit only explicit mutable text; preserve inputs and execution/approval records')
    return moves, edits


def _inactive(root, task, spec):
    proof = next((item for item in spec.get('inactive', []) if item.get('path') == task), None)
    if not proof:
        return 'fresh scheduler inactivity evidence required'
    try:
        path = p._safe(root, proof['evidence'])
        if digest(path) != proof['sha256']:
            return 'scheduler evidence changed'
        evidence = json.loads(path.read_text())
        observed = datetime.fromisoformat(evidence['observed_at'].replace('Z', '+00:00'))
        age = (datetime.now(timezone.utc) - observed).total_seconds()
        record = evidence['tasks'][task]
        if not 0 <= age <= 3600 or record.get('scheduler_active') is not False or not record.get('source'):
            return 'scheduler evidence is stale, active or incomplete'
    except (KeyError, TypeError, ValueError, OSError):
        return 'invalid scheduler evidence'
    return None


def _build(root, spec):
    moves, edits = _spec(root, spec)
    found = inventory(root)
    actions, changes = [], {}
    protected = set()
    for task in found['tasks']:
        ledger = root / task['path'] / 'workflow.json'
        if ledger.is_file() and task['state'] != 'invalid_record':
            record = json.loads(ledger.read_text())
            for item in record.get('inputs', {}).get('files', []):
                if item.get('base', 'task_root') == 'task_root' and isinstance(item.get('path'), str):
                    protected.add((Path(task['path']) / item['path']).as_posix())
            job = record.get('job', {}).get('script', '')
            if job:
                protected.add((Path(task['path']) / job.removeprefix('task_root:')).as_posix())
    paired_paths = set()
    if project_role(root) == 'local':
        for name in ('copies', 'publications'):
            manifest = root / f'.dft/{name}.json'
            if manifest.is_file():
                paired_paths.update(json.loads(manifest.read_text()))
    for move in moves:
        source, target = _path(root, move['source']), _path(root, move['target'])
        action = dict(move, blockers=[], tasks=[])
        try:
            action['files'] = _manifest(source)
        except ValueError as error:
            action['files'] = {}; action['blockers'].append(str(error))
        if target.exists():
            action['blockers'].append('destination already exists; merge explicitly without overwriting')
        if any(_inside(root / name, source) or _inside(source, root / name) for name in paired_paths):
            action['blockers'].append('paired reproduction/publication binding requires manifest-aware migration')
        if (root / PROJECT_FILE).is_file() and any(_inside(root / r['path'], source) for r in project_routes(root)):
            action['blockers'].append('registered route identity must remain in place')
        for task in found['tasks']:
            if not (_inside(root / task['path'], source) or _inside(source, root / task['path'])):
                continue
            action['tasks'].append(task['path'])
            if source != root / task['path'] and _inside(source, root / task['path']) and (
                    _immutable(source) or any(_inside(root / name, source) for name in protected)):
                action['blockers'].append('preserve task input ownership; move the complete task scope')
            reason = _inactive(root, task['path'], spec)
            if task['state'] == 'active':
                reason = 'active execution record; reconcile scheduler state before moving'
            if task.get('execution_bound'):
                reason = 'paired execution binding requires explicit local rebind; preserve task in place'
            if task['state'] == 'invalid_record':
                reason = 'invalid workflow record requires investigation'
            if reason:
                action['blockers'].append(task['path'] + ': ' + reason)
            ledger = root / task['path'] / 'workflow.json'
            if ledger.is_file():
                record = json.loads(ledger.read_text()) if task['state'] != 'invalid_record' else {}
                if record.get('dependencies') or record.get('lineage', {}).get('derived_from'):
                    action['blockers'].append('path-dependent execution lineage requires workflow-aware migration')
                try:
                    before = route_for(root / task['path'])
                    after = route_for(root / _mapped(Path(task['path']), moves))
                    if before and (not after or before[1] != after[1]):
                        action['blockers'].append('workflow route identity would change')
                except ValueError:
                    pass  # Truly unregistered legacy trees are inventoried without invented identities.
        actions.append(action)
    for edit in edits:
        path = _path(root, edit['path'])
        if edit['path'] in protected or edit['path'] in paired_paths:
            raise ValueError('Preserve declared execution inputs, launchers and bound reproduction copies')
        if edit['path'] not in changes:
            old = _text(path)
            if old is None or digest(path) != edit['sha256']:
                raise ValueError('Edit source is unavailable or changed since review')
            changes[edit['path']] = {'before': old, 'after': old, 'sha256': edit['sha256']}
        change = changes[edit['path']]
        if edit['sha256'] != change['sha256'] or edit['old'] not in change['after']:
            raise ValueError('Edit expectation is absent or inconsistent')
        change['after'] = change['after'].replace(edit['old'], edit['new'])
        if p.findings(change['after'].encode(), p.markers()):
            raise ValueError('Keep private environment values outside mutable project documents')
    references = []
    for path in _walk(root):
        if path.relative_to(root).as_posix() in {item['evidence'] for item in spec.get('inactive', [])}:
            continue  # A dated scheduler observation preserves its original scope.
        if path.is_symlink():
            # Aliases may point inside a moved tree; none are silently retargeted.
            destination = path.resolve()
            for action in actions:
                if _inside(destination, root / action['source']):
                    action['blockers'].append('incoming symlink: ' + path.relative_to(root).as_posix())
            continue
        text = _text(path)
        if text is None:
            continue
        relative = path.relative_to(root).as_posix()
        for action in actions:
            source = action['source']
            candidates = {str(root / source), source, './' + source, os.path.relpath(root / source, path.parent)}
            for token in candidates:
                if token in {'.', '..'}:
                    continue
                # ponytail: literal paths only; computed paths require Agent review.
                pattern = re.compile(r'(?<![\w./-])' + re.escape(token) +
                    (r'(?=/)' if '/' not in token and path.parent != root else r'(?=$|[/\s\x22\x27)\],:])'))
                matches = list(pattern.finditer(text))
                if not matches:
                    continue
                unresolved = bool(pattern.search(changes.get(relative, {}).get('after', text)))
                for match in matches:
                    references.append({'file': relative, 'line': text.count('\n', 0, match.start()) + 1,
                                       'source': source, 'resolved': not unresolved})
                if unresolved:
                    action['blockers'].append('unresolved reference: ' + relative)
        if path.name == 'workflow.json':
            try:
                record = json.loads(text)
                dependencies = record.get('dependencies', [])
                if dependencies:
                    scripts = str(Path(__file__).resolve().parents[2] / 'dft-workflow/scripts')
                    if scripts not in sys.path:
                        sys.path.insert(0, scripts)
                    from workflow_control import _resolve_dependency
                    for dependency in dependencies:
                        try:
                            resolved, _ = _resolve_dependency(path.parent, dependency)
                        except (ValueError, RuntimeError, TypeError):
                            resolved = None
                        for action in actions:
                            if (resolved is not None and (_inside(resolved, root / action['source'])
                                    or _inside(root / action['source'], resolved))
                                    or resolved is None and action['tasks']):
                                action['blockers'].append('execution dependency needs resolution: ' + relative)
                # Bare dependency slugs need actual workflow resolver review, not string replacement.
                refs = [next((d[key] for key in ('task_ref', 'task_id', 'path') if key in d), None)
                        if isinstance(d, dict) else d for d in record.get('dependencies', [])]
                for action in actions:
                    for task in found['tasks']:
                        if _inside(Path(task['path']), Path(action['source'])):
                            ledger = root / task['path'] / 'workflow.json'
                            if ledger.is_file() and json.loads(ledger.read_text()).get('task_slug') in refs:
                                action['blockers'].append('incoming workflow dependency: ' + relative)
            except (ValueError, AttributeError):
                for action in actions:
                    action['blockers'].append('unreadable workflow reference: ' + relative)
    if found['uninspected']:
        for action in actions:
            action['blockers'].append('uninspected text/special files require separate review')
    for action in actions:
        action['blockers'] = sorted(set(action['blockers']))
    # An edit and any related move form one unit; preserve both when either is blocked.
    blocked = [a for a in actions if a['blockers']]
    for path, change in changes.items():
        change['blocked'] = any(_inside(Path(path), Path(a['source'])) or any(
            r['file'] == path and r['source'] == a['source'] for r in references) for a in blocked)
        change['target'] = _mapped(Path(path), actions).as_posix()
        for task in found['tasks']:
            if _inside(Path(path), Path(task['path'])):
                if task['state'] == 'active' or _inactive(root, task['path'], spec):
                    change['blocked'] = True
    return {'id': spec['id'], 'moves': actions, 'edits': changes, 'references': references,
            'uninspected': found['uninspected']}


def preview(project_root, spec):
    plan = _build(_root(project_root), spec)
    summary = {key: plan[key] for key in ('id', 'references', 'uninspected')}
    summary['sha256'] = _hash(plan)
    summary['moves'] = [{key: action[key] for key in ('source', 'target', 'blockers', 'tasks')} |
                        {'files': sum(item['kind'] == 'file' for item in action['files'].values()),
                         'bytes': sum(item.get('size', 0) for item in action['files'].values())} for action in plan['moves']]
    summary['edits'] = [{'path': name, 'target': edit['target'], 'blocked': edit['blocked']} for name, edit in plan['edits'].items()]
    summary['status'] = 'needs_review' if any(a['blockers'] for a in plan['moves']) or any(e['blocked'] for e in plan['edits'].values()) else 'ready'
    return summary


def _journal(root, key):
    p._name(key)
    return p._safe(root, f'.dft/organization/{key}/journal.json')


def _save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    for parent in (path.parent, *path.parent.parents):
        parent.chmod(0o700)
        if parent.name == '.dft':
            break
    p._write(path, _encoded(value).decode())
    path.chmod(0o600)


def _copy(source, target, expected):
    """Resume a verified private staging copy; never merge into a public target."""
    if source.is_file():
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.is_file() or digest(target) != expected['.']['sha256']:
            shutil.copy2(source, target)
    else:
        target.mkdir(parents=True, exist_ok=True)
        for relative, item in expected.items():
            if relative == '.':
                continue
            src, dst = source / relative, p._safe(target, relative)
            if item['kind'] == 'directory':
                dst.mkdir(parents=True, exist_ok=True)
            else:
                dst.parent.mkdir(parents=True, exist_ok=True)
                if not dst.is_file() or digest(dst) != item['sha256']:
                    shutil.copy2(src, dst)
        for relative, item in reversed(list(expected.items())):
            if item['kind'] == 'directory':
                shutil.copystat(source / relative, target / relative)
    if _manifest(target) != expected or _manifest(source) != expected:
        raise ValueError('Source changed or copy checksum verification failed; originals preserved')


def _core(spec):
    return {key: spec.get(key, []) for key in ('id', 'moves', 'edits')}


def _expected_after(action, edits):
    result = json.loads(json.dumps(action['files']))
    source = Path(action['source'])
    for name, edit in edits.items():
        if not edit['blocked'] and _inside(Path(name), source):
            item = result[Path(name).relative_to(source).as_posix()]
            content = edit['after'].encode()
            item.update(sha256=hashlib.sha256(content).hexdigest(), size=len(content))
    return result


def _verify(root, journal):
    issues = []
    for index, action in enumerate(journal['plan']['moves']):
        if action['blockers']:
            issues.append(f"{action['source']}: preserved; " + '; '.join(action['blockers']))
            continue
        source, target = _path(root, action['source']), _path(root, action['target'])
        backup = _journal(root, journal['id']).parent / 'originals' / str(index)
        if source.exists():
            issues.append(f"{action['source']}: installation pending; source still present")
        for path, expected, label in ((backup, action['files'], 'retained original'),
                (target, _expected_after(action, journal['plan']['edits']), 'organized target')):
            try:
                if _manifest(path) != expected:
                    issues.append(f"{action['target']}: {label} changed")
            except (OSError, ValueError):
                issues.append(f"{action['target']}: {label} missing or unsafe")
    for name, edit in journal['plan']['edits'].items():
        if edit['blocked']:
            issues.append(f'{name}: reference edit preserved for review')
            continue
        target = _path(root, edit['target'])
        actual = target.read_text() if target.is_file() else None
        expected = edit['after']
        if target.name == 'README.md' and actual is not None:
            actual, expected = (_human_view(text) for text in (actual, expected))
        if actual != expected:
            issues.append(f'{name}: reference update incomplete or changed')
    return issues


def _human_view(text):
    return re.sub(r'<!-- dft-view:start -->.*?<!-- dft-view:end -->', '', text, flags=re.S).strip()


def check(project_root, key):
    root = _root(project_root)
    path = _journal(root, key)
    if not path.is_file():
        raise ValueError('Organization journal missing')
    journal = json.loads(path.read_text())
    issues = _verify(root, journal)
    if journal['state'] not in {'complete', 'partial'}:
        issues.insert(0, 'Organization interrupted; resume with the original preview hash')
    return {'id': key, 'status': 'complete' if not issues else 'needs_review', 'issues': issues,
            'mapping': [{'source': m['source'], 'target': m['target'], 'preserved': bool(m['blockers'])}
                        for m in journal['plan']['moves']]}


def guard_execution(project_root, task_root):
    """Canonical submissions cannot race an unfinished organization scope."""
    root, task = Path(project_root).resolve(), Path(task_root).resolve()
    for path in (root / '.dft/organization').glob('*/journal.json'):
        journal = json.loads(path.read_text())
        if journal.get('state') in {'complete', 'partial'}:
            continue
        for move in journal['plan']['moves']:
            if not move['blockers'] and any(_inside(task, root / move[key]) or _inside(root / move[key], task)
                                             for key in ('source', 'target')):
                raise ValueError('Task belongs to an unfinished organization operation; resume and check first')
        for edit in journal['plan']['edits'].values():
            if not edit['blocked'] and _inside(root / edit['target'], task):
                raise ValueError('Task references are being organized; resume and check first')


def pending_issues(root):
    issues = []
    for path in (root / '.dft/organization').glob('*/journal.json'):
        try:
            value = json.loads(path.read_text())
            if value.get('state') != 'complete':
                issues.append(f"organization {path.parent.name}: pending or preserved items; run organize-check")
        except (OSError, ValueError):
            issues.append(f"organization {path.parent.name}: unreadable journal")
    return issues


def apply(project_root, spec, expected_sha256):
    root = _root(project_root)
    _spec(root, spec)
    path = _journal(root, spec['id'])
    if not path.exists():
        plan = _build(root, spec)
        if expected_sha256 != _hash(plan):
            raise ValueError('Preview changed; review a fresh preview before applying')
        if not any(not a['blockers'] for a in plan['moves']) and not any(not e['blocked'] for e in plan['edits'].values()):
            return {'id': spec['id'], 'status': 'needs_review', 'issues': ['No eligible actions; preserve the tree and resolve preview blockers']}
        journal = {'id': spec['id'], 'scope': _core(spec), 'preview_sha256': expected_sha256,
                   'plan': plan, 'state': 'pending', 'moves_done': [], 'edits_done': []}
    else:
        journal = json.loads(path.read_text())
        if journal['scope'] != _core(spec) or journal['preview_sha256'] != expected_sha256:
            raise ValueError('Existing operation scope differs; resume its original moves/edits and preview hash')
        if journal['state'] in {'complete', 'partial'}:
            return check(root, spec['id'])
    # Lock and recheck exact content before any public destination is modified.
    with p._lock(root):
        if path.exists():
            current = json.loads(path.read_text())
            if current['scope'] != journal['scope'] or current['preview_sha256'] != expected_sha256:
                raise ValueError('Organization journal changed concurrently')
            journal = current
        elif _hash(_build(root, spec)) != expected_sha256:
            raise ValueError('Project changed after preview')
        for index, action in enumerate(journal['plan']['moves']):
            if action['blockers'] or index in journal['moves_done']:
                continue
            source = _path(root, action['source'])
            backup = path.parent / 'originals' / str(index)
            if not backup.exists():
                for task in action['tasks']:
                    reason = _inactive(root, task, spec)
                    if reason:
                        raise ValueError(reason)
                if _manifest(source) != action['files']:
                    raise ValueError('Source changed after preview; retained source will not be overwritten')
            target = _path(root, action['target'])
            if target.exists() and (not backup.exists() or _manifest(target) != action['files']):
                raise ValueError('Destination conflict during resume; contents preserved')
        ignore = root / '.gitignore'
        content = ignore.read_text() if ignore.exists() else ''
        if '.dft/' not in content.splitlines():
            p._write(ignore, content.rstrip() + '\n.dft/\n')
        _save(path, journal)
        for index, action in enumerate(journal['plan']['moves']):
            if action['blockers'] or index in journal['moves_done']:
                continue
            source, target = _path(root, action['source']), _path(root, action['target'])
            backup, staged = path.parent / 'originals' / str(index), path.parent / 'staging' / str(index)
            if not backup.exists():
                _copy(source, staged, action['files'])
                backup.parent.mkdir(parents=True, exist_ok=True)
                if _manifest(source) != action['files']:
                    raise ValueError('Source changed during copying')
                os.rename(source, backup)
            elif _manifest(backup) != action['files']:
                raise ValueError('Retained source changed; inspect before resuming')
            if not target.exists():
                _copy(backup, staged, action['files'])
                target.parent.mkdir(parents=True, exist_ok=True)
                os.rename(staged, target)
            if _manifest(target) != action['files']:
                raise ValueError('Installed target failed verification')
            journal['moves_done'].append(index); _save(path, journal)
        for name, edit in journal['plan']['edits'].items():
            if edit['blocked'] or name in journal['edits_done']:
                continue
            target = _path(root, edit['target'])
            before, after = edit['before'].encode(), edit['after'].encode()
            if target.read_bytes() not in {before, after}:
                raise ValueError('Reference document changed; preserve both versions and merge explicitly')
            saved = path.parent / 'text-originals' / hashlib.sha256(name.encode()).hexdigest()
            if not saved.exists():
                p._write(saved, edit['before'])
            mode = target.stat().st_mode & 0o777
            p._write(target, edit['after']); target.chmod(mode)
            journal['edits_done'].append(name); _save(path, journal)
        issues = _verify(root, journal)
        blocked_issues = sum(bool(a['blockers']) for a in journal['plan']['moves']) + sum(e['blocked'] for e in journal['plan']['edits'].values())
        if len(issues) != blocked_issues:
            raise ValueError('Organization verification incomplete; inspect organize-check and resume')
        journal['state'] = 'views_pending'
        _save(path, journal)
    # Human summaries are derived once, outside the mutation lock.
    if (root / PROJECT_FILE).is_file():
        from .readmes import refresh
        for action in journal['plan']['moves']:
            if action['blockers']:
                continue
            route = route_for(root / action['target'])
            if route and project_role(root) != 'cluster':
                p.append_event(root, route[0], 'organize_' + spec['id'] + '_' + _hash(action)[:8],
                    f"Organized {action['source']} → {action['target']}; original bytes retained in the private operation journal.", [], refresh_views=False)
        # Root/route navigation changes; moved stage files remain byte-bound to the preview.
        refresh(root, scopes={root, *(root / r['path'] for r in project_routes(root))})
    with p._lock(root):
        issues = _verify(root, journal)
        blocked_issues = sum(bool(a['blockers']) for a in journal['plan']['moves']) + sum(e['blocked'] for e in journal['plan']['edits'].values())
        if len(issues) != blocked_issues:
            raise ValueError('Organization views need inspection; repeat apply to resume')
        journal['state'] = 'partial' if issues else 'complete'
        _save(path, journal)
    return check(root, spec['id'])
