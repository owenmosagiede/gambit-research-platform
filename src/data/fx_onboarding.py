"""Read-only legacy FX import into the shared raw/PIT catalog and payload store.

The date is a provider bar label. Historical availability, valuation instant,
source vintage and price basis remain unknown. The original capture clock is
preserved separately. Only the exact requested production close records enter
this snapshot; omitted incomplete bars stay in immutable raw evidence.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import gzip
from pathlib import Path

from data.alfred_onboarding import canonical, sha, stable_read, strict_json
from data.feature_store import FeatureStore
from data.transformations.identity import digest, reference
from data.fx_records import make_record, read_rows, register_locator, write_rows

SOURCE_SYMBOLS = (
    'AUD/USD', 'EUR/USD', 'GBP/USD', 'NZD/USD', 'USD/CNH',
    'CAD/USD', 'CHF/USD', 'JPY/USD', 'CZK/USD', 'HKD/USD', 'HUF/USD',
    'ILS/USD', 'MXN/USD', 'NOK/USD', 'PLN/USD', 'SEK/USD', 'SGD/USD', 'ZAR/USD',
)
PROFILE = 'fx_snapshot.1.0.0'
READINESS = {
    'historical_replay': 'blocked',
    'live_api_daily_pull': 'unresolved',
    'exact_synchronization': 'blocked',
}
LIMITATIONS = (
    'HISTORICAL_AVAILABILITY_UNKNOWN', 'RETROSPECTIVE_VENDOR_SNAPSHOT',
    'SESSION_CLOSE_UNVERIFIED', 'SOURCE_TIMEZONE_UNVERIFIED',
    'PRICE_BASIS_UNKNOWN', 'LIVE_CAPABILITY_NOT_CERTIFIED',
)


class FXOnboardingError(ValueError):
    pass


class InterruptedOnboarding(RuntimeError):
    """Deterministic test interruption; completed immutable work remains reusable."""


def _legacy_path(root, relative):
    path = root / relative
    if path.is_symlink() or not path.resolve().is_relative_to(root):
        raise FXOnboardingError('Legacy artifact leaves the approved source root')
    return path


def _utc(value):
    if not isinstance(value, str) or not value.endswith('Z'):
        raise FXOnboardingError('Original ingestion time must be a known UTC timestamp')
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as exc:
        raise FXOnboardingError('Malformed original ingestion time') from exc
    if parsed.utcoffset().total_seconds() != 0:
        raise FXOnboardingError('Non-UTC original ingestion time')
    return value


def _decimal(value):
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise FXOnboardingError('Invalid source close') from exc
    if not number.is_finite() or number <= 0:
        raise FXOnboardingError('Required source close must be finite and positive')
    text = format(number, 'f')
    return text.rstrip('0').rstrip('.') if '.' in text else text


def _coverage(rows):
    dates = [row['reference_time'] for row in rows]
    return {'start': min(dates), 'end': max(dates)}


def _metadata(source):
    base, quote = source['symbol'].split('/')
    if source['base_currency'] != base or source['quote_currency'] != quote:
        raise FXOnboardingError('Audited quotation direction differs from source identity')
    unit = f'{quote}_per_{base}'
    if source['units'] != [unit]:
        raise FXOnboardingError('Audited price units differ from explicit source direction')
    return {
        'provider': 'Twelve Data', 'provider_symbol': source['symbol'],
        'base_currency': base, 'quote_currency': quote, 'unit': unit,
        'frequency': 'daily', 'price_field': 'close', 'price_basis': 'unknown',
        'timing': {'timezone': None, 'bar_boundary': None,
                   'session_convention': None, 'synchronization': 'unverified'},
        'timestamp_precision': 'date', 'provenance_classification': 'retrospective_snapshot',
        'historical_availability': None, 'historical_vintages_verified': False,
        'source_calendar': None, 'native_vintage_policy': 'captured_snapshot_only',
    }


def inspect_source(legacy_root, source):
    """Validate bytes and expose only audited completed source closes.

    This function is usable without writes. Every canonical close is reconciled
    with its exact raw provider row and original ingestion manifest.
    """
    legacy_root = Path(legacy_root).resolve()
    symbol = source['symbol']
    if symbol not in SOURCE_SYMBOLS:
        raise FXOnboardingError('Source is outside the exact requested scope')
    metadata = _metadata(source)
    expected_dataset = 'DS_TWELVE_' + symbol.replace('/', '_')
    if source['dataset_id'] != expected_dataset:
        raise FXOnboardingError('Unexpected legacy dataset identity')
    pair_root = legacy_root / 'production/twelve_data_fx' / ('symbol=' + symbol.replace('/', '_'))
    stored_pages = {str(p.parent.relative_to(legacy_root)) for p in pair_root.glob('page=*/observations.jsonl.gz')}
    audited_pages = [p['directory'] for p in source['pages']]
    if len(audited_pages) != len(set(audited_pages)) or set(audited_pages) != stored_pages:
        raise FXOnboardingError('Audit does not enumerate every stored historical page exactly once')
    rows, lineage, page_evidence = [], [], []
    seen = {}
    for page in sorted(source['pages'], key=lambda p: p['directory']):
        directory = _legacy_path(legacy_root, page['directory'])
        if directory.parent.name != 'symbol=' + symbol.replace('/', '_'):
            raise FXOnboardingError('Page belongs to a different source')
        page_manifest = strict_json(stable_read(directory / 'page-manifest.json'))
        ingestion_document = strict_json(stable_read(directory / 'raw-ingestion-manifest.json'))
        ingestions = ingestion_document['ingestions']
        if len(ingestions) != 1:
            raise FXOnboardingError('Expected one exact ingestion per canonical page')
        ingestion = ingestions[0]
        capture = _utc(ingestion['retrieved_at'])
        if capture != page['retrieved_at'] or ingestion['ingestion_id'] != page['ingestion_id']:
            raise FXOnboardingError('Original ingestion evidence changed after audit')
        if ingestion['raw_file_location'] != page['raw_path']:
            raise FXOnboardingError('Raw artifact binding changed after audit')
        raw_path = _legacy_path(legacy_root, page['raw_path'])
        raw_bytes = stable_read(raw_path, page['raw_sha256'])
        if sha(raw_bytes) != ingestion['checksum']['value']:
            raise FXOnboardingError('Raw ingestion checksum differs')
        raw = strict_json(raw_bytes)
        if raw['meta'].get('symbol') != symbol or raw['meta'].get('interval') != '1day':
            raise FXOnboardingError('Raw provider identity or frequency mismatch')
        dataset = strict_json(stable_read(directory / 'dataset-registry.json'))['datasets']
        if len(dataset) != 1 or dataset[0]['dataset_id'] != expected_dataset:
            raise FXOnboardingError('Canonical dataset registry differs')
        ds = dataset[0]
        if ds['source_dataset_id'] != symbol or ds['unit'] != metadata['unit'] or ds['frequency'] != 'daily':
            raise FXOnboardingError('Registry source, direction, units or frequency differ')
        canonical_bytes = stable_read(_legacy_path(legacy_root, page['observation_path']), page['observation_sha256'])
        if sha(canonical_bytes) != page_manifest['observations_checksum_sha256']:
            raise FXOnboardingError('Canonical page checksum differs')
        original_rows = [strict_json(line) for line in gzip.decompress(canonical_bytes).splitlines()]
        if len(original_rows) != page['actual_ohlc_rows'] or len(original_rows) != page_manifest['observation_count']:
            raise FXOnboardingError('Canonical page row count differs from audit or manifest')
        raw_by_date = defaultdict(list)
        for index, value in enumerate(raw['values']):
            raw_by_date[value['datetime'][:10]].append((index, value))
        close_count = 0
        for index, original in enumerate(original_rows):
            if original['dimensions'].get('price_field') != 'close':
                continue
            close_count += 1
            day = original['observation_date']
            date.fromisoformat(day)
            if day in seen:
                reason = 'Conflicting' if seen[day] != original['value'] else 'Duplicate'
                raise FXOnboardingError(reason + ' completed source observation')
            seen[day] = original['value']
            if original['dataset_id'] != expected_dataset or original['unit'] != metadata['unit']:
                raise FXOnboardingError('Canonical row identity or units differ')
            if original['retrieved_at'] != capture or original['ingestion_id'] != ingestion['ingestion_id']:
                raise FXOnboardingError('Canonical row ingestion evidence differs')
            if original['vintage_id'] != capture or original['revision_number'] != 0 or 'vendor_history_snapshot' not in original['quality_flags']:
                raise FXOnboardingError('Unexpected vintage profile requires explicit reconciliation')
            # A capture on/before a displayed bar date cannot prove that bar final.
            # This is only the legacy exclusion boundary, never a publication rule.
            if day >= capture[:10]:
                raise FXOnboardingError('Incomplete or future-at-capture daily bar')
            candidates = raw_by_date.get(day, [])
            if not candidates:
                raise FXOnboardingError('Canonical row has no raw provider cell')
            distinct = {_decimal(value['close']) for _, value in candidates}
            if len(distinct) != 1 or _decimal(original['value']) not in distinct:
                raise FXOnboardingError('Conflicting or unreconciled raw close')
            raw_index, raw_row = candidates[0]
            value = _decimal(raw_row['close'])
            core = {
                'reference_time': day, 'observation_date': day,
                'entity_id': 'FX_' + symbol.replace('/', ''),
                'value': value, 'status': 'valid', 'reason_code': None,
                'available_at': None, 'original_ingested_at': capture,
                'source_vintage_at': None, 'legacy_vintage_id': original['vintage_id'],
                'legacy_revision_number': original['revision_number'],
                'vintage_id': 'LEGACY_' + digest(capture),
                'source_record_id': original['source_record_id'],
                'source_ingestion_id': ingestion['ingestion_id'],
                'base_currency': metadata['base_currency'], 'quote_currency': metadata['quote_currency'],
                'unit': metadata['unit'], 'source_precision': 'date',
            }
            key = digest(core)
            rows.append(dict(core, lineage_key=key, lineage='FXSOURCE_' + key))
            lineage.append({
                'reference_time': day, 'lineage_key': key, 'lineage': 'FXSOURCE_' + key,
                'source_row_content_sha256': digest(core),
                'legacy_row_sha256': sha(canonical(original)),
                'legacy_canonical_path': page['observation_path'],
                'legacy_canonical_sha256': page['observation_sha256'],
                'legacy_canonical_row_index': index,
                'raw_blob_sha256': page['raw_sha256'], 'raw_relative_path': page['raw_path'],
                'raw_row_index': raw_index, 'raw_datetime': raw_row['datetime'],
                'raw_field': 'close', 'raw_value': raw_row['close'],
                'raw_row_sha256': digest(raw_row),
                'legacy_available_at': original.get('available_at'),
                'legacy_original_release_at': original.get('original_release_at'),
                'legacy_availability_precision': original.get('timestamp_precision'),
                'availability_evidence_disposition': 'adapter_inference_not_historical_evidence',
                'original_ingested_at': capture,
            })
        if close_count != page['actual_close_rows']:
            raise FXOnboardingError('Completed close count differs from audited page')
        page_evidence.append({
            'canonical_path': page['observation_path'], 'canonical_sha256': page['observation_sha256'],
            'raw_path': page['raw_path'], 'raw_sha256': page['raw_sha256'],
            'ingestion_id': ingestion['ingestion_id'], 'original_ingested_at': capture,
            'ingestion_manifest_sha256': digest(ingestion_document),
            'close_count': close_count,
        })
    rows.sort(key=lambda row: row['reference_time'])
    lineage.sort(key=lambda row: row['reference_time'])
    if not rows or len(rows) != source['actual_close_rows'] or len(rows) != source['unique_close_dates']:
        raise FXOnboardingError('Completed source count differs from audited full history')
    coverage = _coverage(rows)
    if coverage != {'start': source['coverage_min'], 'end': source['coverage_max']}:
        raise FXOnboardingError('Completed source coverage differs from audit')
    return {'metadata': metadata, 'observations': rows, 'lineage': lineage,
            'coverage': coverage, 'pages': page_evidence}


def _install(store, kind, body, display_name=None):
    record = make_record(kind, body, display_name=display_name)
    store.install_record(record)
    return record, reference(record)


def _onboard_source(store, legacy_root, source, *, interrupt_after=None):
    verified = inspect_source(legacy_root, source)
    symbol = source['symbol']
    metadata = verified['metadata']
    raw_members, artifacts = [], []
    for artifact in sorted(source['all_raw_artifacts'], key=lambda a: a['path']):
        path = _legacy_path(legacy_root, artifact['path'])
        data = stable_read(path, artifact['sha256'])
        raw = strict_json(data)
        if raw['meta'].get('symbol') != symbol:
            raise FXOnboardingError('Audited raw artifact belongs to another source')
        member = register_locator(store, path, legacy_root)
        if member['blob_sha256'] != artifact['sha256'] or member['byte_count'] != len(data):
            raise FXOnboardingError('Registered raw locator differs from verified bytes')
        raw_members.append(member)
        artifacts.append({
            'legacy_relative_path': artifact['path'], 'blob_sha256': artifact['sha256'],
            'row_count': len(raw['values']), 'known_ingestions': artifact['known_ingestions'],
        })
    evidence, evidence_ref = _install(store, 'onboarding_evidence', {
        'kind': 'fx_source_audit', 'profile': PROFILE, 'symbol': symbol,
        'completed_coverage': verified['coverage'], 'completed_close_count': len(verified['observations']),
        'legacy_pages': verified['pages'], 'raw_artifacts': artifacts,
        'excluded_raw_dates': source['raw_dates_absent_from_canonical'],
        'suspicious_change_count': len(source.get('suspicious_changes', [])),
        'suspicious_change_policy': source.get('suspicious_change_audit_rule'),
        'source_audit_member': store.io.blob(canonical(source), 'json', 'fx_source_audit'),
        'implementation_members': [store.io.blob(stable_read(Path(__file__)), 'txt', 'fx_onboarding_implementation')],
    })
    policy, policy_ref = _install(store, 'policy_definition', {
        'kind': 'fx_snapshot_import_policy', 'profile': PROFILE,
        'availability': 'unknown_historical_availability',
        'vintage': 'retrospective_snapshot_original_capture_preserved',
        'selection': 'exact_audited_completed_production_closes',
        'quality': 'finite_positive_unique_raw_reconciled_close',
        'alignment': 'native_date_preserved_no_exact_synchronization_claim',
        'basis': 'unknown_no_midpoint_assumption',
        'future_at_capture': 'exclude_without_later_finalization_evidence',
        'scientific_research_approval': None,
    }, 'Legacy FX snapshot preservation policy')
    provider, provider_ref = _install(store, 'provider_contract', {
        'kind': 'fx_provider_contract', 'profile': PROFILE, **metadata,
        'policy': policy_ref,
        'requested_scope': 'legacy_history_import',
        'live_readiness': 'unresolved',
    }, symbol + ' legacy Twelve Data close')
    dataset, dataset_ref = _install(store, 'dataset_definition', {
        'kind': 'fx_source_dataset', 'profile': PROFILE, 'source_contract': provider_ref,
        'economic_entity_ids': ['FX_' + symbol.replace('/', '')],
        'fields': [{'name': 'value', 'data_type': 'decimal', 'unit': metadata['unit'], 'nullable': False}],
        'event_time_field': 'reference_time', 'availability_time_field': 'available_at',
        'ingestion_time_field': 'original_ingested_at', 'revision_key_fields': ['vintage_id'],
        'policy': policy_ref, 'source_metadata': metadata,
    }, symbol + ' daily source closes')
    view, view_ref = _install(store, 'source_view_definition', {
        'kind': 'fx_source_view', 'profile': PROFILE, 'dataset': dataset_ref,
        'fields': ['value'], 'selection': 'completed_production_close',
        'policy': policy_ref, 'source_metadata': metadata,
    }, symbol + ' captured close history')
    raw_snapshot, raw_ref = _install(store, 'snapshot_manifest', {
        'kind': 'fx_raw_snapshot', 'profile': PROFILE, 'definition': dataset_ref,
        'upstream_snapshots': [], 'members': raw_members,
        'record_count': sum(a['row_count'] for a in artifacts),
        'coverage': {'start': min(a['date_min'] for a in source['all_raw_artifacts']),
                     'end': max(a['date_max'] for a in source['all_raw_artifacts'])},
        'semantic_content_sha256': digest(artifacts), 'source_evidence': evidence_ref,
        'policy': policy_ref, 'source_metadata': metadata,
        'readiness': dict(READINESS),
    })
    ingestion_refs = []
    for page in verified['pages']:
        _, ingestion_ref = _install(store, 'ingestion_receipt', {
            'kind': 'fx_legacy_ingestion', 'profile': PROFILE, 'mode': 'legacy_import',
            'dataset': dataset_ref, 'provider_contract': provider_ref,
            'raw_snapshot': raw_ref, 'legacy_ingestion_id': page['ingestion_id'],
            'original_ingested_at': page['original_ingested_at'],
            'source_vintage_at': None, 'historical_available_at': None,
            'source_evidence': page,
        })
        ingestion_refs.append(ingestion_ref)
    if interrupt_after == 'raw':
        raise InterruptedOnboarding('Interrupted after immutable raw evidence; no source PIT seal')
    members = write_rows(store, verified['observations'], 'fx_source_observations')
    lineage_members = write_rows(store, verified['lineage'], 'fx_source_lineage')
    body = {
        'kind': 'fx_source_snapshot', 'profile': PROFILE, 'definition': view_ref,
        'upstream_snapshots': [raw_ref], 'members': members,
        'lineage_members': lineage_members, 'record_count': len(verified['observations']),
        'coverage': verified['coverage'],
        'semantic_content_sha256': digest(verified['observations']),
        'semantic_lineage_sha256': digest(verified['lineage']),
        'source_metadata': metadata, 'source_evidence': evidence_ref, 'policy': policy_ref,
        'original_ingestions': ingestion_refs,
        'readiness': dict(READINESS), 'limitation_codes': list(LIMITATIONS),
        'original_ingestion_times': sorted({r['original_ingested_at'] for r in verified['observations']}),
        'completion_state': 'complete',
    }
    pit_snapshot = make_record('snapshot_manifest', body)
    existed = store.path(f"storage/catalog/snapshots/{pit_snapshot['id']}/manifest.json").exists()
    if interrupt_after == 'payloads':
        raise InterruptedOnboarding('Interrupted after immutable payloads; no source PIT seal')
    # Shared closure verification and a fresh payload read precede the final seal.
    store.verify_closure([provider, dataset, view, raw_snapshot])
    if read_rows(store, members) != verified['observations'] or read_rows(store, lineage_members) != verified['lineage']:
        raise FXOnboardingError('Stored source payload does not reproduce validated inputs')
    store.install_record(pit_snapshot)
    assessments = []
    for capability, decision in (('historical_replay', 'blocked'), ('live_api_daily_pull', 'unresolved')):
        _, assessment_ref = _install(store, 'capability_assessment', {
            'kind': 'fx_source_readiness', 'profile': PROFILE, 'capability': capability,
            'decision': decision, 'dataset': dataset_ref, 'provider_contract': provider_ref,
            'snapshot': reference(pit_snapshot), 'policy': policy_ref, 'evidence': [evidence_ref],
            'coverage': verified['coverage'], 'limitation_codes': list(LIMITATIONS),
        })
        assessments.append(assessment_ref)
    return {
        'symbol': symbol, 'metadata': metadata, 'dataset': dataset_ref,
        'source_view': view_ref, 'provider_contract': provider_ref,
        'raw_snapshot': raw_ref, 'pit_snapshot': reference(pit_snapshot),
        'source_evidence': evidence_ref, 'ingestions': ingestion_refs,
        'readiness_records': assessments, 'row_count': len(verified['observations']),
        'coverage': verified['coverage'], 'readiness': dict(READINESS),
        'limitation_codes': list(LIMITATIONS), 'reused': existed,
    }


def onboard(root, legacy_root, audit_path, *, migration_time, interrupt_after=None):
    """Preserve all 18 audited source histories, then publish one completion seal.

    No provider request, credential read, legacy mutation or source substitution
    occurs. The initial migration time is operational metadata only and excluded
    from source, row and snapshot identities. A repeat reuses the original seal.
    """
    _utc(migration_time)
    root, legacy_root = Path(root).resolve(), Path(legacy_root).resolve()
    if root == legacy_root or root.is_relative_to(legacy_root):
        raise FXOnboardingError('Destination cannot be a legacy source location')
    audit_bytes = stable_read(audit_path)
    audit = strict_json(audit_bytes)
    sources = audit['sources']
    symbols = [s['symbol'] for s in sources]
    if len(symbols) != 18 or len(set(symbols)) != 18 or set(symbols) != set(SOURCE_SYMBOLS):
        raise FXOnboardingError('Audit must contain exactly the requested 18 source series')
    store = FeatureStore(root)
    by_symbol = {s['symbol']: s for s in sources}
    result = []
    with store.writer():
        for symbol in SOURCE_SYMBOLS:
            result.append(_onboard_source(store, legacy_root, by_symbol[symbol], interrupt_after=interrupt_after))
        scientific = {'profile': PROFILE, 'sources': [{k: v for k, v in s.items() if k != 'reused'} for s in result]}
        identifier = 'ONBOARDING_' + digest(scientific)
        relative = f'storage/catalog/onboarding/runs/{identifier}.json'
        path = store.path(relative)
        if path.exists():
            seal = strict_json(stable_read(path))
            if seal['scientific'] != scientific:
                raise FXOnboardingError('Immutable onboarding seal conflicts')
        else:
            seal = {'schema_version': '0.5.0', 'profile': PROFILE, 'status': 'complete',
                    'id': identifier, 'scientific': scientific, 'migration_time': migration_time,
                    'audit_sha256': sha(audit_bytes), 'source_count': 18,
                    'row_count': sum(s['row_count'] for s in result)}
            if interrupt_after == 'sources':
                raise InterruptedOnboarding('Source snapshots complete; run completion not sealed')
            store.io.install(relative, canonical(seal) + b'\n')
    return {'profile': PROFILE, 'sources': result, 'source_count': 18,
            'row_count': sum(s['row_count'] for s in result),
            'reused': all(s['reused'] for s in result),
            'completion_path': relative, 'migration_time': seal['migration_time']}


def read_source(root, pit_snapshot):
    """Read and verify sealed source observations from persisted shared artifacts."""
    store = FeatureStore(root)
    manifest = store.resolve(pit_snapshot)
    body = manifest.get('body', {})
    if body.get('profile') != PROFILE or body.get('kind') != 'fx_source_snapshot' or body.get('completion_state') != 'complete':
        raise FXOnboardingError('Not a completed FX source snapshot')
    store.verify_closure([manifest])
    rows = read_rows(store, body['members'])
    lineage = read_rows(store, body['lineage_members'])
    if len(rows) != body['record_count'] or digest(rows) != body['semantic_content_sha256'] or digest(lineage) != body['semantic_lineage_sha256']:
        raise FXOnboardingError('FX source semantic integrity failure')
    by_key = {item['lineage_key']: item for item in lineage}
    if len(by_key) != len(rows) or _coverage(rows) != body['coverage']:
        raise FXOnboardingError('Source row lineage or coverage mismatch')
    for row in rows:
        core = {k: v for k, v in row.items() if k not in ('lineage_key', 'lineage')}
        key = digest(core)
        if key != row['lineage_key'] or row['lineage'] != 'FXSOURCE_' + key or key not in by_key:
            raise FXOnboardingError('Source lineage does not resolve exactly')
        if row['available_at'] is not None or row['source_vintage_at'] is not None:
            raise FXOnboardingError('Imported snapshot gained unsupported historical availability')
    return {'manifest': manifest, 'observations': rows, 'lineage': lineage,
            'metadata': body['source_metadata']}
