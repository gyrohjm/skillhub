"""Export only executable facts; reconcile cluster edits against the local plan."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import shutil
import sys

CONTRACTS = Path(__file__).resolve().parents[2] / 'dft-contracts'
if str(CONTRACTS) not in sys.path:
    sys.path.insert(0, str(CONTRACTS))
from dft_contracts import paired as pair
from dft_contracts import project as records
from dft_contracts.layout import PROJECT_FILE, project_role, discover_workspace, route_for, stage_root
from dft_contracts.project_transport import digest, info

DESIGN_KEYS = ('design_id', 'revision', 'approval_ref', 'design_sha256', 'draft', 'matrix_id',
               'matrix_class', 'engine_parameters', 'completion_gate', 'baseline_parameter_hash')
WORKFLOW_KEYS = ('schema_version', 'contract', 'task_uuid', 'composition_slug', 'structure_slug',
                 'task_slug', 'variant_slug', 'status', 'engine', 'updated_at', 'stage', 'engine_backend',
                 'primary_input', 'input_authority', 'resources', 'resource_profile', 'job', 'input_snapshot',
                 'submission', 'completion', 'attempts')


def preparation_root(root):
    return records._safe(root, '.dft/preparation')


def prepare_workspace(project_root, composition, structure, *, history_path=None, event_id=None,
                      design_path=None, resource_document=Path('docs/project-resources.md'),
                      resource_profile=None, draft=False, route=None):
    import canonical_workflow as cw
    root = pair.local_root(project_root)
    selected = route_for(root / route if route else root, composition, structure)
    if not selected:
        raise ValueError('Register the research route before preparing paired inputs')
    relative = selected[0].relative_to(root)
    design = records._safe(root, design_path.relative_to(root) if isinstance(design_path, Path) and design_path.is_absolute()
                           else design_path or relative / 'docs/calculation_design.json')
    value = json.loads(design.read_text())
    shadow = preparation_root(root)
    shadow.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((root / PROJECT_FILE).read_text())
    pair.write_json(shadow / PROJECT_FILE, dict(manifest, storage_role='preparation'))
    paths = {design, records._safe(root, resource_document.relative_to(root) if isinstance(resource_document, Path)
                                 and resource_document.is_absolute() else resource_document)}
    history = Path(history_path) if history_path else design.parent / 'history.jsonl'
    if not history.is_absolute():
        history = root / history
    if history.exists():
        paths.add(history)
    for task in value['execution_plan']['tasks']:
        for item in task['inputs']:
            if item['mode'] == 'static':
                paths.add(cw.workspace_path(root, item['source'], 'input source'))
        if task.get('job_script'):
            paths.add(cw.workspace_path(root, task['job_script'], 'job template'))
    for source in paths:
        destination = records._safe(shadow, source.relative_to(root))
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    return cw.initialize_workflow_tree(shadow, composition, structure,
        history_path=history.relative_to(root) if history.exists() and not draft else None,
        event_id=event_id, design_path=design.relative_to(root),
        resource_document=Path(resource_document).relative_to(root) if Path(resource_document).is_absolute() else resource_document,
        resource_profile=resource_profile, draft=draft, route=relative.as_posix())


def bind_workspace(project_root, composition, structure, *, history_path=None, event_id=None, route=None):
    import approval_binding
    root = pair.local_root(project_root)
    selected = route_for(root / route if route else root, composition, structure)
    relative = selected[0].relative_to(root)
    shadow = preparation_root(root)
    for name in ('calculation_design.json', 'history.jsonl'):
        source = root / relative / 'docs' / name
        destination = records._safe(shadow, source.relative_to(root))
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    return approval_binding.bind_approval(shadow, composition, structure, event_id=event_id, route=relative.as_posix())


def operational_workflow(workflow):
    result = {key: copy.deepcopy(workflow[key]) for key in WORKFLOW_KEYS if key in workflow}
    result['design'] = {key: copy.deepcopy(workflow['design'][key]) for key in DESIGN_KEYS if key in workflow['design']}
    result['inputs'] = {'materialization': workflow['inputs']['materialization'], 'files': []}
    for item in workflow['inputs']['files']:
        result['inputs']['files'].append({key: copy.deepcopy(item[key]) for key in
            ('name', 'base', 'path', 'role', 'mode', 'authority', 'sha256', 'source_task', 'artifact') if key in item})
    result['dependencies'] = [{key: copy.deepcopy(item[key]) for key in
        ('task_ref', 'required_artifacts', 'gate_status', 'expected_hashes') if key in item} for item in workflow.get('dependencies', [])]
    result['lineage'] = {key: copy.deepcopy(workflow.get('lineage', {}).get(key)) for key in ('derived_from', 'derived_from_uuid', 'supersedes')}
    result['parameter_reconciliation'] = {'status': 'synchronized', 'changed_parameters': [], 'affected_tasks': []}
    result['result'] = {'status': 'not_started', 'summary': None}
    result['history'] = [{key: item[key] for key in ('at', 'status', 'attempt_id') if key in item}
                         for item in workflow.get('history', [])]
    # Resource data is machine-local execution configuration, never published to local Git.
    result.get('resources', {}).pop('document', None)
    result.get('resources', {}).pop('document_sha256', None)
    result['resource_profile'] = {'ref': 'workspace_root:.dft/resource-profile.json', 'overrides': {}}
    return result


def _stable(workflow):
    return {'task_uuid': workflow['task_uuid'], 'engine': workflow['engine'], 'stage': workflow['stage'],
            'design': {key: workflow['design'].get(key) for key in DESIGN_KEYS if key != 'baseline_parameter_hash'},
            'inputs': [{key: item.get(key) for key in ('name', 'base', 'path', 'mode', 'source_task', 'artifact')}
                       for item in workflow['inputs']['files']],
            'job': workflow.get('job'), 'resources': workflow.get('resources'),
            'dependencies': [{key: item.get(key) for key in ('task_ref', 'required_artifacts', 'expected_hashes')}
                             for item in workflow.get('dependencies', [])]}


def execution_snapshot(local, task, workflow, *, reconciled=False):
    import canonical_workflow as cw
    import input_reconciliation as ir
    route = route_for(local / task)
    if not route:
        raise ValueError('Executable task is outside a registered route')
    plan = route[0] / 'docs/calculation_design.json'
    design = json.loads(plan.read_text())
    approval = None
    if not workflow['design'].get('draft'):
        reference = workflow['design'].get('approval_ref', '')
        if '#' not in reference:
            raise ValueError('Missing real scientific approval')
        approval, approved, matrix, approved_envelope, history = cw.verify_design_approval(local,
            plan.parent / 'history.jsonl', reference.split('#', 1)[1], workflow['design']['matrix_id'],
            workflow['stage'], workflow['engine'], workflow['composition_slug'], workflow['structure_slug'])
        if not reconciled and workflow['design'].get('design_sha256') != approval['design_sha256']:
            raise ValueError('Prepared inputs are not bound to the verified approval')
    envelope = next((e for e in design.get('engine_stage_envelopes', [])
                     if e['matrix_id'] == workflow['design'].get('matrix_id') and e['engine'] == workflow['engine']), None)
    if not envelope or not ir._same_value(envelope['engine_parameters'], workflow['design']['engine_parameters']):
        raise ValueError('Task parameters differ from the current local plan; reconcile first')
    return {'schema_version': 1, 'project_id': json.loads((local / PROJECT_FILE).read_text())['project_id'],
            'task': task, 'authorized': approval is not None, 'facts': _stable(workflow),
            'source': {'design_sha256': cw._load_design_verifier().canonical_json_sha256(design),
                       'approval_event': approval.get('event_id') if approval else None,
                       'approval_sha256': approval.get('design_sha256') if approval else None,
                       'scope': approval.get('scope', []) if approval else []}}


def deploy_task(project_root, task_root, *, endpoint=None):
    import canonical_workflow as cw
    import input_reconciliation as ir
    local = pair.local_root(project_root)
    source = Path(task_root).resolve()
    source_root = discover_workspace(source)
    if source_root != preparation_root(local):
        raise ValueError('Deploy from this project’s private preparation workspace')
    task = source.relative_to(source_root).as_posix()
    workflow = json.loads((source / 'workflow.json').read_text())
    if workflow['status'] not in {'planned', 'prepared', 'awaiting_upstream'} or workflow.get('attempts'):
        raise ValueError('Deploy only unsubmitted input candidates')
    endpoint = endpoint or pair.endpoint_for(local)
    pair.check_remote(local, endpoint)
    current_blob = endpoint.read(task + '/workflow.json', optional=True)
    current = json.loads(current_blob) if current_blob else None
    if current and (current.get('task_uuid') != workflow['task_uuid'] or current.get('attempts')
                    or current.get('status') not in {'planned', 'prepared', 'awaiting_upstream'}):
        raise ValueError('Existing cluster execution is not an overwrite target')
    result = operational_workflow(workflow)
    snapshot = execution_snapshot(local, task, result)
    # Approval metadata is not enough: bind only the actual reviewed bytes.
    baseline = workflow.get('input_snapshot', {})
    current_inputs = cw.parse_current_inputs(workflow['engine'], source,
        primary_input=cw.snapshot_primary_input(source, workflow), previous_snapshot=baseline)
    if (ir.semantic_diff(baseline, current_inputs)
            or current_inputs.get('file_hashes') != baseline.get('file_hashes')):
        raise ValueError('Prepared input changed after review; reconcile locally before deployment')
    inputs = [(item['path'], cw._submission_child(source, item['path'], 'deployment input'))
              for item in workflow['inputs']['files'] if cw._submission_child(source, item['path'], 'deployment input').is_file()]
    job = cw._job_script_path(source, workflow, required=False)
    if job.is_file():
        inputs.append((job.relative_to(source).as_posix(), job))
    snapshot['hashes'] = {name: digest(path) for name, path in inputs}
    state_path = local / '.dft/deployments.json'
    states = pair.read_json(state_path, {})
    state = states.get(task, {'files': {}})
    # Preflight every destination before uploading any input.
    for name, path in inputs:
        metadata = endpoint.stat(task + '/' + name)
        if metadata and metadata['sha256'] not in {state['files'].get(name), snapshot['hashes'][name]}:
            raise ValueError('Cluster input differs from the previous deployment; reconcile, do not overwrite')
    snapshot_bytes = pair.encoded(snapshot)
    snapshot_hash = hashlib.sha256(snapshot_bytes).hexdigest()
    snapshot_name = f'.dft/execution/{workflow["task_uuid"]}/{snapshot_hash}.json'
    result['execution'] = {'path': snapshot_name, 'sha256': snapshot_hash}
    state['state'] = 'pending'; states[task] = state; pair.write_json(state_path, states)
    for name, path in inputs:
        endpoint.put(task + '/' + name, path, expected=state['files'].get(name))
        state['files'][name] = snapshot['hashes'][name]
        pair.write_json(state_path, states)
    endpoint.write(snapshot_name, snapshot_bytes)
    endpoint.write(task + '/workflow.json', pair.encoded(result),
                   expected=hashlib.sha256(current_blob).hexdigest() if current_blob else None)
    stage = stage_root(local / task).relative_to(local).as_posix()
    if endpoint.read(stage + '/README.md', optional=True) is None:
        endpoint.write(stage + '/README.md', b'# Task stage\n\n## Purpose\n\nDescribe the task.\n\n## Files and use\n\nInputs and raw outputs stay here; scripts/, data/ and figures/ belong to this stage.\n')
    state.update(state='complete', execution_sha256=snapshot_hash)
    pair.write_json(state_path, states)
    pair.sync_pair(local, endpoint=endpoint)
    return {'task': task, 'status': 'deployed', 'authorized': snapshot['authorized']}


def check_execution(task_root, workflow, *, write=True):
    """Fail closed on cluster edits without loading any human planning documents."""
    import canonical_workflow as cw
    import input_reconciliation as ir
    root = discover_workspace(task_root)
    execution = workflow.get('execution', {})
    path = records._safe(root, execution.get('path', ''))
    if not path.is_file() or digest(path) != execution.get('sha256'):
        raise cw.WorkflowError('Missing or changed local-bound execution snapshot')
    snapshot = json.loads(path.read_text())
    if (not snapshot.get('authorized') or snapshot['project_id'] != json.loads((root / PROJECT_FILE).read_text())['project_id']
            or snapshot['task'] != Path(task_root).relative_to(root).as_posix()
            or snapshot['facts'] != _stable(workflow)):
        raise cw.WorkflowError('Execution identity, parameters, dependencies or authority changed; reconcile locally')
    changes = []
    for name, expected in snapshot['hashes'].items():
        file = cw._submission_child(Path(task_root), name, 'bound input')
        actual = digest(file) if file.is_file() else None
        if actual != expected:
            changes.append({'file': name, 'old_sha256': expected, 'new_sha256': actual})
    current = cw.parse_current_inputs(workflow['engine'], Path(task_root),
        primary_input=cw.snapshot_primary_input(Path(task_root), workflow), previous_snapshot=workflow.get('input_snapshot'))
    differences = ir.semantic_diff(workflow.get('input_snapshot', {}), current)
    pending_recipes = ir._recipe_input_names(workflow)
    differences = [d for d in differences if not (d['name'] in pending_recipes and d.get('old') is None)]
    pending_primary = workflow.get('primary_input') in pending_recipes and not current.get('file_hashes')
    parse_errors = current.get('parse_errors', [])
    if pending_primary:
        parse_errors = [error for error in parse_errors if error != 'no Quantum ESPRESSO .in input exists']
    if parse_errors or changes or differences:
        if write:
            pair.write_json(root / '.dft/input-drift' / (workflow['task_uuid'] + '.json'),
                {'task': snapshot['task'], 'input_changes': changes, 'parameter_changes': differences,
                 'verdict': 'NEEDS_AGENT', 'reason': 'local_plan_reconciliation_required'})
        return {'verdict': 'NEEDS_AGENT', 'changed_parameters': differences, 'input_changes': changes}
    return {'verdict': 'ADVANCE', 'changed_parameters': []}


def reconcile_remote(project_root, task, *, endpoint=None, event_id=None):
    import canonical_workflow as cw
    import input_reconciliation as ir
    local = pair.local_root(project_root)
    records._safe(local, task)
    endpoint = endpoint or pair.endpoint_for(local)
    pair.check_remote(local, endpoint)
    blob = endpoint.read(task + '/workflow.json')
    workflow = json.loads(blob)
    if workflow['status'] not in {'planned', 'prepared', 'awaiting_upstream', 'awaiting_user_decision'} or workflow.get('attempts'):
        raise ValueError('Preserve running/finished snapshots; create an explicit scientific rerun')
    route = route_for(local / task)
    if not route:
        raise ValueError('Unknown route')
    shadow = preparation_root(local)
    shadow.mkdir(parents=True, exist_ok=True)
    pair.write_json(shadow / PROJECT_FILE, dict(pair.read_json(local / PROJECT_FILE), storage_role='preparation'))
    leaf = records._safe(shadow, task)
    leaf.mkdir(parents=True, exist_ok=True)
    # Pull known ledgers so existing downstream impact handling can see the graph.
    old_ledgers = {}
    for path in endpoint.workflows(route[0].relative_to(local).as_posix()):
        content = endpoint.read(path)
        old_ledgers[path] = content
        records._write(records._safe(shadow, path), content.decode())
    inputs = [item['path'] for item in workflow['inputs']['files']]
    job = workflow.get('job', {}).get('script', '').removeprefix('task_root:')
    if job:
        inputs.append(job)
    observed = {}
    deployed = pair.read_json(local / '.dft/deployments.json', {}).get(task, {}).get('files', {})
    for name in inputs:
        destination = records._safe(leaf, name)
        metadata = endpoint.stat(task + '/' + name)
        if metadata is None:
            if any(item['path'] == name and item.get('mode') == 'recipe' for item in workflow['inputs']['files']):
                continue
            raise ValueError('Cluster input missing')
        existing = info(destination)
        baseline = next((item.get('sha256') for item in workflow['inputs']['files'] if item['path'] == name), None)
        if existing and existing['sha256'] not in {deployed.get(name), baseline, metadata['sha256']}:
            raise ValueError('Local prepared copy was edited; reconcile both versions before downloading')
        endpoint.fetch(task + '/' + name, destination, metadata, expected=existing['sha256'] if existing else None)
        observed[name] = metadata['sha256']
    plan = route[0] / 'docs/calculation_design.json'
    old_execution = workflow.get('execution', {})
    bound_bytes = endpoint.read(old_execution['path']) if old_execution.get('path') else None
    if bound_bytes and hashlib.sha256(bound_bytes).hexdigest() != old_execution.get('sha256'):
        raise ValueError('Execution snapshot changed; restore its verified version before reconciliation')
    bound = json.loads(bound_bytes) if bound_bytes else None
    if bound:
        facts = _stable(workflow)
        for field in ('engine', 'stage', 'inputs', 'dependencies', 'resources', 'job'):
            if bound['facts'].get(field) != facts.get(field):
                raise ValueError('Execution metadata changed; review the local design and prepare a new candidate')
        if (bound['facts']['task_uuid'] != workflow['task_uuid']
                and workflow.get('lineage', {}).get('derived_from_uuid') != bound['facts']['task_uuid']):
            raise ValueError('Execution identity changed without an explicit rerun')
        if not event_id and bound['facts']['design'] != facts['design']:
            raise ValueError('Design binding changed; restore it or provide a reviewed local approval')
    preview = ir.reconcile_task(leaf, plan, write=False)
    if preview.get('parse_errors') and not (workflow.get('primary_input') in ir._recipe_input_names(workflow)
                                           and preview['parse_errors'] == ['no Quantum ESPRESSO .in input exists']):
        return dict(preview, verdict='NEEDS_AGENT')
    if not event_id and bound and bound.get('facts') == _stable(workflow) and bound.get('hashes') == observed:
        execution_snapshot(local, task, workflow, reconciled=True)
        return dict(preview, status='synchronized')
    if job and bound and observed.get(job) != bound.get('hashes', {}).get(job):
        raise ValueError('Launcher changed; review resources and redeploy a locally prepared launcher')
    if event_id:
        approval, design, matrix, envelope, history = cw.verify_design_approval(local,
            plan.parent / 'history.jsonl', event_id, workflow['design']['matrix_id'], workflow['stage'],
            workflow['engine'], workflow['composition_slug'], workflow['structure_slug'])
        available = {item['name']: leaf / item['path'] for item in workflow['inputs']['files'] if (leaf / item['path']).is_file()}
        cw.validate_engine_inputs(workflow['engine'], available, envelope['engine_parameters'], workflow.get('primary_input'))
        workflow['design'].update(engine_parameters=envelope['engine_parameters'], revision=approval['revision'],
            approval_ref=f'workspace_root:{history.relative_to(local)}#{event_id}', design_sha256=approval['design_sha256'], draft=False)
        workflow['status'] = 'awaiting_upstream' if workflow.get('dependencies') else 'prepared'
        workflow['input_snapshot'] = cw.parse_current_inputs(workflow['engine'], leaf,
            primary_input=cw.snapshot_primary_input(leaf, workflow), previous_snapshot=workflow.get('input_snapshot'))
        workflow['design']['baseline_parameter_hash'] = workflow['input_snapshot']['parameter_hash']
        pair.write_json(leaf / 'workflow.json', workflow)
        result = {'verdict': 'ADVANCE', 'changed_parameters': []}
    else:
        result = ir.reconcile_task(leaf, plan, write=True)
    if result['verdict'] != 'ADVANCE':
        key = 'review_' + hashlib.sha256(pair.encoded({'task': task, 'inputs': observed, 'verdict': result['verdict']})).hexdigest()[:20]
        records.append_event(local, local / task, key,
            f'Input review blocked for {task}: {result["verdict"]}. Resolve the recorded parameter differences locally.', [])
        return result
    updated = pair.read_json(leaf / 'workflow.json')
    snapshot = execution_snapshot(local, task, updated, reconciled=True)
    snapshot['hashes'] = observed
    encoded = pair.encoded(snapshot)
    sha = hashlib.sha256(encoded).hexdigest()
    path = f'.dft/execution/{workflow["task_uuid"]}/{sha}.json'
    updated.pop('pending_input_snapshot', None)
    updated['execution'] = {'path': path, 'sha256': sha}
    updated['design'].pop('path', None)
    for name, wanted in observed.items():
        if endpoint.stat(task + '/' + name)['sha256'] != wanted:
            raise ValueError('Cluster inputs changed during local reconciliation; repeat review')
    if endpoint.read(task + '/workflow.json') != blob:
        raise ValueError('Cluster task changed during local reconciliation')
    endpoint.write(path, encoded)
    endpoint.write(task + '/workflow.json', pair.encoded(updated), expected=hashlib.sha256(blob).hexdigest())
    for name, previous in old_ledgers.items():
        if name == task + '/workflow.json':
            continue
        current = records._safe(shadow, name).read_bytes()
        if current != previous:
            endpoint.write(name, current, expected=hashlib.sha256(previous).hexdigest())
    key = 'reconcile_' + sha[:20]
    records.append_event(local, route[0], key, f'Local input review completed for {task}.', [str(plan.relative_to(local))])
    pair.sync_pair(local, endpoint=endpoint)
    return result
