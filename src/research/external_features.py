"""Date-precision stored Feature alignment, independent of provider and frequency.

Consumes immutable published observations; never reevaluates a Feature or changes
its source identity. Hashes may cover cross-phase bytes. Value decoding is limited
to this phase and the single prevailing preperiod state.
"""
from copy import deepcopy
from datetime import date, timedelta
import re
import hashlib

from data.alfred_onboarding import stable_read, strict_json
from data.feature_store import FeatureStore
from data.feature_store_contracts import normalize_materialization, normalize_observation
from data.transformations.contracts import normalize_time
from data.transformations.identity import canonical_bytes, digest, reference, feature_id, signal_id
from data.targets.scheduling import temporal_eligible
from research.contracts import canonical, ref, exact_selection, profile_blockers
from research.store import inside, read_json


def blocked(message):
    from research.inputs import InputsBlocked
    raise InputsBlocked(message)


def validate_policy(policy):
    required = {'id', 'version', 'approval_state', 'sampling_mode', 'eligibility_rule',
                'availability_precision_rule', 'freshness_rule', 'invalid_update_rule',
                'collision_rule', 'missing_anchor_rule', 'phase_context_rule'}
    if not isinstance(policy, dict) or set(policy) != required:
        blocked('Incomplete or conflicting external alignment policy')
    exact_selection({k: policy[k] for k in ('id', 'version')})
    expected = {'approval_state': 'approved', 'sampling_mode': 'DAILY_STATE',
        'eligibility_rule': 'availability_and_evaluation_strictly_before_anchor',
        'availability_precision_rule': 'date_only_next_scheduled_weekday',
        'invalid_update_rule': 'newest_supersedes_including_null',
        'collision_rule': 'reject_duplicate_effective_dates',
        'missing_anchor_rule': 'preserve_scheduled_grid',
        'phase_context_rule': 'one_prevailing_preperiod_state'}
    if any(policy.get(k) != v for k, v in expected.items()):
        blocked('Unsupported external alignment semantics')
    fresh = policy['freshness_rule']
    if not isinstance(fresh, dict): blocked('Freshness rule must be explicit')
    fields = {'mode', 'age_basis', 'unit', 'precedence'}
    if fresh.get('mode') == 'MAX_AGE': fields |= {'maximum', 'boundary'}
    if (set(fresh) != fields or fresh.get('mode') not in ('UNTIL_SUPERSEDED', 'MAX_AGE', 'EVENT_ONLY')
            or fresh.get('age_basis') not in ('available_at', 'evaluation_cutoff')
            or fresh.get('unit') != 'calendar_days' or fresh.get('precedence') != 'select_newest_then_age'):
        blocked('Incomplete or conflicting freshness rule')
    if fresh['mode'] == 'MAX_AGE' and (type(fresh['maximum']) is not int or fresh['maximum'] < 0
            or fresh['boundary'] not in ('inclusive', 'exclusive')):
        blocked('MAX_AGE requires a nonnegative maximum and explicit boundary')
    return deepcopy(policy)


def load_policy(root, binding):
    exact_selection({k: binding[k] for k in ('id', 'version')})
    path = inside(root, f"definitions/alignment_policies/{binding['id']}/{binding['version']}.json")
    policy = validate_policy(read_json(path))
    if ref(policy) != binding or path.read_bytes() != canonical(policy) + b'\n':
        blocked('External alignment policy identity differs')
    return policy


def load_profile(root):
    config = read_json(inside(root, 'config/external_feature_alignment.json'))
    binding = config['research_spec']; exact_selection({k: binding[k] for k in ('id', 'version')})
    path = inside(root, f"definitions/research_specs/{binding['id']}/{binding['version']}.json")
    profile = read_json(path)
    if ref(profile) != binding or path.read_bytes() != canonical(profile) + b'\n':
        blocked('External Research Spec identity differs')
    if profile_blockers(profile): blocked('External Research Spec has unresolved approvals')
    load_policy(root, profile['external_alignment_policy'])
    return profile


