"""Fixed companion currency universes for matched spot/funding comparisons.

CNH is excluded by the declared funding model, never by observed performance or
date-specific coverage. The original eighteen-member currency Scopes are intact.
"""
from datetime import datetime, timedelta, timezone

from data.feature_store import FeatureStore
from data.fx_currency_catalog import resolve_prices
from data.fx_records import make_record
from data.targets.fx_total import policy
from data.transformations import fx_currency as currency
from data.transformations.identity import reference

PROFILE = 'funded_currency_scopes.1.0.0'
SCOPE_IDS = tuple('FX_CCY_FUNDED_VS_' + q for q in currency.REFERENCES)
EXCLUDED = ['CNH']


def members(quote):
    return [symbol for symbol in currency.members(quote) if symbol[:3] not in EXCLUDED]


def eligibility():
    return {'funding_model': reference(policy()), 'excluded_currencies': EXCLUDED[:],
            'paired_membership': 'same_fixed_members_for_both_return_families'}


def validate_basis(scope):
    quote = scope.get('reference_currency')
    if (quote not in currency.REFERENCES or scope.get('id') != 'FX_CCY_FUNDED_VS_' + quote
            or scope.get('version') != '1.0.0' or scope.get('members') != members(quote)
            or scope.get('funding_eligibility') != eligibility()):
        raise ValueError('Financed currency Scope must freeze the exact seventeen-member comparison')


def _records(catalog, instruments, request_text):
    if not isinstance(request_text, str) or not request_text.strip():
        raise ValueError('Explicit matched currency-universe request evidence is required')
    evidence = make_record('onboarding_evidence', {
        'kind': 'funded_currency_scope_specification', 'profile': PROFILE,
        'price_catalog': reference(catalog), 'request_text': request_text,
        'eligibility': eligibility(), 'membership': 'all_supported_non_reference_currencies_except_CNH',
        'member_order': 'currency_code_ascending', 'readiness_filtering': False,
        'missing_funding': 'retain_unavailable_rows_and_apply_complete_date_CS_rules'})
    policies = [{'schema_version': '0.2.0', 'record_type': 'policy_definition',
        'id': 'POLICY_FX_FUNDED_CURRENCY_' + kind.upper(), 'version': '1.0.0',
        'display_name': 'Financed currency Scope ' + kind,
        'body': {'kind': kind, 'specification': reference(evidence), 'parameters': [],
                 'approval_state': 'approved', 'compatibility_evidence': []}}
        for kind in ('membership', 'eligibility', 'exclusion')]
    definitions = [{'schema_version': '0.2.0', 'record_type': 'scope_definition',
        'id': 'FX_CCY_FUNDED_VS_' + q, 'version': '1.0.0',
        'display_name': q + ' currencies - matched Spot + Total Return (17 members)',
        'body': {'kind': 'universe',
                 'entity_ids': sorted(instruments[s]['economic_id'] for s in members(q)),
                 **{p['body']['kind'] + '_policy': reference(p) for p in policies}}}
        for q in currency.REFERENCES]
    metadata = {s: {'instrument_id': s, 'economic_id': r['economic_id'],
        'base_currency': r['source_metadata']['base_currency'],
        'quote_currency': r['source_metadata']['quote_currency'],
        'instrument_registration': r['registration']} for s, r in instruments.items()}
    resolution = make_record('onboarding_evidence', {'kind': 'funded_currency_scope_resolution',
        'profile': PROFILE, 'specification': reference(evidence), 'price_catalog': reference(catalog),
        'registered_instruments': [metadata[s] for s in sorted(metadata)]})
    return evidence, policies, definitions, metadata, resolution


