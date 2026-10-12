"""Strict records for retrospective FX Feature preparation; never historical PIT.

This profile keeps source availability unknown and does not weaken the original
0.3 stored Feature contract. Identity binds a pinned captured price state, a
knowledge cutoff, an explicit output interval and all implementation policies.
"""
from collections import Counter
from copy import deepcopy
from datetime import date
from data.transformations.contracts import (ContractError, object_fields,
    normalize_reference, normalize_time, canonical_decimal, normalize_selection)
from data.transformations.identity import digest

VERSION = '0.6.0'
PROFILE = 'fx_retrospective_feature.1.0.0'


def materialization_id(key):
    return 'MATERIALIZATION_' + digest({'identity_profile': PROFILE, 'input_key': key})


def lineage_record(kind, body):
    record = {'schema_version': VERSION, 'record_type': kind, 'version': '1.0.0', 'body': body}
    record['id'] = 'LINEAGE_' + digest(record)
    validate_record(record)
    return record


def _date(value):
    return normalize_time(value, 'date')


def _count(value):
    if type(value) is not int or value < 0:
        raise ContractError('Invalid FX Feature count')


def validate_observation(row):
    object_fields(row, {'materialization_id', 'entity_id', 'measure', 'dimensions',
        'reference_time', 'available_at', 'evaluation_cutoff', 'vintage_id', 'value',
        'status', 'reason_code', 'lineage', 'historical_eligibility_certified'}, path='FX Feature observation')
    normalize_selection({key:row[key] for key in ('entity_id','measure','dimensions')})
    _date(row['reference_time']); _date(row['evaluation_cutoff']); normalize_reference(row['lineage'])
    if row['reference_time'] > row['evaluation_cutoff'] or row['available_at'] is not None or row['historical_eligibility_certified'] is not False:
        raise ContractError('Retrospective Feature cannot assert historical availability')
    if row['status'] == 'valid':
        canonical_decimal(row['value'])
        if row['reason_code'] is not None: raise ContractError('Valid Feature has a failure reason')
    else:
        from data.transformations.numeric import FAILURE_CODES
        if row['status'] not in ('missing','invalid') or row['value'] is not None or row['reason_code'] not in FAILURE_CODES:
            raise ContractError('Invalid Feature null status')
    return row