def definition(root, selection):
    store = FeatureStore(root)
    exact_selection(selection)
    path = store.path(f"definitions/features/{selection['id']}/{selection['version']}.json")
    if not path.is_file(): blocked('External Feature definition is not registered; non-FX Scope application remains unresolved')
    feature = strict_json(stable_read(path)); store._validate(feature)
    if feature.get('record_type') != 'feature_definition' or {k: feature[k] for k in ('id', 'version')} != selection:
        blocked('Unsupported application type')
    recipe = feature['body']['recipe']
    if feature['id'] != feature_id(recipe) or feature['body']['signal_id'] != signal_id(recipe):
        blocked('External Feature identity differs from its recipe')
    sources = recipe['sources']
    if len(sources) != 1: blocked('External alignment requires one unambiguous source series')
    view = store.resolve(sources[0]['source_view']); dataset = store.resolve(view['body']['dataset'])
    if dataset['body'].get('kind') == 'fx_constructed_dataset':
        blocked('Instrument-native calculations must use their reusable recipe')
    # This path consumes a selected external source series, never a per-member recipe.
    return feature


def verify_metadata_closure(store, value, seen=None):
    """Verify exact references and bytes without decoding source observations."""
    seen = set() if seen is None else seen
    if isinstance(value, dict):
        if set(value) == {'id', 'version', 'content_sha256'}:
            key = tuple(value[k] for k in ('id', 'version', 'content_sha256'))
            if key in seen: return
            seen.add(key); verify_metadata_closure(store, store.resolve(value), seen); return
        if {'blob_sha256', 'format', 'byte_count'} <= set(value): store.payload(value)
        if value.get('record_type') in ('onboarding_evidence', 'ingestion_receipt') and value.get('schema_version') != '0.5.0':
            payload = value['body']['payload']
            store.payload({'blob_sha256': payload['sha256'], 'format': 'json', 'byte_count': payload['byte_count']})
        for child in value.values(): verify_metadata_closure(store, child, seen)
    elif isinstance(value, list):
        for child in value: verify_metadata_closure(store, child, seen)


def next_weekday(day):
    result = date.fromisoformat(day) + timedelta(days=1)
    while result.weekday() >= 5: result += timedelta(days=1)
    return result.isoformat()


def resolve_source(root, feature, profile):
    if 'external_alignment_policy' not in profile: blocked('Missing approved external alignment policy')
    policy = load_policy(root, profile['external_alignment_policy'])
    store = FeatureStore(root); candidates = []
    for path in sorted(store.path('storage/catalog/feature_store').glob('*/manifest.json')):
        value = strict_json(stable_read(path))
        if value.get('definition') == reference(feature):
            if value.get('schema_version') != '0.3.0': blocked('Unsupported external stored observation contract')
            manifest = normalize_materialization(value)
            if path.parent.name != manifest['id']: blocked('External materialization path differs')
            candidates.append(manifest)
    pins = profile.get('external_materializations', {})
    pin = pins.get(feature['id'])
    if pin is not None: candidates = [m for m in candidates if reference(m) == pin]
    if len(candidates) != 1: blocked('Exactly one external materialization or an exact approved pin is required')
    manifest = candidates[0]; metadata = manifest['metadata']; recipe = feature['body']['recipe']
    if metadata['temporal_precision'] != 'date' or metadata['availability_semantics'] != 'derived_at_cutoff':
        blocked('External pathway supports date-only derived-at-cutoff observations')
    if (metadata['selection'] != recipe['selection'] or metadata['source_view'] != recipe['sources'][0]['source_view']
            or metadata['history_policy'] != recipe['history_policy'] or metadata['history_mode'] != recipe['history_mode']
            or metadata['unit'] != recipe['output_unit']): blocked('External source selection or semantics conflict')
    view = store.resolve(metadata['source_view'])
    if view['body']['dataset'] != metadata['dataset']: blocked('External dataset lineage differs')
    for binding in manifest['input_key']['policy_bindings']:
        p = store.resolve(binding['artifact'])
        if p['record_type'] != 'policy_definition' or p['body']['approval_state'] != 'approved':
            blocked('External Feature depends on an unapproved policy')
    verify_metadata_closure(store, [feature, manifest])
    # Validate temporal/series headers without decoding any Feature values.
    headers = observation_headers(store, manifest)
    if not headers: blocked('External materialization has no observation schedule')
    if policy['freshness_rule']['mode'] == 'EVENT_ONLY' and len({next_weekday(x[0]) for x in headers}) != len(headers):
        blocked('External event collisions require an explicit compatible policy')
    return {'feature': reference(feature), 'materialization': reference(manifest),
        'metadata': deepcopy(metadata), 'source_snapshots': manifest['input_key']['source_snapshots'],
        'alignment_policy': profile['external_alignment_policy'], 'policy': policy,
        'first_eligible_anchor': next_weekday(headers[0][0]),
        'row_count': manifest['row_count'], 'status_counts': manifest['status_counts'],
        'coverage': {'reference_start': min((x['reference_time'] for x in manifest['input_key']['output_index'] if x['reference_time']), default=None),
            'reference_end': max((x['reference_time'] for x in manifest['input_key']['output_index'] if x['reference_time']), default=None),
            'cutoff_start': headers[0][0], 'cutoff_end': headers[-1][0]}}