def register(root, catalog_ref, request_text, *, registered_at=None):
    """Stage additive definitions; the separate CS release pointer activates them."""
    from data.scopes import _make_snapshot, _snapshot_index, _preflight
    store = FeatureStore(root)
    catalog, instruments = resolve_prices(root, catalog_ref)
    evidence, policies, definitions, metadata, resolution = _records(catalog, instruments, request_text)
    index = _snapshot_index(store)
    prior = [s for (identifier, _), values in index.items() if identifier in SCOPE_IDS for s in values]
    when = registered_at or datetime.now(timezone.utc)
    if when.utcoffset() != timedelta(0):
        raise ValueError('UTC registration timestamp required')
    period = prior[0]['period'] if prior else {
        'start_inclusive': when.strftime('%Y-%m-%dT%H:%M:%S.%fZ'),
        'end_exclusive': (when + timedelta(microseconds=1)).strftime('%Y-%m-%dT%H:%M:%S.%fZ')}
    snapshots, payloads = [], []
    for definition in definitions:
        snapshot, payload = _make_snapshot(definition, metadata, policies, evidence, resolution, period)
        snapshots.append(snapshot)
        payloads.append((snapshot['members'][0], payload))
    records = [evidence, resolution, *policies, *snapshots, *definitions]
    with store.writer():
        _preflight(store, records, payloads)
        for member, payload in payloads:
            store.io.blob(payload, 'jsonl', 'membership', member['row_count'])
        for record in records:
            store.install_record(record)
    return {d['id']: reference(d) for d in definitions}


def resolve(store, definition, index):
    from data.fx_total_return_cs import load_release
    from data.scopes import _make_snapshot, _readiness
    config = load_release(store.root)
    if config['scopes'].get(definition['id']) != reference(definition):
        raise ValueError('Financed currency Scope is not selected by the frozen funding release')
    snapshots = index.get((definition['id'], definition['version']), [])
    if len(snapshots) != 1:
        raise ValueError('Financed currency Scope requires one exact membership snapshot')
    snapshot = snapshots[0]
    if (snapshot['period']['start_inclusive'] >= snapshot['period']['end_exclusive']
            or len(snapshot['lineage']) != 2):
        raise ValueError('Invalid financed currency membership lineage or interval')
    resolution, evidence = [store.resolve(binding) for binding in snapshot['lineage']]
    catalog, instruments = resolve_prices(store.root, config['price_catalog'])
    expected = _records(catalog, instruments, evidence['body']['request_text'])
    spec, policies, definitions, metadata, expected_resolution = expected
    if (evidence != spec or resolution != expected_resolution or definition not in definitions
            or store.resolve(reference(definition)) != definition
            or reference(spec) != config['scope_specification']):
        raise ValueError('Financed currency membership differs from its exact specification')
    for p in policies:
        if store.resolve(reference(p)) != p:
            raise ValueError('Financed currency membership policy differs')
    expected_snapshot, payload = _make_snapshot(definition, metadata, policies, spec, resolution, snapshot['period'])
    if snapshot != expected_snapshot or store.payload(snapshot['members'][0]) != payload:
        raise ValueError('Financed currency membership content differs')
    quote = definition['id'].removeprefix('FX_CCY_FUNDED_VS_')
    binding = reference(snapshot)
    return {'id': definition['id'], 'version': definition['version'], 'kind': 'universe',
        'display_name': definition['display_name'], 'reference': reference(definition),
        'definition_binding': reference(definition), 'member_count': 17, 'members': members(quote),
        'economic_entity_ids': definition['body']['entity_ids'], 'membership_snapshot': binding,
        'research_basis': 'currency_against_quote_reference', 'reference_currency': quote,
        'price_catalog': reference(catalog), 'funding_eligibility': eligibility(),
        'readiness': _readiness(members(quote), instruments),
        'experiment_scope': {'id': definition['id'], 'version': definition['version']},
        'dependency': {'requirement': 'required', 'bindings': [
            {'role': 'membership', 'artifact': binding},
            {'role': 'currency_prices', 'artifact': reference(catalog)},
            {'role': 'funding_model', 'artifact': reference(policy())},
            *[{'role': p['body']['kind'] + '_policy', 'artifact': reference(p)} for p in policies]]}}
