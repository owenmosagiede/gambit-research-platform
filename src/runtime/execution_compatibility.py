"""Explicit, immutable execution approval for one frozen program and exact cohort.

Proposals are inert. This module never grants approval, changes an envelope, or
infers execution permission from the ordinary result-reuse release registry.
"""
from copy import deepcopy
from datetime import datetime
import re

from research.contracts import canonical, digest, ref, request_id, ResearchConflict
from research.store import inside, read_json, install_bytes

BASE = 'storage/catalog/operations/execution_compatibility'
PROPOSAL_SCHEMA = 'frozen_program_execution_proposal_v1'
SUCCESSOR_SCHEMA = 'frozen_program_execution_proposal_v2'
APPROVAL_SCHEMA = 'frozen_program_execution_approval_v1'
SCOPES = ['intake', 'pending_execution']


def _require(value, message):
    if not value:
        raise ResearchConflict('Execution compatibility: ' + message)


def _hash(value):
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value) is not None


def _seal(prefix, body):
    return dict(body, id=prefix + '_' + digest(body))


def _identity(value, prefix):
    _require(type(value) is dict and value.get('id') == prefix + '_' +
             digest({k: v for k, v in value.items() if k != 'id'}), 'record identity differs')


def _implementation(value):
    _require(type(value) is dict and set(value) == {'profile', 'files', 'numeric_environment', 'fingerprint'},
             'complete implementation required')
    _require(type(value['files']) is dict and bool(value['files']) and
             all(isinstance(k, str) and _hash(v) for k, v in value['files'].items()) and
             value['fingerprint'] == digest(value['files']), 'implementation fingerprint differs')
    _require(type(value['numeric_environment']) is dict and
             isinstance(value['numeric_environment'].get('python'), str), 'Python environment required')


def make_proposal(*, manifest_sha256, operator_sha256, from_implementation,
                  to_implementation, cohort, evidence, source_archive_sha256,
                  target_archive_sha256, predecessor_approval=None,
                  historical_trial_implementations=None):
    """Create an inert proposal. No approval or store write is performed."""
    body = {'schema': PROPOSAL_SCHEMA, 'version': '1.0.0',
        'state': 'proposed', 'manifest_sha256': manifest_sha256,
        'operator_sha256': operator_sha256, 'from_implementation': deepcopy(from_implementation),
        'to_implementation': deepcopy(to_implementation), 'scopes': SCOPES,
        'cohort': deepcopy(cohort), 'evidence': deepcopy(evidence),
        'source_archive_sha256': source_archive_sha256, 'target_archive_sha256': target_archive_sha256}
    if predecessor_approval is not None:
        body.update(schema=SUCCESSOR_SCHEMA, version='2.0.0',
                    predecessor_approval=deepcopy(predecessor_approval),
                    historical_trial_implementations=deepcopy(historical_trial_implementations))
    else:
        _require(historical_trial_implementations is None, 'historical executor pins require a predecessor')
    value = _seal('EXECPROPOSAL', body)
    return validate_proposal(value)