def _header(line, name):
    # Canonical JSON strings; allow spaces only inside quoted values. No value field is decoded.
    matches = re.findall(rb'"' + re.escape(name.encode()) + rb'":("(?:[^"\\]|\\.)*"|null)(?=[,}])', line)
    if len(matches) != 1: blocked('Missing or ambiguous external observation header: ' + name)
    return strict_json(matches[0])


def observation_headers(store, manifest):
    """Return verified temporal headers and opaque lines, never decoded values."""
    found = []; expected = manifest['metadata']['selection']; index = []; semantic_lines = []
    for part in manifest['partitions']:
        lines = store.payload(part).splitlines()
        if len(lines) != part['row_count']: blocked('External partition count differs')
        for line in lines:
            cutoff = _header(line, 'evaluation_cutoff'); available = _header(line, 'available_at')
            reference_time = _header(line, 'reference_time')
            normalize_time(cutoff, 'date'); normalize_time(available, 'date')
            if available != cutoff: blocked('Unsupported availability evidence for stored observation contract')
            if reference_time is not None:
                normalize_time(reference_time, 'date')
                if reference_time > cutoff: blocked('Reference period exceeds evaluation cutoff')
            if _header(line, 'entity_id') != expected['entity_id'] or _header(line, 'measure') != expected['measure']:
                blocked('Mixed external entity or measure')
            # Dimensions are contract metadata, not observation values.
            dims = re.findall(rb'"dimensions":(.*?)(?=,"entity_id":)', line)
            if len(dims) != 1 or strict_json(dims[0]) != expected['dimensions']: blocked('Mixed or ambiguous external dimensions')
            if _header(line, 'materialization_id') != manifest['id']: blocked('External observation belongs to another materialization')
            stripped, count = re.subn(rb'"materialization_id":"MATERIALIZATION_[0-9a-f]{64}",', b'', line)
            if count != 1: blocked('External observation identity is noncanonical')
            semantic_lines.append(stripped)
            found.append((max(available, cutoff), line))
            index.append({'reference_time': reference_time, 'evaluation_cutoff': cutoff})
    if hashlib.sha256(b'[' + b','.join(semantic_lines) + b']').hexdigest() != manifest['semantic_rows_sha256']:
        blocked('External observation semantic checksum differs')
    if index != manifest['input_key']['output_index']: blocked('External observation schedule differs from frozen output index')
    if len({when for when, _ in found}) != len(found): blocked('Duplicate eligible external temporal candidates')
    return sorted(found, key=lambda x: x[0])


def phase_rows(root, source, period):
    store = FeatureStore(root); manifest = store.resolve(source['materialization'])
    if manifest['definition'] != source['feature'] or manifest['metadata'] != source['metadata']:
        blocked('Frozen external source semantics differ')
    headers = observation_headers(store, manifest)
    from research.inputs import _period_days
    days = list(_period_days(period))
    if not days: return []
    past = [item for item in headers if item[0] < days[0]]
    selected = (past[-1:] if past else []) + [item for item in headers if days[0] <= item[0] < days[-1]]
    rows = []
    for _, line in selected:
        row = normalize_observation(strict_json(line), 'date')
        if canonical_bytes(row) != line: blocked('Noncanonical external observation')
        if row['lineage'] not in manifest['lineage']: blocked('External observation lacks declared lineage')
        lineage = store.resolve(row['lineage'])
        if (lineage['operation'] != source['feature'] or lineage['implementation'] != manifest['input_key']['implementation']
                or lineage['policy_bindings'] != manifest['input_key']['policy_bindings']): blocked('External observation lineage semantics differ')
        if row['status'] == 'valid' and not lineage['inputs']: blocked('Valid external observation lacks operand lineage')
        verify_selected_lineage(store, lineage, row, source)
        rows.append(row)
    return rows


