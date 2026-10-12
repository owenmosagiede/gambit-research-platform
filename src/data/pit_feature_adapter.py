"""Map verified native PIT history into the existing transformation envelope.

This adapter never opens provider payloads or selects a provider-specific formula.
The upstream source resolver must verify stored PIT and raw snapshots, definitions,
policies and native semantics before supplying them. Explicit mapping metadata owns
field interpretation. This conversion does not approve an evaluation schedule.

Operand records are compact locators, not copied observations. Their digest covers
an entire canonical stored PIT row, including any retrospective successor metadata,
solely for integrity verification. Successor dates never enter canonical inputs or
supply historical availability; only each row's own native availability is used.
"""
from copy import deepcopy
from functools import lru_cache
import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from .transformations.contracts import (ContractError, INTEGER, canonical_decimal, normalize_cadence,
    normalize_dimensions, normalize_input, normalize_reference, normalize_selection,
    normalize_time, object_fields, token, text)
from .transformations.identity import digest, reference


class AdapterError(ContractError):
    """Native history or its explicit mapping violates the canonical contract."""


FIELD_NAMES = {'reference_time','available_at','value','status','entity_id','raw_snapshot',
               'source_view','raw_blob_sha256','raw_value_field','temporal_precision'}
MAPPING_FIELDS = {'measure','entity_id','dimension_fields','constant_fields','fields',
                  'pit_row_key_fields','raw_row_key_fields','temporal_precision',
                  'value_semantics','cadence'}


@lru_cache(maxsize=1)
def _record_validator():
    schema_path = Path(__file__).resolve().parents[2]/'specs/schemas/platform.schema.json'
    schema = json.loads(schema_path.read_text())
    return Draft202012Validator(schema,format_checker=FormatChecker())


def _record(value, kind):
    if type(value) is not dict or value.get('record_type') != kind:
        raise AdapterError('Expected a resolved '+kind)
    _record_validator().validate(value)
    return reference(value)


def normalize_mapping(mapping):
    """Validate plain field bindings; no executable mapping expressions are allowed."""
    object_fields(mapping,MAPPING_FIELDS,path='PIT mapping')
    object_fields(mapping['fields'],FIELD_NAMES,path='PIT field mapping')
    fields = {name:token(value,'mapped field') for name,value in mapping['fields'].items()}
    if len(set(fields.values())) != len(fields):
        raise AdapterError('Distinct canonical fields require distinct native field bindings')
    if mapping['temporal_precision'] not in ('date','utc_timestamp'):
        raise AdapterError('PIT mapping requires explicit native temporal precision')
    dimensions = []
    if type(mapping['dimension_fields']) is not list:
        raise AdapterError('dimension_fields must be a list')
    for item in mapping['dimension_fields']:
        object_fields(item,{'name','field','value'},path='dimension mapping')
        dimensions.append({'name':token(item['name']),'field':token(item['field']),
                           'value':text(item['value'])})
    normalize_dimensions([{'name':d['name'],'value':d['value']} for d in dimensions])
    constants = []
    if type(mapping['constant_fields']) is not list:
        raise AdapterError('constant_fields must be a list')
    for item in mapping['constant_fields']:
        object_fields(item,{'field','value'},path='constant mapping')
        constants.append({'field':token(item['field']),'value':text(item['value'])})
    if len({v['field'] for v in constants}) != len(constants):
        raise AdapterError('Duplicate constant field binding')
    keys = mapping['pit_row_key_fields']
    if type(keys) is not list or not keys or len(set(keys)) != len(keys):
        raise AdapterError('PIT row key fields must be nonempty and unique')
    keys = sorted(token(key,'PIT row key field') for key in keys)
    if not {fields['reference_time'],fields['available_at']} <= set(keys):
        raise AdapterError('PIT row key must include reference and availability fields')
    raw_keys = []
    if type(mapping['raw_row_key_fields']) is not list or not mapping['raw_row_key_fields']:
        raise AdapterError('Raw cell requires an explicit native row selector')
    for item in mapping['raw_row_key_fields']:
        object_fields(item,{'raw_field','pit_field'},path='raw row key mapping')
        raw_keys.append({'raw_field':token(item['raw_field']),'pit_field':token(item['pit_field'])})
    if len({v['raw_field'] for v in raw_keys}) != len(raw_keys):
        raise AdapterError('Duplicate raw row selector field')
    if any(item['pit_field'] not in keys for item in raw_keys):
        raise AdapterError('Every raw row selector requires an explicit PIT row key binding')
    return {'measure':token(mapping['measure']),'entity_id':token(mapping['entity_id']),
            'dimension_fields':sorted(dimensions,key=lambda d:d['name']),
            'constant_fields':sorted(constants,key=lambda d:d['field']),'fields':dict(sorted(fields.items())),
            'pit_row_key_fields':keys,'raw_row_key_fields':sorted(raw_keys,key=lambda d:d['raw_field']),
            'temporal_precision':mapping['temporal_precision'],
            'value_semantics':token(mapping['value_semantics']),
            'cadence':normalize_cadence(mapping['cadence'])}