def validate_proposal(value, *, _depth=0):
    _require(_depth < 16, 'approval chain exceeds review bound')
    _identity(value, 'EXECPROPOSAL')
    successor = value.get('schema') == SUCCESSOR_SCHEMA
    extra = {'predecessor_approval', 'historical_trial_implementations'} if successor else set()
    _require(set(value) == {'id', 'schema', 'version', 'state', 'manifest_sha256', 'operator_sha256',
        'from_implementation', 'to_implementation', 'scopes', 'cohort', 'evidence',
        'source_archive_sha256', 'target_archive_sha256'} | extra, 'unexpected proposal fields')
    _require((value['schema'], value['version']) in
             ((PROPOSAL_SCHEMA, '1.0.0'), (SUCCESSOR_SCHEMA, '2.0.0')) and
             value['state'] == 'proposed' and value['scopes'] == SCOPES, 'proposal contract differs')
    for name in ('manifest_sha256', 'operator_sha256', 'source_archive_sha256', 'target_archive_sha256'):
        _require(_hash(value[name]), 'exact ' + name + ' required')
    for name in ('from_implementation', 'to_implementation'):
        _implementation(value[name])
    _require(value['from_implementation'] != value['to_implementation'], 'identical implementations need no approval')
    _require(type(value['evidence']) is dict and set(value['evidence']) == {'equivalence_sha256', 'tests_sha256'} and
             all(_hash(v) for v in value['evidence'].values()), 'exact equivalence/test evidence required')
    rows = value['cohort']
    _require(type(rows) is list and bool(rows), 'nonempty frozen cohort required')
    seen = set()
    for row in rows:
        _require(type(row) is dict and set(row) == {'request_id', 'canonical_request_id', 'intent_sha256',
            'scientific_identity', 'submission_sha256', 'committed_trials'}, 'cohort fields differ')
        request_id(row['request_id']); request_id(row['canonical_request_id'])
        _require(row['request_id'] not in seen, 'duplicate cohort UUID')
        seen.add(row['request_id'])
        _require(_hash(row['intent_sha256']) and _hash(row['scientific_identity']) and
                 (row['submission_sha256'] is None or _hash(row['submission_sha256'])), 'cohort pins differ')
        _require(type(row['committed_trials']) is list, 'committed trial references required')
        trial_ids = set()
        for binding in row['committed_trials']:
            _require(type(binding) is dict and set(binding) == {'id', 'version', 'content_sha256'} and
                     re.fullmatch('TRIAL_[0-9a-f]{64}', binding['id']) and binding['version'] == '1.0.0' and
                     _hash(binding['content_sha256']) and binding['id'] not in trial_ids, 'invalid/duplicate trial reference')
            trial_ids.add(binding['id'])
        _require(row['submission_sha256'] is not None or not row['committed_trials'],
                 'unaccepted entry cannot own committed trials')
    if successor:
        previous = validate_approval(value['predecessor_approval'], _depth=_depth + 1)
        prior = previous['proposal']
        _require(all(value[k] == prior[k] for k in
                     ('manifest_sha256', 'operator_sha256', 'from_implementation')),
                 'successor changes the original frozen program')
        _require(value['to_implementation'] not in requested_implementations(previous),
                 'successor must use a distinct executor; reverse migration needs separate review')
        prior_rows = {r['request_id']: r for r in prior['cohort']}
        _require(set(prior_rows) == seen, 'successor cohort differs from predecessor')
        all_trials = {r['id'] for row in rows for r in row['committed_trials']}
        generations = value['historical_trial_implementations']
        _require(type(generations) is dict and set(generations) == all_trials,
                 'exact executor reference required for every historical trial')
        for binding in generations.values():
            _require(type(binding) is dict and set(binding) == {'id', 'version', 'content_sha256'} and
                     isinstance(binding['id'], str) and
                     re.fullmatch('RESEARCHIMPLEMENTATION_[0-9a-f]{64}', binding['id']) and
                     isinstance(binding['version'], str) and _hash(binding['content_sha256']),
                     'invalid historical executor reference')
        for row in rows:
            before = prior_rows[row['request_id']]
            _require(all(row[k] == before[k] for k in
                         ('canonical_request_id', 'intent_sha256', 'scientific_identity')) and
                     (before['submission_sha256'] is None or
                      row['submission_sha256'] == before['submission_sha256']),
                     'successor changes an existing envelope or scientific identity')
            _require(all(binding in row['committed_trials'] for binding in before['committed_trials']),
                     'successor omits or changes predecessor trial references')
        if prior['schema'] == SUCCESSOR_SCHEMA:
            _require(all(generations.get(k) == v for k, v in prior['historical_trial_implementations'].items()),
                     'successor relabels a historical executor')
    return value


