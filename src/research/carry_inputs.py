"""Align five retrospective carry recipes with existing paired return Targets."""
from bisect import bisect_left
from copy import deepcopy

from data.fx_carry import phase_observations, recipe, FAMILIES
from data.transformations.identity import digest, reference
from research.contracts import canonical, profile_blockers, ref
from research.store import inside, read_json


def load_profile(root):
    binding = read_json(inside(root, 'config/fx_carry_research.json'))['research_spec']
    path = inside(root, 'definitions/research_specs/' + binding['id'] + '/' + binding['version'] + '.json')
    profile = read_json(path)
    if ref(profile) != binding or path.read_bytes() != canonical(profile) + b'\n' or profile_blockers(profile):
        raise ValueError('Carry Research Spec is unapproved or differs from its pin')
    if profile.get('carry_recipes') != [reference(recipe(family)) for family in FAMILIES]:
        raise ValueError('Carry Research Spec must pin exactly the five fixed carry recipes')
    return profile


def restrict_horizons(schedule, source):
    result = deepcopy(schedule)
    for horizon in list(result['horizons']):
        coverage = source['coverage'][str(horizon)]
        if coverage['exclusion']:
            result['horizons'].remove(horizon)
            result.setdefault('excluded_horizons', {})[str(horizon)] = coverage['exclusion']
            result.get('horizon_periods', {}).pop(str(horizon), None)
    return result


def prepare(root, plan, phase, period, cancelled=None):
    from research.inputs import _check_cancel
    from runtime.research_jobs import implementation
    _check_cancel(cancelled)
    rows = phase_observations(root, plan['carry_source'], period)
    _check_cancel(cancelled)
    prepared = {'plan_id': plan['plan_id'], 'phase': phase, 'period': deepcopy(period),
        'implementation_fingerprint': implementation()['fingerprint'],
        'members': [{'instrument_id': plan['scope']['members'][0],
                     'materializations': [plan['carry_source']['snapshot']],
                     'phase_observations_sha256': digest(rows), 'unavailable': []}]}
    prepared['prepared_id'] = 'PREPARED_' + digest(prepared)
    return prepared


def load(root, plan, prepared, phase, horizon, period):
    from research.inputs import _load_target, InputsBlocked
    from runtime.research_jobs import implementation
    source, member = plan['carry_source'], plan['members'][0]
    features = phase_observations(root, source, period)
    if (prepared['implementation_fingerprint'] != implementation()['fingerprint']
            or prepared['members'][0]['materializations'] != [source['snapshot']]
            or prepared['members'][0]['phase_observations_sha256'] != digest(features)):
        raise InputsBlocked('Prepared carry inputs or implementation differ')
    features.sort(key=lambda row: row['date'])
    available = [row['date'] for row in features]
    targets, exclusions = _load_target(root, member, plan, period, horizon)
    rows = []
    updates = set()
    for target in targets:
        anchor = target['prediction_anchor']
        index = bisect_left(available, anchor) - 1
        feature = features[index] if index >= 0 else None
        # Daily carry scores require their precise next scheduled anchor.
        if feature and feature['first_anchor'] != anchor:
            feature = None
        reasons = []
        if feature is None or feature['value'] is None:
            reasons.append('CARRY_FEATURE_UNAVAILABLE')
        if target['status'] != 'valid':
            reasons.append(target['reason_code'])
        if feature:
            updates.add(feature['date'])
        rows.append({'date': anchor, 'instrument': member['instrument_id'],
            'feature': feature['value'] if feature else None,
            'target': target['value'] if target['status'] == 'valid' else None,
            'target_entry': target['entry_time'], 'target_end': target['exit_time'],
            'valid': not reasons, 'status': 'valid' if not reasons else 'unavailable',
            'reason_codes': reasons, 'available_at': feature['date'] if feature else None,
            'target_available_at': None, 'historical_eligibility_certified': False,
            'lineage': {'carry_snapshot': source['snapshot'], 'recipe': source['recipe'],
                'funding_snapshot': source['funding_snapshot'], 'inflation_capture': source['inflation_capture'], 'observation_sha256': digest(feature) if feature else None,
                'operands': feature['operands'] if feature else None, 'price_snapshot': member['price_snapshot'],
                'target_materialization': member['targets'][str(horizon)]['materialization'],
                'target_row_id': target['id'], 'target_operands': target['operands']}})
    valid_count = sum(row['valid'] for row in rows)
    return {'plan_id': plan['plan_id'], 'phase': phase, 'horizon': horizon, 'mode': 'TS',
        'members': deepcopy(plan['scope']['members']), 'rows': rows,
        'coverage': [{'instrument_id': member['instrument_id'], 'scheduled_rows': len(rows),
            'aligned_weekday_rows': len(rows), 'valid_rows': valid_count,
            'unavailable_rows': len(rows) - valid_count, 'distinct_source_update_count': len(updates),
            'exclusions': exclusions, 'feature_unavailable_windows': []}],
        'lineage': {'recipe': plan['recipe'], 'scope': plan['scope']['reference'],
            'membership_snapshot': plan['scope']['membership_snapshot'], 'prepared_id': prepared['prepared_id'],
            'carry_snapshot': source['snapshot']}, 'availability_mode': 'retrospective_date_label',
        'historical_replay_certified': False, 'live_certified': False}
