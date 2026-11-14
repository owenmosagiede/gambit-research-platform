"""Bind a P2 evaluation to the sign and immutable evidence from P1."""
from copy import deepcopy
from research.contracts import DISCOVERY_DIRECTION, DIRECTIONS, HORIZONS, ResearchBlocked, ResearchError, digest, ref, request_id
from research.schedule import period_for

SKIPPED_FOR_SIGN = 'DISCOVERY_EFFECT_CONTRADICTS_EXPECTED_DIRECTION'
FOLLOWUP_POLICY = 'retrospective_skipped_p2_v1'


def observed_direction(effect):
    from research.p1_discovery.contract import numeric
    value = numeric(effect)
    if value:
        return 'POSITIVE' if value > 0 else 'NEGATIVE'
    return None


def discovery_binding(p1, admission, *, skipped=None):
    if (p1['body']['stage'] != 'P1' or p1['body']['admission'] != 'admitted'
            or admission['body']['decision'] != 'admitted'
            or admission['body']['trial'] != ref(p1)
            or admission['body']['relationship'] != p1['scientific_key']['relationship']):
        raise ResearchError('Direction requires authoritative admitted P1 evidence')
    sign = observed_direction(p1['body']['metrics'].get('primary_effect'))
    if sign is None:
        return None
    binding = {'policy': DISCOVERY_DIRECTION, 'direction': sign,
               'discovery_trial': ref(p1), 'admission': ref(admission)}
    if skipped is not None:
        binding.update(classification=FOLLOWUP_POLICY, prior_decision=ref(skipped))
    return binding


def verify_direction_binding(store, relation, p1, admission, p2, validation):
    """Use the selected sign for display and validation evidence verification."""
    binding = p2['scientific_key'].get('direction_binding') if p2 else None
    submitted = relation['body']['expected_direction']
    if binding is None:
        if validation is not None and 'direction_binding' in validation['body']:
            raise ResearchError('Validation direction lacks a matching trial binding')
        if p2 and submitted == DISCOVERY_DIRECTION:
            raise ResearchError('Discovery-selected P2 is missing its frozen direction')
        if submitted != DISCOVERY_DIRECTION:
            return submitted.upper()
        if p1['body'].get('admission') == 'admitted':
            return observed_direction(p1['body']['metrics'].get('primary_effect'))
        return None
    skipped = None
    if 'prior_decision' in binding:
        skipped = store.resolve('validation', binding['prior_decision'])
        verify_skipped(relation, p1, skipped, p2['scientific_key']['period'])
    elif submitted != DISCOVERY_DIRECTION:
        raise ResearchError('Fixed-direction branch lacks follow-up evidence')
    if (validation is None or binding != discovery_binding(p1, admission, skipped=skipped)
            or validation['body'].get('direction_binding') != binding
            or p2['body']['expected_direction'] != binding['direction']):
        raise ResearchError('P2 direction does not match the frozen P1 evidence')
    return binding['direction']


def verify_skipped(relationship, p1, skipped, period):
    value = skipped['body']
    original = relationship['body']['expected_direction']
    sign = observed_direction(p1['body']['metrics'].get('primary_effect'))
    if (original not in DIRECTIONS or sign not in DIRECTIONS or sign == original
            or value['relationship'] != ref(relationship)
            or value['decision'] != 'FAILED' or value['reason_codes'] != [SKIPPED_FOR_SIGN]
            or value['discovery_trial'] != ref(p1) or value['evaluation_trial'] is not None
            or value['period'] != period):
        raise ResearchError('Follow-up requires a skipped P2 decision for the same trial and period')


def discovery_plan(plan):
    from research.inputs import _plan_id
    value = deepcopy(plan)
    value['intent']['expected_direction'] = DISCOVERY_DIRECTION
    value['plan_id'] = _plan_id(value)
    return value


def verify_followup(jobs, submission, plan, *, verify_artifacts=False, parent_job=None):
    """Allow a new execution to use only the parent P1 evidence pinned at intake."""
    store = jobs.store
    entry = submission['p2_followup']
    horizons = plan.get('horizons', HORIZONS)
    if (set(entry) != {'policy', 'parent_request_id', 'parent_submission_sha256', 'skipped'}
            or entry['policy'] != FOLLOWUP_POLICY or type(entry['skipped']) is not dict
            or not entry['skipped'] or set(entry['skipped']) - {str(h) for h in horizons}):
        raise ResearchError('Invalid P2-only follow-up plan')
    parent = jobs._submission(entry['parent_request_id'])
    if (parent['record_sha256'] != entry['parent_submission_sha256']
            or parent.get('p2_followup') is not None or parent['research_spec'] != submission['research_spec']
            or discovery_plan(parent['frozen_plan']) != plan
            or submission['intent'] != plan['intent']):
        raise ResearchError('Follow-up differs from the original frozen research inputs')
    if parent_job is None:
        parent_job = jobs._read_job(parent['request_id'])
    if parent_job['status'] != 'succeeded':
        raise ResearchError('Follow-up needs a finished parent request')
    saved = {}
    metadata = {ref_['id']: ref_ for ref_ in parent_job['results']}
    for h in horizons:
        link_ref = entry['skipped'].get(str(h))
        if link_ref is None:
            continue
        if metadata.get(link_ref['id']) != link_ref:
            raise ResearchError('Follow-up evidence is not a final result of its parent')
        link = store.resolve('link', link_ref)['body']
        relationship = store.resolve('relationship', link['relationship'])
        p1_ref, = link['trial_results']
        admission_ref, = link['admission_results']
        validation_ref, = link['validation_results']
        p1 = store.resolve('trial', p1_ref)
        admission = store.resolve('admission', admission_ref)
        skipped = store.resolve('validation', validation_ref)
        if (relationship['body']['horizon'] != h or p1['scientific_key']['horizon'] != h
                or p1['scientific_key']['period'] != period_for(plan, 'P1', h)
                or p1['scientific_key']['research_spec']['content_sha256'] != digest(plan['profile'])):
            raise ResearchError('Saved P1 does not match the frozen horizon, period or research spec')
        verify_skipped(relationship, p1, skipped, period_for(plan, 'P2', h))
        discovery_binding(p1, admission, skipped=skipped)
        if verify_artifacts:
            for artifact in p1['body']['artifact_manifests']:
                store.verify_artifact(artifact)
        saved[h] = relationship, p1, admission, skipped
    return saved