def validate_approval(value, *, _depth=0):
    _identity(value, 'EXECAPPROVAL')
    _require(set(value) == {'id', 'schema', 'version', 'decision', 'proposal', 'approval'}, 'unexpected approval fields')
    _require(value['schema'] == APPROVAL_SCHEMA and value['version'] == '1.0.0' and
             value['decision'] == 'equivalent_execution', 'explicit execution approval required')
    validate_proposal(value['proposal'], _depth=_depth)
    approval = value['approval']
    _require(type(approval) is dict and set(approval) == {'approved_by', 'approved_at', 'decision_reference'} and
             all(isinstance(v, str) and v.strip() for v in approval.values()), 'human approval evidence required')
    try:
        timestamp = datetime.fromisoformat(approval['approved_at'])
        _require(timestamp.tzinfo is not None, 'approval timestamp requires timezone')
    except ValueError as exc:
        raise ResearchConflict('Execution compatibility: invalid approval time') from exc
    return value


def source_implementation(proposal):
    """The installed predecessor is distinct from the unchanged original pins."""
    previous = proposal.get('predecessor_approval')
    return previous['proposal']['to_implementation'] if previous else proposal['from_implementation']


def requested_implementations(approval):
    values = [approval['proposal']['to_implementation']]
    current = approval
    while current['proposal'].get('predecessor_approval'):
        current = current['proposal']['predecessor_approval']
        values.append(current['proposal']['to_implementation'])
    return values + [current['proposal']['from_implementation']]


def verify_predecessor(root, approval):
    previous = approval['proposal'].get('predecessor_approval')
    if previous is not None:
        _require(resolve(root, ref(previous)) == previous, 'installed predecessor approval differs')


def historical_executor_matches(approval, trial, implementation, *, original=None):
    proposal = approval['proposal']
    if proposal['schema'] == SUCCESSOR_SCHEMA:
        return (trial['scientific_key']['implementation'] == ref(implementation) ==
                proposal['historical_trial_implementations'].get(trial['id']))
    # Older historical aliases can have an older original executor. The status
    # reader supplies that immutable envelope; pending execution uses from.
    expected = original['implementation'] if original is not None else proposal['from_implementation']
    return implementation['body'] == expected


def approval_path(root, value):
    # An older executor must still be able to start after code-only recovery.
    # Its v1 reader never enters this new append-only namespace.
    folder = 'successor_approvals' if value['proposal']['schema'] == SUCCESSOR_SCHEMA else 'approvals'
    return inside(root, BASE + '/' + folder + '/' + value['id'] + '.json')


def install_approval(root, value):
    """Publish an already explicitly approved record; never convert a proposal."""
    validate_approval(value)
    verify_predecessor(root, value)
    install_bytes(approval_path(root, value), canonical(value) + b'\n')
    return ref(value)


def resolve(root, binding):
    _require(type(binding) is dict and set(binding) == {'id', 'version', 'content_sha256'} and
             isinstance(binding['id'], str) and re.fullmatch('EXECAPPROVAL_[0-9a-f]{64}', binding['id']),
             'exact approval reference required')
    paths = [inside(root, BASE + '/' + folder + '/' + binding['id'] + '.json')
             for folder in ('approvals', 'successor_approvals')]
    found = [p for p in paths if p.exists()]
    _require(len(found) <= 1, 'duplicate approval publication')
    path = found[0] if found else paths[0]
    value = validate_approval(read_json(path))
    _require(ref(value) == binding and path == approval_path(root, value) and
             path.read_bytes() == canonical(value) + b'\n', 'approval bytes/reference differ')
    verify_predecessor(root, value)
    return value


def approvals(root):
    for folder in ('approvals', 'successor_approvals'):
        for path in sorted(inside(root, BASE + '/' + folder).glob('*.json')):
            value = validate_approval(read_json(path))
            _require(path == approval_path(root, value) and path.read_bytes() == canonical(value) + b'\n',
                     'noncanonical approval publication')
            verify_predecessor(root, value)
            yield value