def verify_selected_lineage(store, lineage, row, source):
    """Exact operand locators are verified without decoding unrelated PIT values."""
    for binding in lineage['inputs']:
        record = store.resolve(binding['artifact'])
        if record['record_type'] != 'pit_operand_record': blocked('Unsupported external operand lineage contract')
        body = record['body']; context = body['key']; metadata = source['metadata']
        if (body['pit_snapshot'] not in source['source_snapshots'] or body['dataset'] != metadata['dataset']
                or body['source_view'] != metadata['source_view'] or body['temporal_precision'] != 'date'
                or {k: context[k] for k in ('entity_id', 'measure', 'dimensions')} != metadata['selection']
                or context['available_at'] > row['evaluation_cutoff'] or context['reference_time'] > row['evaluation_cutoff']):
            blocked('External operand violates source selection or observation cutoff')
        snapshot = store.resolve(body['pit_snapshot']); view = store.resolve(body['source_view'])
        if snapshot['definition'] != body['source_view'] or view['body']['dataset'] != body['dataset'] or body['raw_snapshot'] not in snapshot['upstream_snapshots']:
            blocked('External operand snapshot relationship differs')
        matches = []; native_lines = []
        for part in snapshot['members']:
            if part['format'] != 'jsonl': blocked('External operand evidence requires canonical JSONL')
            lines = store.payload(part).splitlines(); native_lines.extend(lines)
            for line in lines:
                if all(_header(line, item['field']) == item['value'] for item in body['pit_row_key']):
                    matches.append(strict_json(line))
        if (len(native_lines) != snapshot['record_count'] or
                hashlib.sha256(b'[' + b','.join(native_lines) + b']').hexdigest() != snapshot['semantic_content_sha256']):
            blocked('External PIT semantic checksum differs')
        if len(matches) != 1 or digest(matches[0]) != body['pit_row_sha256']: blocked('External operand row does not resolve exactly')
        native = matches[0]; mapping = body['field_mapping']
        if any(native.get(mapping[k]) != context[k] for k in ('entity_id', 'reference_time', 'available_at')):
            blocked('External operand key differs from native row')
        if any(native.get(mapping[k]) != body[k] for k in ('raw_snapshot', 'source_view')):
            blocked('External operand native source differs')
        raw = store.resolve(body['raw_snapshot'])
        if body['raw_cell']['blob_sha256'] not in {p['blob_sha256'] for p in raw['members']}:
            blocked('External operand raw evidence is not pinned')
        if (native.get(mapping['raw_blob_sha256']) != body['raw_cell']['blob_sha256']
                or native.get(mapping['raw_value_field']) != body['raw_cell']['field']
                or native.get(mapping['temporal_precision']) != body['temporal_precision']): blocked('External operand raw coordinates differ')
        selectors = {x['field']: x['value'] for x in body['raw_cell']['row_key']}
        if any(native.get(x['pit_field']) != selectors[x['raw_field']] for x in body['raw_row_mapping']):
            blocked('External operand raw row mapping differs')


def state_at(rows, anchor, policy):
    validate_policy(policy); normalize_time(anchor, 'date')
    eligible = [row for row in rows if all(temporal_eligible(row[k], 'date', anchor, 'date')['eligible']
                for k in ('available_at', 'evaluation_cutoff'))]
    if not eligible: return None, None, 'FEATURE_NOT_AVAILABLE'
    if policy['freshness_rule']['mode'] == 'EVENT_ONLY' and sum(next_weekday(max(r['available_at'],r['evaluation_cutoff'])) == anchor for r in eligible) > 1:
        blocked('External event collisions require an explicit compatible policy')
    keys = [max(r['available_at'], r['evaluation_cutoff']) for r in eligible]
    if len(set(keys)) != len(keys): blocked('Duplicate eligible external temporal candidates')
    row = max(eligible, key=lambda r: max(r['available_at'], r['evaluation_cutoff']))
    fresh = policy['freshness_rule']; age = (date.fromisoformat(anchor) - date.fromisoformat(row[fresh['age_basis']])).days
    if row['status'] != 'valid': return row, age, row['reason_code']
    if fresh['mode'] == 'MAX_AGE' and (age > fresh['maximum'] if fresh['boundary'] == 'inclusive' else age >= fresh['maximum']):
        return row, age, 'FEATURE_STALE'
    if fresh['mode'] == 'EVENT_ONLY' and anchor != next_weekday(max(row['available_at'], row['evaluation_cutoff'])):
        return row, age, 'NOT_FEATURE_EVENT_ANCHOR'
    return row, age, None


