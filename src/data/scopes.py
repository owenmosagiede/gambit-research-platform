"""Fixed FX research scopes in the existing definition and membership contracts.

Membership is pinned economic metadata, independent of observations and readiness.
The snapshot period records the registration event, never a historical eligibility
interval. This bounded adapter does not implement changing historical universes.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
import re

from data.alfred_onboarding import stable_read, strict_json
from data.feature_store import FeatureStore, record_path
from data.fx_pipeline import list_instruments
from data.fx_records import make_record
from data.transformations.identity import canonical_bytes, digest, reference

VERSION = '1.0.0'
PROFILE = 'fixed_fx_research_scopes.1.0.0'
PAIR_IDS = tuple('''AUDUSD EURUSD GBPUSD NZDUSD USDCAD USDCHF
USDCNH USDCZK USDHKD USDHUF USDILS USDJPY USDMXN USDNOK USDPLN USDSEK USDSGD USDZAR
AUDCAD AUDCHF AUDJPY AUDNZD CADCHF CADJPY CHFJPY EURAUD EURCAD EURCHF EURCZK EURGBP
EURHUF EURJPY EURNOK EURNZD EURPLN GBPAUD GBPCAD GBPCHF GBPJPY GBPNZD NZDCAD NZDCHF NZDJPY'''.split())
CORE_CURRENCIES = frozenset('AUD CAD CHF EUR GBP JPY NZD USD'.split())
G10_CURRENCIES = CORE_CURRENCIES | {'NOK', 'SEK'}
UNIVERSES = (
    ('FTMO_UNIVERSE', 'FTMO Universe', 43, 'parent'),
    ('FX_G10', 'G10', 31, 'both_g10'),
    ('FX_NON_G10', 'Non-G10', 12, 'outside_g10'),
    ('FX_CORE_28', 'Core FX', 28, 'both_core'),
    ('FX_USD_PAIRS', 'USD Pairs', 18, 'contains_usd'),
    ('FX_NON_USD_CROSSES', 'Non-USD Crosses', 25, 'without_usd'),
    ('FX_CORE_USD_PAIRS', 'Core USD Pairs', 7, 'core_contains_usd'),
    ('FX_CORE_CROSSES', 'Core Crosses', 21, 'core_without_usd'),
    ('FX_NORDIC', 'Nordic', 3, 'contains_nok_or_sek'),
    ('FX_CENTRAL_EUROPE', 'Central Europe', 6, 'contains_czk_huf_or_pln'),
    ('FX_ASIA_CNH_HKD_SGD', 'Asia: CNH, HKD, SGD', 3, 'contains_cnh_hkd_or_sgd'),
    ('FX_AUD_PAIRS', 'AUD Pairs', 7, 'contains_aud'),
    ('FX_CAD_PAIRS', 'CAD Pairs', 7, 'contains_cad'),
    ('FX_CHF_PAIRS', 'CHF Pairs', 7, 'contains_chf'),
    ('FX_EUR_PAIRS', 'EUR Pairs', 11, 'contains_eur'),
    ('FX_GBP_PAIRS', 'GBP Pairs', 7, 'contains_gbp'),
    ('FX_JPY_PAIRS', 'JPY Pairs', 7, 'contains_jpy'),
    ('FX_NZD_PAIRS', 'NZD Pairs', 7, 'contains_nzd'),
)
PERIOD_MEANING = 'document_registration_interval_not_economic_or_broker_eligibility'
NOTE = ('Fixed research membership. Stored price coverage and research readiness are separate; '
        'membership does not certify current or historical FTMO account eligibility or uniform directional exposure.')


class ScopeError(ValueError):
    """Stored membership or its exact reference closure is invalid."""


class ScopeNotFound(ScopeError):
    """The requested exact scope version is not registered."""


class ScopeConflict(ScopeError):
    """An existing name or immutable record is incompatible; nothing is replaced."""


def grouping_specification():
    return {'profile': PROFILE, 'parent_instrument_ids': sorted(PAIR_IDS),
            'core_currencies': sorted(CORE_CURRENCIES), 'g10_currencies': sorted(G10_CURRENCIES),
            'universes': [{'id': i, 'display_name': n, 'expected_member_count': c, 'rule': r}
                          for i, n, c, r in UNIVERSES],
            'membership_basis': 'registered_economic_pair_base_and_quote_currency',
            'membership_kind': 'fixed_research_reference', 'period_meaning': PERIOD_MEANING,
            'observation_filtering': False, 'quotation_or_direction_changes': False,
            'broker_eligibility_certified': False}


def resolve_groups(metadata):
    """Resolve explicit rules from registered currency metadata, not source labels."""
    if set(metadata) != set(PAIR_IDS):
        raise ScopeError('Expected exactly the approved 43 registered economic instruments')
    sets = {}
    for symbol, item in metadata.items():
        base, quote = item['base_currency'], item['quote_currency']
        if (not isinstance(base, str) or not isinstance(quote, str) or base == quote
                or not re.fullmatch('[A-Z]{3}', base) or not re.fullmatch('[A-Z]{3}', quote)
                or item['instrument_id'] != symbol or base + quote != symbol
                or item['economic_id'] != 'FX_' + base + '_' + quote):
            raise ScopeError('Registered economic pair/currency metadata mismatch: ' + symbol)
        sets[symbol] = {base, quote}
    predicates = {
        'parent': lambda c: True, 'both_g10': lambda c: c <= G10_CURRENCIES,
        'outside_g10': lambda c: not c <= G10_CURRENCIES,
        'both_core': lambda c: c <= CORE_CURRENCIES,
        'contains_usd': lambda c: 'USD' in c, 'without_usd': lambda c: 'USD' not in c,
        'core_contains_usd': lambda c: c <= CORE_CURRENCIES and 'USD' in c,
        'core_without_usd': lambda c: c <= CORE_CURRENCIES and 'USD' not in c,
        'contains_nok_or_sek': lambda c: bool(c & {'NOK', 'SEK'}),
        'contains_czk_huf_or_pln': lambda c: bool(c & {'CZK', 'HUF', 'PLN'}),
        'contains_cnh_hkd_or_sgd': lambda c: bool(c & {'CNH', 'HKD', 'SGD'}),
    }
    predicates.update({'contains_' + currency.lower(): lambda c, currency=currency: currency in c
                       for currency in ('AUD', 'CAD', 'CHF', 'EUR', 'GBP', 'JPY', 'NZD')})
    groups = {identifier: sorted(symbol for symbol, c in sets.items() if predicates[rule](c))
              for identifier, _, _, rule in UNIVERSES}
    for identifier, _, count, _ in UNIVERSES:
        if len(groups[identifier]) != count:
            raise ScopeError('Explicit membership rule count differs for ' + identifier)
    expected = {'FX_NORDIC': {'EURNOK', 'USDNOK', 'USDSEK'},
                'FX_CENTRAL_EUROPE': {'EURCZK', 'EURHUF', 'EURPLN', 'USDCZK', 'USDHUF', 'USDPLN'},
                'FX_ASIA_CNH_HKD_SGD': {'USDCNH', 'USDHKD', 'USDSGD'}}
    for identifier, members in expected.items():
        if set(groups[identifier]) != members:
            raise ScopeError('Explicit membership set differs for ' + identifier)
    for parent, left, right in (('FTMO_UNIVERSE', 'FX_G10', 'FX_NON_G10'),
                                ('FTMO_UNIVERSE', 'FX_USD_PAIRS', 'FX_NON_USD_CROSSES'),
                                ('FX_CORE_28', 'FX_CORE_USD_PAIRS', 'FX_CORE_CROSSES')):
        if set(groups[left]) & set(groups[right]) or set(groups[left]) | set(groups[right]) != set(groups[parent]):
            raise ScopeError('Membership partition differs: ' + parent)
    return groups


def _registration_metadata(store, binding):
    record = store.resolve(binding)
    body = record.get('body', {})
    if record.get('record_type') != 'onboarding_evidence' or body.get('kind') != 'fx_instrument_registration':
        raise ScopeError('Membership must resolve an economic instrument registration')
    source = body['source_metadata']
    return {'instrument_id': body['instrument_id'], 'economic_id': body['economic_id'],
            'base_currency': source['base_currency'], 'quote_currency': source['quote_currency'],
            'instrument_registration': binding}


def _metadata_from_registry(store):
    registered = {item['instrument_id']: item for item in list_instruments(store.root)}
    missing = set(PAIR_IDS) - set(registered)
    if missing:
        raise ScopeError('Missing registered instruments: ' + ', '.join(sorted(missing)))
    result = {symbol: _registration_metadata(store, registered[symbol]['registration']) for symbol in sorted(PAIR_IDS)}
    resolve_groups(result)
    return result


def _request_evidence(text):
    if not isinstance(text, str) or not text.strip():
        raise ScopeError('Exact user request text is required as registration evidence')
    return make_record('onboarding_evidence', {'kind': 'fixed_fx_scope_specification',
        'profile': PROFILE, 'approval_source': 'explicit_user_request', 'request_text': text,
        'request_sha256': hashlib.sha256(text.encode('utf-8')).hexdigest(),
        'specification': grouping_specification()}, 'Approved fixed FX research scope specification')


def _policies(evidence):
    specs = [('membership', 'registered_currency_metadata_fixed_research_membership'),
             ('eligibility', 'fixed_reference_membership_not_broker_eligibility'),
             ('exclusion', 'no_observation_readiness_or_missing_data_exclusions')]
    return [{'schema_version': '0.2.0', 'record_type': 'policy_definition',
             'id': 'POLICY_FX_FIXED_RESEARCH_' + kind.upper(), 'version': VERSION,
             'display_name': 'Fixed FX research ' + kind,
             'body': {'kind': kind, 'specification': reference(evidence),
                      'parameters': [{'name': 'semantics', 'unit': 'policy',
                                      'value': {'kind': 'token', 'value': meaning}}],
                      'approval_state': 'approved', 'compatibility_evidence': []}}
            for kind, meaning in specs]


def _definitions(metadata, policies):
    policy_refs = {p['body']['kind'] + '_policy': reference(p) for p in policies}
    groups = resolve_groups(metadata)
    specs = [('universe', i, n, groups[i]) for i, n, _, _ in UNIVERSES]
    specs.extend(('instrument', symbol, symbol, [symbol]) for symbol in sorted(PAIR_IDS))
    return [{'schema_version': '0.2.0', 'record_type': 'scope_definition',
             'id': identifier, 'version': VERSION, 'display_name': name,
             'body': {'kind': kind, 'entity_ids': sorted(metadata[m]['economic_id'] for m in members), **policy_refs}}
            for kind, identifier, name, members in specs]


def _snapshot_index(store):
    found = {}
    for path in sorted(store.path('storage/catalog/snapshots').glob('SNAPSHOT_*/manifest.json')):
        value = strict_json(stable_read(path))
        if value.get('schema_version') != '0.2.0' or value.get('layer') != 'membership':
            continue
        store._validate(value)
        if record_path(value) != str(path.relative_to(store.root)):
            raise ScopeError('Membership snapshot path differs from its identity')
        key = (value['definition']['id'], value['definition']['version'])
        found.setdefault(key, []).append(value)
    return found


def _resolution_metadata(store, resolution):
    body = resolution['body']
    if body.get('kind') != 'fixed_fx_scope_resolution' or body.get('profile') != PROFILE:
        raise ScopeError('Unsupported membership resolution profile')
    if body.get('period_meaning') != PERIOD_MEANING:
        raise ScopeError('Membership interval must not imply historical economic eligibility')
    rows = body.get('registered_instruments', [])
    metadata = {row['instrument_id']: row for row in rows}
    if len(metadata) != len(rows):
        raise ScopeError('Duplicate registered economic instruments in membership resolution')
    for row in rows:
        if _registration_metadata(store, row['instrument_registration']) != row:
            raise ScopeError('Pinned membership metadata differs from its instrument registration')
    resolve_groups(metadata)
    return metadata


def _scope_rows(definition, metadata):
    entities = set(definition['body']['entity_ids'])
    return [{'scope_id': definition['id'], 'scope_version': definition['version'], **deepcopy(row)}
            for symbol, row in sorted(metadata.items()) if row['economic_id'] in entities]


def _make_snapshot(definition, metadata, policies, evidence, resolution, period):
    rows = _scope_rows(definition, metadata)
    payload = b''.join(canonical_bytes(row) + b'\n' for row in rows)
    member = {'role': 'membership', 'blob_sha256': hashlib.sha256(payload).hexdigest(),
              'format': 'jsonl', 'byte_count': len(payload), 'row_count': len(rows)}
    value = {'schema_version': '0.2.0', 'record_type': 'snapshot_manifest', 'version': VERSION,
             'layer': 'membership', 'definition': reference(definition), 'period': period,
             'information_cutoff': period['start_inclusive'], 'members': [member],
             'semantic_content_sha256': digest(rows), 'record_count': len(rows),
             'upstream_snapshots': [], 'policy_bindings': [
                 {'role': p['body']['kind'], 'artifact': reference(p)} for p in policies],
             'implementation': None, 'lineage': [reference(resolution), reference(evidence)]}
    value['id'] = 'SNAPSHOT_' + digest(value)
    return value, payload


def _preflight(store, records, payloads):
    """Check all deterministic destination conflicts before publishing any record."""
    # Recheck inside the shared writer lock: a competing publisher may have
    # installed membership while this process was preparing its registration.
    current = _snapshot_index(store)
    for record in records:
        store._validate(record)
        if record['record_type'] == 'snapshot_manifest' and record.get('layer') == 'membership':
            previous = current.get((record['definition']['id'], record['definition']['version']), [])
            if previous and previous != [record]:
                raise ScopeConflict('A different membership snapshot already exists for ' + record['definition']['id'])
        relative = record_path(record)
        path = store.path(relative)
        if path.exists() and stable_read(path) != canonical_bytes(record) + b'\n':
            raise ScopeConflict('Incompatible immutable record: ' + relative)
        if record['record_type'] in ('scope_definition', 'policy_definition'):
            for other in path.parent.glob('*.json'):
                if other != path:
                    raise ScopeConflict('Existing name has another version requiring explicit resolution: ' + record['id'])
    for member, payload in payloads:
        path = store.path(f"storage/payloads/sha256/{member['blob_sha256'][:2]}/{member['blob_sha256']}.jsonl")
        if path.exists() and stable_read(path) != payload:
            raise ScopeConflict('Incompatible membership payload: ' + str(path.relative_to(store.root)))


def register_fx_scopes(root, request_text, *, registered_at=None):
    """Register 18 overlapping universes and 43 singleton scopes; repeat is a no-op.

    The request text is supplied by the CLI from the user's actual instruction.
    Existing matching memberships pin their original metadata evidence even when a
    newer price registration or readiness assessment becomes available.
    """
    store = FeatureStore(root)
    evidence = _request_evidence(request_text)
    policies = _policies(evidence)
    index = _snapshot_index(store)
    names = set(PAIR_IDS) | {row[0] for row in UNIVERSES}
    existing = [snapshot for (identifier, version), snapshots in index.items()
                if identifier in names and version == VERSION for snapshot in snapshots]
    if existing:
        first = existing[0]
        resolution = store.resolve(first['lineage'][0])
        metadata = _resolution_metadata(store, resolution)
        if resolution['body']['specification'] != reference(evidence):
            raise ScopeConflict('Stored scopes use a different approved specification')
        period = first['period']
    else:
        metadata = _metadata_from_registry(store)
        resolution = make_record('onboarding_evidence', {'kind': 'fixed_fx_scope_resolution',
            'profile': PROFILE, 'specification': reference(evidence), 'period_meaning': PERIOD_MEANING,
            'registered_instruments': [metadata[symbol] for symbol in sorted(metadata)]},
            'Pinned economic currency metadata for fixed FX scope membership')
        when = registered_at or datetime.now(timezone.utc)
        if when.tzinfo is None or when.utcoffset() != timedelta(0):
            raise ScopeError('Registration event requires a UTC timestamp')
        period = {'start_inclusive': when.strftime('%Y-%m-%dT%H:%M:%S.%fZ'),
                  'end_exclusive': (when + timedelta(microseconds=1)).strftime('%Y-%m-%dT%H:%M:%S.%fZ')}
    definitions = _definitions(metadata, policies)
    snapshots, payloads = [], []
    for definition in definitions:
        snapshot, payload = _make_snapshot(definition, metadata, policies, evidence, resolution, period)
        previous = index.get((definition['id'], definition['version']), [])
        if previous and previous != [snapshot]:
            raise ScopeConflict('Incompatible or ambiguous resolved membership for ' + definition['id'])
        snapshots.append(snapshot)
        payloads.append((snapshot['members'][0], payload))
    records = [evidence, resolution, *policies, *definitions, *snapshots]
    with store.writer():
        _preflight(store, records, payloads)
        # Payloads and referenced records precede discoverable scope definitions.
        for member, payload in payloads:
            store.io.blob(payload, 'jsonl', 'membership', member['row_count'])
        for record in [evidence, resolution, *policies, *snapshots, *definitions]:
            store.install_record(record)
    return {'schema_version': '1.0.0', 'universe_count': len(UNIVERSES),
            'instrument_scope_count': len(PAIR_IDS), 'scope_count': len(definitions),
            'membership_count': sum(s['record_count'] for s in snapshots),
            'universes': [{'id': d['id'], 'version': d['version'], 'display_name': d['display_name'],
                           'member_count': len(d['body']['entity_ids'])}
                          for d in definitions if d['body']['kind'] == 'universe'],
            'specification': reference(evidence), 'resolution': reference(resolution)}


def _readiness(members, current):
    rows = []
    for symbol in members:
        item = current.get(symbol, {})
        rows.append({'instrument_id': symbol, 'registered': bool(item),
                     'readiness_capabilities': deepcopy(item.get('readiness_capabilities', {})),
                     'price_coverage': deepcopy(item.get('price_coverage', {'start': None, 'end': None})),
                     'price_row_count': item.get('price_row_count', 0)})
    result = {'members': rows, 'note': NOTE,
              'registered_member_count': sum(r['registered'] for r in rows),
              'stored_price_member_count': sum(r['price_row_count'] > 0 for r in rows)}
    for label, capability in [('retrospective_ready_member_count', 'retrospective_research'),
                              ('historical_replay_ready_member_count', 'historical_replay'),
                              ('live_ready_member_count', 'live_use')]:
        result[label] = sum(r['readiness_capabilities'].get(capability, {}).get('decision') == 'ready' for r in rows)
    return result


def _resolve(store, definition, index, current):
    store._validate(definition)
    scope_ref = reference(definition)
    if store.resolve(scope_ref) != definition:
        raise ScopeError('Scope definition did not resolve its exact immutable reference')
    snapshots = index.get((definition['id'], definition['version']), [])
    if len(snapshots) != 1:
        raise ScopeError('Scope requires exactly one unambiguous fixed membership snapshot')
    snapshot = snapshots[0]
    raw = {k: v for k, v in snapshot.items() if k != 'id'}
    if snapshot['id'] != 'SNAPSHOT_' + digest(raw) or snapshot['definition'] != scope_ref:
        raise ScopeError('Membership snapshot identity or definition binding differs')
    if snapshot['upstream_snapshots'] or snapshot['implementation'] is not None or len(snapshot['lineage']) != 2:
        raise ScopeError('Unexpected dependencies for fixed research membership')
    resolution, evidence = [store.resolve(ref) for ref in snapshot['lineage']]
    if evidence.get('body', {}).get('kind') != 'fixed_fx_scope_specification':
        raise ScopeError('Membership specification is not approved FX grouping evidence')
    if _request_evidence(evidence['body']['request_text']) != evidence:
        raise ScopeError('Membership grouping rules or request evidence differ')
    if resolution['body'].get('specification') != reference(evidence):
        raise ScopeError('Resolved membership uses another grouping specification')
    metadata = _resolution_metadata(store, resolution)
    policies = _policies(evidence)
    for policy in policies:
        if store.resolve(reference(policy)) != policy:
            raise ScopeError('Membership policy differs from its approved exact version')
    expected = {d['id']: d for d in _definitions(metadata, policies)}
    if expected.get(definition['id']) != definition:
        raise ScopeError('Stored scope does not follow the approved exact economic membership rules')
    expected_snapshot, payload = _make_snapshot(definition, metadata, policies, evidence, resolution, snapshot['period'])
    if expected_snapshot != snapshot or store.payload(snapshot['members'][0]) != payload:
        raise ScopeError('Stored membership rows differ from the registered scope or pinned economic metadata')
    if snapshot['period']['start_inclusive'] >= snapshot['period']['end_exclusive']:
        raise ScopeError('Invalid document registration interval')
    rows = _scope_rows(definition, metadata)
    members = [row['instrument_id'] for row in rows]
    binding = reference(snapshot)
    return {'id': definition['id'], 'version': definition['version'], 'kind': definition['body']['kind'],
            'display_name': definition['display_name'], 'reference': scope_ref,
            'member_count': len(members), 'members': members,
            'economic_entity_ids': definition['body']['entity_ids'], 'membership_snapshot': binding,
            'readiness': _readiness(members, current), 'experiment_scope': {
                'id': definition['id'], 'version': definition['version']},
            'definition_binding': scope_ref,
            'dependency': {'requirement': 'required', 'bindings': [
                {'role': 'membership', 'artifact': binding},
                *[{'role': p['body']['kind'] + '_policy', 'artifact': reference(p)} for p in policies]]}}


def _scope_path(store, identifier, version):
    if not isinstance(identifier, str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_.-]{0,127}', identifier):
        raise ScopeError('Invalid scope identifier')
    if not isinstance(version, str) or not re.fullmatch(r'(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)', version):
        raise ScopeError('Invalid exact scope version')
    return store.path(f'definitions/scopes/{identifier}/{version}.json')


def resolve_scope(root, identifier, version):
    """Resolve one exact version into the existing experiment dependency contract."""
    store = FeatureStore(root)
    path = _scope_path(store, identifier, version)
    if not path.is_file():
        raise ScopeNotFound('Scope version is not registered: ' + identifier + '@' + version)
    definition = strict_json(stable_read(path))
    if record_path(definition) != str(path.relative_to(store.root)):
        raise ScopeError('Scope definition path does not match its identity')
    current = {item['instrument_id']: item for item in list_instruments(root)}
    return _resolve(store, definition, _snapshot_index(store), current)


def list_scopes(root):
    """Registry projection; unsupported/unavailable scopes are reported, never hidden as ready."""
    store = FeatureStore(root)
    index = _snapshot_index(store)
    current = {item['instrument_id']: item for item in list_instruments(root)}
    scopes, issues = [], []
    for path in sorted(store.path('definitions/scopes').glob('*/*.json')):
        try:
            definition = strict_json(stable_read(path))
            if record_path(definition) != str(path.relative_to(store.root)):
                raise ScopeError('Scope path differs from its declared identity')
            scopes.append(_resolve(store, definition, index, current))
        except (ValueError, KeyError, OSError, TypeError):
            issues.append({'scope_id': path.parent.name, 'version': path.stem,
                           'reason': 'Stored scope could not be verified'})
    scopes.sort(key=lambda item: (item['kind'], item['display_name'], item['id'], item['version']))
    return {'schema_version': '1.0.0', 'scope_count': len(scopes), 'scopes': scopes, 'issues': issues}