def row_for(approval, rid, *, canonical=False):
    field = 'canonical_request_id' if canonical else 'request_id'
    rows = [r for r in approval['proposal']['cohort'] if r[field] == rid]
    _require(bool(rows), 'request absent from approved cohort')
    # Multiple program aliases may point to one immutable historical request.
    pins = [{k: v for k, v in r.items() if k != 'request_id'} for r in rows]
    _require(all(v == pins[0] for v in pins), 'ambiguous canonical cohort request')
    return rows[0]


def _check_packet(row, packet):
    from runtime.experiment_identity import scientific_key
    _require(digest(packet['intent']) == row['intent_sha256'] and
             scientific_key(packet) == row['scientific_identity'], 'frozen scientific inputs differ')


def validate_cohort_packet(approval, rid, packet):
    row = row_for(approval, rid)
    _check_packet(row, packet)
    return row


def validate_cohort_envelope(approval, rid, original):
    row = validate_cohort_packet(approval, rid, original)
    _require(original['request_id'] == row['canonical_request_id'] and
             original['record_sha256'] == digest({k: v for k, v in original.items() if k != 'record_sha256'}),
             'canonical envelope identity/checksum differs')
    if row['submission_sha256'] is not None:
        _require(original['record_sha256'] == row['submission_sha256'], 'canonical historical envelope differs')
    else:
        _require(original['implementation'] == approval['proposal']['to_implementation'] and
                 original.get('execution_compatibility') == ref(approval),
                 'new envelope lacks this exact approved intake provenance')
    return row


def for_program(root, *, manifest_sha256, operator_sha256, actual_implementation, binding=None):
    candidates = [resolve(root, binding)] if binding else list(approvals(root))
    matches = [a for a in candidates if a['proposal']['manifest_sha256'] == manifest_sha256 and
        a['proposal']['operator_sha256'] == operator_sha256 and
        a['proposal']['to_implementation'] == actual_implementation]
    _require(len(matches) == 1, 'one exact program/operator/executor approval required')
    return matches[0]


def authorize_intake(root, rid, packet, *, original=None, binding=None):
    """A scoped result-reuse bridge, never a global release-equivalence override."""
    candidates = [resolve(root, binding)] if binding else list(approvals(root))
    matches = []
    for approval in candidates:
        p = approval['proposal']
        if p['to_implementation'] != packet['implementation']:
            continue
        rows = [r for r in p['cohort'] if r['request_id'] == rid]
        if not rows:
            continue
        row = rows[0]; _check_packet(row, packet)
        if original is not None:
            validate_cohort_envelope(approval, rid, original)
        matches.append(approval)
    _require(len(matches) <= 1, 'ambiguous execution approvals')
    if binding:
        _require(bool(matches), 'intake is outside approved cohort')
    return matches[0] if matches else None


def authorize_execution(root, submission, actual_implementation):
    if submission['implementation'] == actual_implementation:
        if submission.get('execution_compatibility'):
            return authorize_intake(root, submission['request_id'], submission,
                                    binding=submission['execution_compatibility'])
        return None
    matches = []
    for approval in approvals(root):
        p = approval['proposal']
        if submission['implementation'] not in requested_implementations(approval) or p['to_implementation'] != actual_implementation:
            continue
        rows = [r for r in p['cohort'] if r['canonical_request_id'] == submission['request_id']]
        if not rows:
            continue
        row = row_for(approval, submission['request_id'], canonical=True); _check_packet(row, submission)
        _require(row['submission_sha256'] == submission['record_sha256'], 'frozen submission checksum differs')
        matches.append(approval)
    _require(len(matches) == 1, 'exact pending-execution approval missing or ambiguous')
    return matches[0]


