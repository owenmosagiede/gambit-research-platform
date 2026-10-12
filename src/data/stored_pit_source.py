"""Read-only resolution of a registered stored PIT source into adapter inputs.

Provider field interpretation belongs here, upstream of the generic numeric
adapter and recipe engine. This module never infers an evaluation schedule,
calculates features, downloads evidence, repairs an index, or publishes data.
The native series identity and all scientific source pins come from the request.
"""
from __future__ import annotations
from pathlib import Path

from api.pit_library import definition, verified_item
from data.alfred_onboarding import ref, stable_read, strict_json
from data.alfred_pit import inside
from data.alfred_full_history import read_pit, load_package, payload_record_bytes
from data.transformations.contracts import (normalize_reference, normalize_selection,
                                            object_fields, token)

PROFILE = 'alfred_full_history_vintage_date'


class SourceResolutionError(ValueError):
    """The requested registered source cannot be truthfully resolved and pinned."""


def _record(store, binding):
    record = store.records[(binding['id'], binding['version'])]
    if ref(record) != binding:
        raise SourceResolutionError('Source record differs from its pinned reference')
    return record


def _resolve_dataset(root, native_series_id, expected):
    # Resolve the actual registry relationship instead of decoding a native ID
    # into a fabricated canonical name or silently choosing its newest version.
    matches = []
    for path in sorted(inside(root, 'definitions/datasets').glob('*/*.json')):
        candidate = strict_json(stable_read(path))
        if candidate.get('record_type') != 'dataset_definition':
            raise SourceResolutionError('Dataset registry contains a non-dataset record')
        provider = definition(root, 'providers', candidate['body']['source_contract'], 'provider_contract')
        if provider['body']['native_series_id'] == native_series_id and ref(candidate) == expected:
            resolved = definition(root, 'datasets', expected, 'dataset_definition')
            if path.resolve() != inside(root, f"definitions/datasets/{expected['id']}/{expected['version']}.json").resolve():
                raise SourceResolutionError('Dataset registration location differs from its identity')
            matches.append((resolved, provider))
    if len(matches) != 1:
        raise SourceResolutionError('Native series does not resolve uniquely to the exact configured dataset reference')
    return matches[0]


def load_source(root, request):
    """Return verified source records, canonical PIT rows and adapter mapping.

    Request fields consumed here are ``source`` and ``selection``. Source is a
    closed object containing profile, native_series_id and exact dataset,
    source_view and pit_snapshot references. Recipe/schedule configuration is
    owned by orchestration. A null evaluation policy does not make this source
    read fail; publication eligibility remains explicitly unestablished here.
    """
    try:
        return _load_source(Path(root).resolve(), request)
    except SourceResolutionError:
        raise
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise SourceResolutionError('Stored PIT source or its exact references failed verification') from error