def prepare(root, plan, phase, period, cancelled=None):
    from research.inputs import _check_cancel
    _check_cancel(cancelled)
    source = plan['external_source']
    rows = phase_rows(root, source, period)
    _check_cancel(cancelled)
    # A phase-scoped alignment descriptor; existing source observations are not copied/published.
    from runtime.research_jobs import implementation
    prepared = {'plan_id': plan['plan_id'], 'phase': phase, 'period': deepcopy(period),
        'implementation_fingerprint': implementation()['fingerprint'],
        'alignment_policy': source['alignment_policy'],
        'members': [{'instrument_id': plan['scope']['members'][0], 'materializations': [source['materialization']],
                     'unavailable': [], 'phase_observations_sha256': digest(rows)}]}
    prepared['prepared_id'] = 'PREPARED_' + digest(prepared)
    return prepared


def load(root, plan, prepared, phase, horizon, period):
    from research.inputs import _load_target
    from runtime.research_jobs import implementation
    if prepared.get('implementation_fingerprint') != implementation()['fingerprint']:
        blocked('External preparation implementation has changed')
    source = plan['external_source']; member = plan['members'][0]; policy = load_policy(root, source['alignment_policy'])
    features = phase_rows(root, source, period)
    if (prepared.get('alignment_policy') != source['alignment_policy'] or prepared['members'][0].get('phase_observations_sha256') != digest(features)
            or prepared['members'][0]['materializations'] != [source['materialization']]): blocked('External prepared evidence differs')
    targets, exclusions = _load_target(root, member, plan, period, horizon)
    rows = []; updates = set(); valid_updates = set()
    for target in targets:
        feature, age, reason = state_at(features, target['prediction_anchor'], policy)
        observation_ref = None if feature is None else {'materialization': source['materialization'], 'observation_sha256': digest(feature),
            'key': {k: feature[k] for k in ('entity_id', 'reference_time', 'evaluation_cutoff')}}
        if feature: updates.add(digest(observation_ref))
        reasons = ([reason] if reason else []) + ([target['reason_code']] if target['status'] != 'valid' else [])
        valid = not reasons
        if valid: valid_updates.add(digest(observation_ref))
        evidence = {'original_observation': observation_ref, 'feature_definition': source['feature'],
            'source_selection': source['metadata']['selection'], 'target_instrument': member['instrument_id'],
            'source_snapshots': source['source_snapshots'], 'alignment_policy': source['alignment_policy'],
            'age': {'amount': age, 'basis': policy['freshness_rule']['age_basis'], 'unit': 'calendar_days'},
            'source_observation': None if feature is None else {k: feature[k] for k in
                ('reference_time', 'available_at', 'evaluation_cutoff', 'vintage_id', 'status', 'reason_code', 'value')},
            'feature_materialization': source['materialization']['id'], 'feature_lineage': None if feature is None else feature['lineage'],
            'target_materialization': member['targets'][str(horizon)]['materialization'], 'target_row_id': target['id'],
            'target_operands': target['operands'], 'price_snapshot': member['price_snapshot']}
        rows.append({'date': target['prediction_anchor'], 'instrument': member['instrument_id'],
            'feature': feature['value'] if feature and reason is None else None,
            'target': target['value'] if target['status'] == 'valid' else None,
            'target_entry': target['entry_time'], 'target_end': target['exit_time'], 'valid': valid,
            'status': 'valid' if valid else 'unavailable', 'reason_codes': reasons,
            'available_at': None, 'target_available_at': None, 'historical_eligibility_certified': False, 'lineage': evidence})
    valid_count = sum(r['valid'] for r in rows)
    return {'plan_id': plan['plan_id'], 'phase': phase, 'horizon': horizon, 'mode': 'TS',
        'members': deepcopy(plan['scope']['members']), 'rows': rows,
        'coverage': [{'instrument_id': member['instrument_id'], 'scheduled_rows': len(rows), 'aligned_weekday_rows': len(rows),
            'distinct_source_update_count': len(updates), 'valid_distinct_source_update_count': len(valid_updates),
            'valid_rows': valid_count, 'unavailable_rows': len(rows) - valid_count, 'exclusions': exclusions,
            'feature_unavailable_windows': []}],
        'lineage': {'recipe': plan['recipe'], 'scope': plan['scope']['reference'], 'membership_snapshot': plan['scope']['membership_snapshot'],
            'prepared_id': prepared['prepared_id'], 'alignment_policy': source['alignment_policy'], 'source_materialization': source['materialization']},
        'availability_mode': 'retrospective_date_label', 'historical_replay_certified': False, 'live_certified': False}