def _native(row, name):
    if name not in row:
        raise AdapterError('Mapped native field is missing: '+name)
    return row[name]


def _key_value(row,name):
    value = _native(row,name)
    return text(value,'native row key')


def adapt_pit_history(*, dataset, source_view, pit_snapshot, raw_snapshots, rows,
                      mapping, history_policy, provenance=None):
    """Return a canonical input and exact operand locators, without authorizing use.

    `rows` must be the verified selected native PIT partition, not provider payloads.
    `available_vintages` reports observed labels only: it is deliberately not an
    approved evaluation schedule, release-event list, or a latest-reference rule.
    No file writes or provider requests occur here.
    """
    from .feature_store_contracts import make_pit_operand

    mapping = normalize_mapping(mapping)
    dataset_ref = _record(dataset,'dataset_definition')
    view_ref = _record(source_view,'source_view_definition')
    pit_ref = _record(pit_snapshot,'snapshot_manifest')
    if source_view['body']['dataset'] != dataset_ref:
        raise AdapterError('SourceView is not pinned to this dataset')
    if pit_snapshot['layer'] != 'pit' or pit_snapshot['definition'] != view_ref:
        raise AdapterError('PIT snapshot is not pinned to this SourceView')
    if type(raw_snapshots) is not list or not raw_snapshots:
        raise AdapterError('Resolved upstream raw snapshots are required')
    raw_by_id = {}
    for raw in raw_snapshots:
        binding = _record(raw,'snapshot_manifest')
        if raw['layer'] != 'raw' or raw['definition'] != dataset_ref:
            raise AdapterError('Raw snapshot does not belong to this dataset')
        if binding['id'] in raw_by_id:
            raise AdapterError('Duplicate upstream raw snapshot identity')
        raw_by_id[binding['id']] = (binding,raw)
    if sorted(pit_snapshot['upstream_snapshots'],key=lambda r:r['id']) != sorted(
            [r for r,_ in raw_by_id.values()],key=lambda r:r['id']):
        raise AdapterError('PIT upstream references differ from supplied raw snapshots')
    history_policy = normalize_reference(history_policy)
    selection = normalize_selection({'measure':mapping['measure'],'entity_id':mapping['entity_id'],
        'dimensions':[{'name':d['name'],'value':d['value']} for d in mapping['dimension_fields']]})
    fields = {field['name']:field for field in dataset['body']['fields']}
    field = fields.get(selection['measure'])
    if field is None or field['data_type'] not in ('decimal','integer'):
        raise AdapterError('Selected dataset measure is not explicitly numeric')
    if selection['measure'] not in source_view['body']['fields']:
        raise AdapterError('Selected measure is absent from the SourceView')
    if selection['entity_id'] not in dataset['body']['economic_entity_ids']:
        raise AdapterError('Selected entity is absent from dataset metadata')
    entity_selection = source_view['body']['entity_selection']
    if entity_selection['kind'] != 'fixed_entities' or selection['entity_id'] not in entity_selection['entity_ids']:
        raise AdapterError('Adapter requires an explicitly selected fixed SourceView entity')
    if source_view['body']['filters']:
        raise AdapterError('Filtered SourceViews require an explicit verified upstream filter adapter')
    if mapping['cadence']['ordering'] != 'reference_time':
        raise AdapterError('Native PIT input must retain reference-history ordering')
    # Original source policies remain pinned in each operand locator. The generic
    # transformation history policy is a separate mathematical execution contract.
    policy_bindings = [{'role':name,'artifact':normalize_reference(dataset['body'][name+'_policy'])}
                       for name in ['availability','revision','quality']]
    policy_bindings += [{'role':name,'artifact':normalize_reference(source_view['body'][name+'_policy'])}
                        for name in ['alignment','selection']]
    if type(rows) is not list or not rows:
        raise AdapterError('Verified native PIT history must be a nonempty list')
    observations,operands,keys = [],[],set()
    fm = mapping['fields']
    for row in rows:
        if type(row) is not dict:
            raise AdapterError('Native PIT row must be an object')
        if _native(row,fm['entity_id']) != selection['entity_id']:
            raise AdapterError('Mixed entity partition in selected PIT history')
        for item in mapping['dimension_fields']+mapping['constant_fields']:
            if _native(row,item['field']) != item['value']:
                raise AdapterError('Native row differs from selected dimension or constant binding')
        if _native(row,fm['temporal_precision']) != mapping['temporal_precision']:
            raise AdapterError('Native PIT precision differs from declared mapping')
        reference_time = normalize_time(_native(row,fm['reference_time']),mapping['temporal_precision'])
        available_at = normalize_time(_native(row,fm['available_at']),mapping['temporal_precision'])
        if _native(row,fm['source_view']) != view_ref:
            raise AdapterError('Native row SourceView binding mismatch')
        raw_ref = normalize_reference(_native(row,fm['raw_snapshot']))
        raw_info = raw_by_id.get(raw_ref['id'])
        if raw_info is None or raw_info[0] != raw_ref:
            raise AdapterError('Native row raw snapshot binding mismatch')
        raw_blob = _native(row,fm['raw_blob_sha256'])
        if raw_blob not in {member['blob_sha256'] for member in raw_info[1]['members']}:
            raise AdapterError('Raw cell blob is not a member of the pinned raw snapshot')
        source_field = token(_native(row,fm['raw_value_field']),'native raw value field')
        status = _native(row,fm['status']);value = _native(row,fm['value'])
        if status == 'valid':
            canonical_decimal(value);reason = None
            if field['data_type']=='integer' and not INTEGER.fullmatch(value):
                raise AdapterError('Native value contradicts integer dataset measure')
        elif status in ('missing','invalid'):
            if value is not None:
                raise AdapterError('Native failed row must contain null value')
            if status=='missing' and not field['nullable']:
                raise AdapterError('Missing native value contradicts nonnullable dataset measure')
            reason = 'SOURCE_MISSING' if status=='missing' else 'SOURCE_INVALID'
        else:
            raise AdapterError('Unsupported native validity status')
        pit_key = [{'field':name,'value':_key_value(row,name)} for name in mapping['pit_row_key_fields']]
        key_identity = digest(pit_key)
        if key_identity in keys:
            raise AdapterError('Duplicate or ambiguous native PIT row key')
        keys.add(key_identity)
        key = {**deepcopy(selection),'reference_time':reference_time,'available_at':available_at}
        body = {'dataset':dataset_ref,'source_view':view_ref,'pit_snapshot':pit_ref,'raw_snapshot':raw_ref,
                'source_policy_bindings':policy_bindings,'key':key,'temporal_precision':mapping['temporal_precision'],
                'pit_row_key':pit_key,'pit_row_sha256':digest(row),
                'pit_row_digest_profile':'canonical_stored_row_v1','field_mapping':fm,
                'raw_row_mapping':mapping['raw_row_key_fields'],
                'raw_cell':{'blob_sha256':raw_blob,'field':source_field,
                    'row_key':[{'field':v['raw_field'],'value':_key_value(row,v['pit_field'])} for v in mapping['raw_row_key_fields']]}}
        operand = make_pit_operand(body)
        operands.append(operand)
        observations.append({**deepcopy(selection),'reference_time':reference_time,'available_at':available_at,
            'vintage_id':'VINTAGE_'+digest({'source_view':view_ref,'key':key}),'value':value,'status':status,
            'reason_code':reason,'lineage':reference(operand)})
    series = normalize_input({'contract_version':'1.0.0','source_view':view_ref,'source_snapshots':[pit_ref],
        'selection':selection,'unit':field['unit'],'value_semantics':mapping['value_semantics'],
        'cadence':mapping['cadence'],'history_policy':history_policy,'capabilities':['revision_history'],
        'temporal_precision':mapping['temporal_precision'],'provenance':deepcopy(provenance or {}),
        'observations':observations})
    periods = sorted({r['reference_time'] for r in observations})
    vintages = sorted({r['available_at'] for r in observations})
    operands.sort(key=lambda r:r['id'])
    return {'series':series,'operand_records':operands,'available_vintages':vintages,
            'facts':{'reference_start':periods[0],'reference_end':periods[-1],
                     'reference_count':len(periods),'vintage_start':vintages[0],'vintage_end':vintages[-1],
                     'vintage_count':len(vintages),'native_row_count':len(rows),
                     'valid_row_count':sum(r['status']=='valid' for r in observations),
                     'missing_row_count':sum(r['status']=='missing' for r in observations),
                     'invalid_row_count':sum(r['status']=='invalid' for r in observations),
                     'temporal_precision':mapping['temporal_precision']},
            'publication_eligibility':'not_established'}