def validate_record(record):
    if record.get('schema_version') != VERSION or record.get('version') != '1.0.0':
        raise ContractError('Unsupported FX Feature profile')
    kind = record.get('record_type')
    if kind in ('fx_feature_input_record','fx_feature_lineage_record'):
        object_fields(record, {'schema_version','record_type','id','version','body'}, path=kind)
        if record['id'] != 'LINEAGE_' + digest({k:v for k,v in record.items() if k != 'id'}):
            raise ContractError('FX Feature lineage identity mismatch')
        body = record['body']
        if kind == 'fx_feature_input_record':
            object_fields(body, {'profile','price_snapshot','knowledge_cutoff','schedule_start','schedule_end',
                'calendar_id','calendar_version','scheduled_inputs','source_rows_sha256'}, path=kind)
            normalize_reference(body['price_snapshot']); _date(body['knowledge_cutoff'])
            _date(body['schedule_start']); _date(body['schedule_end'])
            if body['calendar_id'] != 'RESEARCH_WEEKDAYS' or body['calendar_version'] != '1.0.0':
                raise ContractError('Unapproved Feature calendar')
            if type(body['scheduled_inputs']) is not list: raise ContractError('Scheduled input list required')
            dates = []
            for row in body['scheduled_inputs']:
                object_fields(row, {'reference_time','price_row_id','price_row_sha256'}, path='scheduled input')
                dates.append(_date(row['reference_time']))
                if (row['price_row_id'] is None) != (row['price_row_sha256'] is None):
                    raise ContractError('Incomplete source row locator')
            if dates != sorted(set(dates)): raise ContractError('Duplicate or unordered scheduled input')
        else:
            object_fields(body, {'profile','scheduled_input','prefix_count','reference_time','evaluation_cutoff',
                'operation','implementation','policy_bindings','dependency_semantics'}, path=kind)
            for field in ('scheduled_input','operation','implementation'): normalize_reference(body[field])
            _count(body['prefix_count']); _date(body['reference_time']); _date(body['evaluation_cutoff'])
            if body['dependency_semantics'] != 'causal_prefix_audit_superset':
                raise ContractError('Unsupported dependency semantics')
        if body['profile'] != PROFILE: raise ContractError('Wrong lineage profile')
        return record
    if kind != 'materialization_manifest': raise ContractError('Unsupported FX Feature record type')
    object_fields(record, {'schema_version','record_type','id','version','identity_profile','dataset_role','definition',
        'input_key','metadata','scheduled_input','lineage','partitions','row_count','status_counts','reason_counts',
        'semantic_content_sha256','readiness_capabilities'}, path='FX Feature manifest')
    if record['identity_profile'] != PROFILE or record['dataset_role'] != 'feature':
        raise ContractError('Wrong materialization profile')
    key=record['input_key']
    object_fields(key, {'definition','source_snapshots','implementation','policy_bindings','batch_policy',
        'knowledge_cutoff','period','scheduled_input'}, path='FX Feature input key')
    for field in ('definition','implementation','scheduled_input'): normalize_reference(key[field])
    if len(key['source_snapshots']) != 1: raise ContractError('Exactly one constructed FX snapshot required')
    normalize_reference(key['source_snapshots'][0]); _date(key['knowledge_cutoff'])
    object_fields(key['period'], {'start_inclusive','end_inclusive'}, path='output period')
    start,end=key['period']['start_inclusive'],key['period']['end_inclusive']
    _date(start); _date(end)
    if start > end or end > key['knowledge_cutoff']: raise ContractError('Output interval exceeds knowledge cutoff')
    if (date.fromisoformat(end)-date.fromisoformat(start)).days >= 366:
        raise ContractError('The verification profile permits at most 366 calendar days per materialization')
    if record['id'] != materialization_id(key) or record['definition'] != key['definition'] or record['scheduled_input'] != key['scheduled_input']:
        raise ContractError('FX Feature materialization identity mismatch')
    meta=record['metadata']
    object_fields(meta, {'source_view','dataset','selection','unit','value_semantics','cadence','history_policy',
        'source_policy_bindings','history_mode','temporal_precision','availability_semantics'}, path='FX Feature metadata')
    for field in ('source_view','dataset','history_policy'): normalize_reference(meta[field])
    normalize_selection(meta['selection'])
    if meta['temporal_precision'] != 'date' or meta['availability_semantics'] != 'unknown_historical_availability' or meta['history_mode'] != 'resolved_state':
        raise ContractError('Invalid retrospective Feature timing claim')
    expected={'frequency':'daily','ordering':'reference_time','gap_policy':'explicit_missing',
              'calendar':'RESEARCH_WEEKDAYS','calendar_version':'1.0.0'}
    if meta['cadence'] != expected: raise ContractError('Feature must retain the approved weekday schedule')
    _count(record['row_count'])
    if not record['row_count'] or set(record['status_counts']) != {'valid','missing','invalid'}:
        raise ContractError('Feature requires a nonempty complete status summary')
    for value in record['status_counts'].values(): _count(value)
    if sum(record['status_counts'].values()) != record['row_count'] or not record['status_counts']['valid']:
        raise ContractError('Only Features with valid observations can be published')
    from data.fx_records import validate_member
    for member in record['partitions']:
        validate_member(member)
        if member['format'] != 'jsonl' or member['role'] != 'fx_feature_observations':
            raise ContractError('Unexpected Feature observation payload')
    if sum(member['row_count'] for member in record['partitions']) != record['row_count']:
        raise ContractError('Feature partition counts differ')
    for ref in record['lineage']: normalize_reference(ref)
    expected_readiness={'retrospective_research': {'decision':'ready','policy':key['batch_policy']['retrospective_policy']},
        'historical_replay': {'decision':'blocked','reason':'Historical source availability and complete vintages are unknown.'},
        'live_use': {'decision':'unresolved','reason':'Valuation clock, price basis and live eligibility remain unverified.'}}
    if record['readiness_capabilities'] != expected_readiness: raise ContractError('Unsupported Feature readiness claim')
    return record


def validate_materialization(record, rows):
    validate_record(record)
    for row in rows:
        validate_observation(row)
        if row['materialization_id'] != record['id'] or row['evaluation_cutoff'] != record['input_key']['knowledge_cutoff']:
            raise ContractError('Feature row belongs to another materialization')
    dates=[row['reference_time'] for row in rows]
    if dates != sorted(set(dates)): raise ContractError('Duplicate or unordered Feature observations')
    counts={status:sum(row['status']==status for row in rows) for status in ('valid','missing','invalid')}
    if len(rows) != record['row_count'] or counts != record['status_counts'] or dict(Counter(row['reason_code'] for row in rows if row['reason_code'])) != record['reason_counts'] or digest(rows) != record['semantic_content_sha256']:
        raise ContractError('Feature payload integrity mismatch')
    return deepcopy(record)