def record_execution(root, approval, submission, actual, attempt_id):
    body = {'schema': 'frozen_program_execution_attempt_v1', 'version': '1.0.0',
        'request_id': submission['request_id'], 'attempt_id': attempt_id,
        'submission_sha256': submission['record_sha256'], 'approval': ref(approval),
        'requested_implementation': submission['implementation'], 'executing_implementation': actual}
    value = _seal('EXECATTEMPT', body)
    install_bytes(inside(root, BASE + '/attempts/' + value['id'] + '.json'), canonical(value) + b'\n')
    return ref(value)


def record_trial_intent(store, approval, submission, key):
    """Pin exact new-executor trial identity before calculation/publication.

    The intent is operational provenance, not a trial or an admission. It lets
    recovery find a committed new trial even when its result link was not saved.
    """
    from research.contracts import scientific
    row = row_for(approval, submission['request_id'], canonical=True)
    validate_cohort_envelope(approval, row['request_id'], submission)
    actual = store.resolve('implementation', key['implementation'])
    _require(actual['body'] == approval['proposal']['to_implementation'], 'trial executor differs from approval')
    body = {'schema': 'frozen_program_trial_intent_v1', 'version': '1.0.0',
        'approval': ref(approval), 'request_id': submission['request_id'],
        'submission_sha256': submission['record_sha256'],
        'trial_id': 'TRIAL_' + digest(key), 'scientific_key': scientific(key)}
    value = _seal('EXECTRIALINTENT', body)
    path = inside(store.root, BASE + '/trial_intents/' + submission['request_id'] + '/' + value['id'] + '.json')
    install_bytes(path, canonical(value) + b'\n')
    return ref(value)


def _claimed_trials(store, approval, submission):
    folder = inside(store.root, BASE + '/trial_intents/' + submission['request_id'])
    for path in sorted(folder.glob('*.json')):
        value = read_json(path); _identity(value, 'EXECTRIALINTENT')
        _require(set(value) == {'id','schema','version','approval','request_id','submission_sha256','trial_id','scientific_key'} and
                 value['schema'] == 'frozen_program_trial_intent_v1' and value['version'] == '1.0.0' and
                 value['id'] + '.json' == path.name and path.read_bytes() == canonical(value) + b'\n',
                 'execution trial intent bytes differ')
        _require(value['request_id'] == submission['request_id'] and
                 value['submission_sha256'] == submission['record_sha256'] and
                 value['trial_id'] == 'TRIAL_' + digest(value['scientific_key']), 'execution trial intent identity differs')
        if value['approval'] != ref(approval):
            continue
        if store.path('trial', value['trial_id']).exists():
            trial = store.get('trial', value['trial_id'])
            _require(trial['scientific_key'] == value['scientific_key'], 'claimed trial key differs')
            yield ref(trial)