def _load_source(root, request):
    if type(request) is not dict or 'source' not in request or 'selection' not in request:
        raise SourceResolutionError('A source request and one explicit selection are required')
    source = request['source']
    object_fields(source, {'profile', 'native_series_id', 'dataset', 'source_view', 'pit_snapshot'}, path='source')
    if source['profile'] != PROFILE:
        raise SourceResolutionError('Unsupported stored source adapter profile')
    native_id = token(source['native_series_id'], 'source.native_series_id')
    dataset_ref = normalize_reference(source['dataset'])
    view_ref = normalize_reference(source['source_view'])
    snapshot_ref = normalize_reference(source['pit_snapshot'])
    selection = normalize_selection(request['selection'])
    dataset, provider = _resolve_dataset(root, native_id, dataset_ref)
    if provider['body']['provider'] != 'FRED_ALFRED':
        raise SourceResolutionError('Provider contract is incompatible with this upstream adapter profile')
    view = definition(root, 'source_views', view_ref, 'source_view_definition')
    if view['body']['dataset'] != dataset_ref:
        raise SourceResolutionError('SourceView does not bind the selected dataset')
    if view['body']['entity_selection']['kind'] != 'fixed_entities' or selection['entity_id'] not in view['body']['entity_selection']['entity_ids']:
        raise SourceResolutionError('Selected entity is not certified by the SourceView')
    if selection['dimensions'] or view['body']['filters']:
        raise SourceResolutionError('This scalar stored profile has no dimensions or implemented filter reinterpretation')
    fields = {field['name']:field for field in dataset['body']['fields']}
    if selection['measure'] != 'value' or fields.get('value', {}).get('data_type') != 'decimal' or 'value' not in view['body']['fields']:
        raise SourceResolutionError('The requested measure is not the stored scalar numeric field')
    if dataset['body']['event_time_field'] != 'observation_date' or dataset['body']['availability_time_field'] != 'vintage_date':
        raise SourceResolutionError('Dataset temporal field semantics are incompatible with the stored profile')

    completion_path = inside(root, f"storage/catalog/pit_store/full_history/completions/{snapshot_ref['id']}.json")
    library_item = verified_item(root, completion_path)
    snapshot, rows, run = read_pit(root, snapshot_ref['id'])
    if ref(snapshot) != snapshot_ref or snapshot['definition'] != view_ref or run['dataset'] != dataset_ref or run['source_view'] != view_ref:
        raise SourceResolutionError('Requested source pins differ from the verified PIT package')
    if library_item['id'] != dataset['id'] or library_item['series_id'] != native_id or run['provider_contract'] != ref(provider):
        raise SourceResolutionError('Verified PIT metadata differs from the dataset registry relationship')
    store, second_run = load_package(root, snapshot_ref['id'])
    if second_run != run:
        raise SourceResolutionError('Source package changed while being resolved')
    raw_snapshots = [_record(store, binding) for binding in snapshot['upstream_snapshots']]
    if any(record['layer'] != 'raw' for record in raw_snapshots):
        raise SourceResolutionError('PIT source lacks its exact raw upstream snapshot')

    metadata_bindings = [run['ingestion_receipts'][name] for name in ('metadata_start', 'metadata_end')]
    metadata_records = [_record(store, binding) for binding in metadata_bindings]
    metadata = [strict_json(payload_record_bytes(root, record))['seriess'] for record in metadata_records]
    if any(len(items) != 1 or items[0]['id'] != native_id for items in metadata):
        raise SourceResolutionError('Stored official metadata has a different or ambiguous native series')
    first, last = metadata[0][0], metadata[1][0]
    for name in ('frequency', 'units', 'seasonal_adjustment'):
        if first[name] != last[name] or first[name] != provider['body'][name]:
            raise SourceResolutionError('Source semantics differ across pinned metadata and provider contract')
    if first['frequency'] != 'Monthly' or first['frequency_short'] != 'M':
        raise SourceResolutionError('This full-history source profile only certifies monthly reference cadence')
    if first['units'] != 'Dollars per Hour' or fields['value']['unit'] != 'USD_per_hour':
        raise SourceResolutionError('Native units lack a certified canonical unit mapping in this source profile')
    if any(row['entity_id'] != selection['entity_id'] or row['series_id'] != native_id or row['timing_precision'] != 'date' or not row['observation_date'].endswith('-01') for row in rows):
        raise SourceResolutionError('PIT rows conflict with the selected partition, cadence or timing precision')
    readiness = _record(store, run['historical_assessment'])
    if readiness['body']['decision'] != 'ready' or readiness['body']['capability'] != 'historical_replay' or readiness['body']['snapshot'] != snapshot_ref:
        raise SourceResolutionError('No pinned historical replay assessment certifies this PIT snapshot')

    policy_bindings = []
    for role, binding in [
        ('availability', dataset['body']['availability_policy']),
        ('revision', dataset['body']['revision_policy']),
        ('quality', dataset['body']['quality_policy']),
        ('selection', view['body']['selection_policy']),
        ('alignment', view['body']['alignment_policy']),
        ('readiness', readiness['body']['policy']),
    ]:
        policy = _record(store, binding)
        if policy['record_type'] != 'policy_definition' or policy['body']['approval_state'] != 'approved':
            raise SourceResolutionError('Source policy is not approved')
        policy_bindings.append({'role':role, 'artifact':binding})

    mapping = {
        'measure':selection['measure'], 'entity_id':selection['entity_id'],
        'dimension_fields':[], 'constant_fields':[{'field':'series_id', 'value':native_id}],
        'fields':{'reference_time':'observation_date', 'available_at':'vintage_date',
                  'value':'value', 'status':'status', 'entity_id':'entity_id',
                  'raw_snapshot':'raw_snapshot', 'source_view':'source_view',
                  'raw_blob_sha256':'source_raw_blob_sha256', 'raw_value_field':'source_field',
                  'temporal_precision':'timing_precision'},
        'pit_row_key_fields':['series_id','observation_date','vintage_date'],
        'raw_row_key_fields':[{'raw_field':'date','pit_field':'observation_date'}],
        'temporal_precision':'date', 'value_semantics':'numeric_level',
        'cadence':{'frequency':'monthly', 'ordering':'reference_time',
                   'gap_policy':'explicit_missing', 'calendar':'gregorian'},
    }
    source_metadata = {
        'dataset_title':dataset['display_name'], 'native_series_id':native_id,
        'provider':provider['body']['provider'], 'native_units':first['units'],
        'unit':fields['value']['unit'], 'frequency':first['frequency'],
        'seasonal_adjustment':first['seasonal_adjustment'],
        'reference_period_convention':'first_of_month_label',
        'selected_measure':selection['measure'], 'entity_id':selection['entity_id'], 'dimensions':[],
        'availability_precision':'date', 'reference_start':run['coverage']['observation_start'],
        'reference_end':run['coverage']['observation_end'],
        'archive_vintage_start':run['coverage']['vintage_start'],
        'archive_vintage_end':run['coverage']['vintage_end'],
        'archive_captured_at':run['capture_finished_at'],
        'historical_readiness':run['historical_assessment'],
        'metadata_evidence':metadata_bindings,
        'limitations':readiness['body']['limitations'],
    }
    completion = strict_json(stable_read(completion_path))
    return {
        'dataset':dataset, 'source_view':view, 'provider':provider,
        'pit_snapshot':snapshot, 'raw_snapshots':raw_snapshots, 'rows':rows,
        'mapping':mapping, 'source_policy_bindings':policy_bindings,
        'source_metadata':source_metadata, 'metadata_evidence_refs':metadata_bindings,
        'historical_assessment':readiness, 'source_record_paths':list(run['record_paths']),
        'source_payload_paths':list(run['payload_paths']),
        'source_package_path':completion['run_path'],
        'source_completion_path':str(completion_path.relative_to(root)),
        'publication_eligibility':'not_established',
    }