def continuation_id(parent_request_id, *, followup):
    from uuid import UUID, uuid5
    return str(uuid5(UUID(parent_request_id), FOLLOWUP_POLICY if followup else DISCOVERY_DIRECTION))


def continuation_packet(jobs, rid, intent, implementation, parent_id, followup):
    """Operator-only intake using an exact frozen queued or completed parent."""
    parent = jobs._submission(parent_id)
    plan = discovery_plan(parent['frozen_plan'])
    if jobs.adapter is None:
        from research.inputs import _validate_plan
        _validate_plan(plan)
    job = jobs._read_job(parent_id)
    if (parent.get('p2_followup') is not None or parent['intent']['expected_direction'] not in DIRECTIONS
            or plan['mode'] != 'TS' or plan['intent'] != intent
            or rid != continuation_id(parent_id, followup=followup is not None)):
        raise ResearchError('Continuation identity or original momentum inputs differ')
    packet = {'intent': intent, 'research_spec': parent['research_spec'],
              'implementation': implementation, 'frozen_plan': plan}
    if 'feature_application' in plan:
        packet['feature_application'] = plan['feature_application']
    if followup is None:
        if job['status'] not in ('queued', 'cancelled') or job.get('plan'):
            raise ResearchError('Only an unstarted parent can move to the new direction rule')
        if job['results'] or any(row['p1_status'] != 'pending' for row in job['horizons']):
            raise ResearchError('Queued continuation cannot replace discovery work that already started')
    else:
        packet['p2_followup'] = {'policy': FOLLOWUP_POLICY, 'parent_request_id': parent_id,
                                 'parent_submission_sha256': parent['record_sha256'], 'skipped': followup}
        verify_followup(jobs, packet, plan, parent_job=job)
    return packet


def exposure_key(relationship, period):
    return digest([{key: value for key, value in relationship.items() if key != 'expected_direction'},
                   period])


def p2_exposures(store, wanted):
    """Read ledger metadata only, accounting for a committed P2 under either sign."""
    from research.store import FOLDERS
    catalog = store.root / 'storage/catalog'
    related, accessed, phase_attempts, records = {}, set(), {}, {}
    for path in (catalog / FOLDERS['exposure']).glob('EXPOSURE_*.json'):
        exposure = store.get('exposure', path.stem)
        body, key = exposure['body'], exposure['scientific_key']
        if key.get('phase') == 'P2':
            identity = (key['request_id'], key['horizon'])
            accessed.add(identity)
            phase_attempts.setdefault(identity, set()).add(body.get('plan_id'))
        if body.get('stage') != 'P2':
            continue
        binding = body['relationship']
        if binding['id'] not in related:
            related[binding['id']] = store.resolve('relationship', binding)
        relationship = related[binding['id']]
        if ref(relationship) != binding:
            raise ResearchError('P2 exposure points to a different relationship')
        fingerprint = exposure_key(relationship['body'], body['period'])
        if fingerprint in wanted:
            records.setdefault(fingerprint, set()).add(key['trial_key'])
    return accessed, records, phase_attempts


def verify_no_prior_p2(jobs, submission, plan, saved):
    store = jobs.store
    followup = submission['p2_followup']
    rid = submission['request_id']
    parent_id = request_id(followup['parent_request_id'])
    fingerprints = {h: exposure_key(relationship['body'], period_for(plan, 'P2', h))
                    for h, (relationship, *_) in saved.items()}
    accessed, records, phase_attempts = p2_exposures(store, set(fingerprints.values()))
    # A completed result committed by this same follow-up can be recovered
    # idempotently. A read without committed evidence needs reconciliation.
    own_trials = {}
    skipped_refs = [ref(row[-1]) for row in saved.values()]
    for link_ref in jobs._read_job(rid)['results']:
        link = store.resolve('link', link_ref)['body']
        for trial_ref in link['trial_results']:
            trial = store.resolve('trial', trial_ref)
            key = trial['scientific_key']
            if (key['stage'] == 'P2'
                    and key.get('direction_binding', {}).get('prior_decision')
                    in skipped_refs):
                own_trials[key['horizon']] = trial
    for h, fingerprint in fingerprints.items():
        own = own_trials.get(h)
        own_key = {digest(own['scientific_key'])} if own else set()
        other = records.get(fingerprint, set()) - own_key
        if ((parent_id, h) in accessed or other
                or (rid, h) in accessed and (own is None or phase_attempts[(rid, h)] != {plan['plan_id']})):
            raise ResearchBlocked([{'code': 'PRIOR_P2_ACCESS',
                'message': 'Prior P2 access requires reconciliation for horizon ' + str(h)}])
    return own_trials