def verify_committed_closure(store, approval, submission, plan):
    """Refuse omitted or unclaimed trials, including publication-before-link interruptions.

    This intentionally scans immutable trial metadata once per approved attempt.
    No rows are loaded and no result is recomputed. A committed new-executor
    trial requires this exact request's durable trial intent before reuse.
    """
    from research.contracts import HORIZONS, scientific
    from research.performance import measure, counter
    row = row_for(approval, submission['request_id'], canonical=True)
    pins = {r['id']: r for r in row['committed_trials']}
    claimed = {r['id']: r for r in _claimed_trials(store, approval, submission)}
    profile = submission['research_spec']
    contexts = {}
    for horizon in HORIZONS:
        relation = {'recipe': plan['recipe'], 'scope': plan['scope'], 'mode': plan['mode'],
            'target_family': 'price_return', 'horizon': horizon, 'horizon_unit': 'scheduled_weekdays',
            'members': [m['instrument_id'] for m in plan['members']],
            'targets': [m['targets'][str(horizon)]['definition'] for m in plan['members']],
            'expected_direction': plan['intent']['expected_direction']}
        if 'feature_application' in plan: relation['feature_application'] = plan['feature_application']
        existing = store.find('relationship', relation)
        if existing:
            contexts[horizon] = {'relationship': ref(existing),
                'research_spec': {'id': profile['id'], 'version': profile['version'], 'content_sha256': digest(profile)},
                'targets': [{'instrument': m['instrument_id'], 'binding': m['targets'][str(horizon)]} for m in plan['members']]}
    with measure('compatibility.committed_closure'):
        for path in sorted(inside(store.root, 'storage/catalog/trial_ledger/records').glob('*.json')):
            trial = store.get('trial', path.stem)
            counter('compatibility.trial_metadata_checked')
            key = trial['scientific_key']; context = contexts.get(key.get('horizon'))
            phase = key.get('stage')
            if not context or phase not in ('P1', 'P2'):
                continue
            if key.get('period') != plan['periods'][phase] or not all(key.get(k) == scientific(v) for k,v in context.items()):
                continue
            impl = store.resolve('implementation', key['implementation'])
            if approval['proposal']['schema'] == SUCCESSOR_SCHEMA and trial['id'] in pins:
                _require(pins[trial['id']] == ref(trial) and historical_executor_matches(approval, trial, impl),
                         'committed historical trial or executor differs from exact successor pins')
            elif impl['body'] == approval['proposal']['from_implementation']:
                _require(pins.get(trial['id']) == ref(trial),
                         'committed historical trial omitted from exact approved closure')
            elif impl['body'] == approval['proposal']['to_implementation']:
                _require(claimed.get(trial['id']) == ref(trial),
                         'committed new-executor trial lacks this exact request trial intent')
            elif approval['proposal']['schema'] == SUCCESSOR_SCHEMA:
                raise ResearchConflict('Execution compatibility: unpinned historical executor trial in committed closure')
    return True


def committed_trial(store, approval, submission, plan, phase, horizon, relationship, *,
                    discovery_trial=None, discovery_effect=None):
    """Reuse only exact approved authority; never synthesize a historical key."""
    if approval is None:
        return None
    row = row_for(approval, submission['request_id'], canonical=True)
    found = []
    candidates = [(r, approval['proposal']['from_implementation']) for r in row['committed_trials']]
    candidates.extend((r, approval['proposal']['to_implementation']) for r in _claimed_trials(store, approval, submission))
    for binding, expected_implementation in candidates:
        trial = store.resolve('trial', binding)
        key = trial['scientific_key']
        if key['stage'] != phase or key['horizon'] != horizon:
            continue
        profile = submission['research_spec']
        expected = {'relationship': ref(relationship), 'stage': phase, 'horizon': horizon,
            'research_spec': {'id': profile['id'], 'version': profile['version'], 'content_sha256': digest(profile)},
            'period': plan['periods'][phase],
            'targets': [{'instrument': m['instrument_id'], 'binding': m['targets'][str(horizon)]} for m in plan['members']],
            'discovery_trial': discovery_trial, 'discovery_effect': discovery_effect}
        from research.contracts import scientific
        _require(all(key.get(k) == scientific(v) for k, v in expected.items()), 'committed trial belongs to different science')
        old_impl = store.resolve('implementation', key['implementation'])
        historical = binding in row['committed_trials']
        _require(historical_executor_matches(approval, trial, old_impl) if historical else
                 old_impl['body'] == expected_implementation, 'committed trial executor differs')
        _require(key['prepared']['phase'] == phase and key['prepared']['period'] == plan['periods'][phase] and
                 [m['instrument_id'] for m in key['prepared']['members']] ==
                 [m['instrument_id'] for m in plan['members']], 'committed prepared membership differs')
        for artifact in trial['body']['artifact_manifests']:
            store.verify_artifact(artifact)
        found.append(trial)
    _require(len(found) <= 1, 'multiple committed trials for one stage/horizon')
    return found[0] if found else None
