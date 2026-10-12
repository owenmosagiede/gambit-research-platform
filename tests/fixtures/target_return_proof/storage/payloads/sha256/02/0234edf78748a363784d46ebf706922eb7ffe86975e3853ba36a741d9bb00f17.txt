"""Date-preserving Feature Store records, reusing existing identities and paths.

These structural and integrity validators do not approve a source, evaluation
schedule, scientific relationship, or production publication. Dependency closure
and exact source/recipe compatibility must be resolved by the store reader/writer.
"""
from copy import deepcopy
import re

from data.transformations import contracts as c
from data.transformations import identity as i

ContractError = c.ContractError
SCHEMA_VERSION = '0.3.0'
OBSERVATION_SCHEMA_VERSION = '0.3.0'
IDENTITY_PROFILE = c.EXECUTION_IDENTITY_PROFILE
_HASH = re.compile(r'[0-9a-f]{64}\Z', re.ASCII)
_OBSERVATION_FIELDS = {'materialization_id','entity_id','measure','dimensions','reference_time','available_at','evaluation_cutoff','vintage_id','value','status','reason_code','lineage'}
_METADATA_FIELDS = {'source_view','dataset','selection','unit','value_semantics','cadence','history_policy','source_policy_bindings','history_mode','temporal_precision','availability_semantics'}
_PARTITION_FIELDS = {'role','blob_sha256','format','byte_count','row_count','partition_key','entity_id','minimum_key','maximum_key'}
_FIELD_MAPPING_FIELDS = {'reference_time','available_at','value','status','entity_id','raw_snapshot','source_view','raw_blob_sha256','raw_value_field','temporal_precision'}


def _hash(value, path='hash'):
    if type(value) is not str or not _HASH.fullmatch(value):raise ContractError(path+': invalid SHA-256')
    return value


def _integer(value, minimum=0, path='count'):
    if type(value) is not int or value<minimum:raise ContractError(path+': invalid nonnegative integer')
    return value


def _identifier(value,prefix):
    if type(value) is not str or not re.fullmatch(prefix+r'[0-9a-f]{64}',value):raise ContractError('Invalid '+prefix+' identity')
    return value


def _envelope(record,kind,fields):
    c.object_fields(record,fields,path=kind)
    c.choice(record['schema_version'],{SCHEMA_VERSION},'schema_version')
    c.choice(record['record_type'],{kind},'record_type')
    c.choice(record['version'],{'1.0.0'},'version')


def _identified(record,prefix):
    expected=prefix+i.digest({k:v for k,v in record.items() if k!='id'})
    if record['id']!=expected:raise ContractError('Record ID differs from normalized canonical contents')
    return record


def normalize_execution_input_key(value):
    fields={'recipe','source_snapshots','input_series_sha256','temporal_precision','evaluation_cutoffs','implementation','policy_bindings'}
    c.object_fields(value,fields,{'output_index','output_projection'},'execution input key')
    precision=c.choice(value['temporal_precision'],{'date','utc_timestamp'},'temporal_precision')
    cutoffs=c.normalize_cutoffs(value['evaluation_cutoffs'],precision)
    snapshots=c.normalize_references(value['source_snapshots'])
    if not snapshots:raise ContractError('Input key requires pinned source snapshots')
    result={'recipe':c.normalize_reference(value['recipe']),'source_snapshots':snapshots,
            'input_series_sha256':_hash(value['input_series_sha256']),'temporal_precision':precision,
            'evaluation_cutoffs':cutoffs,'implementation':c.normalize_reference(value['implementation']),
            'policy_bindings':i.normalize_bindings(value['policy_bindings'])}
    if ('output_index' in value)==('output_projection' in value):raise ContractError('Declare exactly one output coverage projection')
    if 'output_projection' in value:
        result['output_projection']=c.choice(value['output_projection'],{'latest_per_cutoff'},'output_projection')
    else:
        if type(value['output_index']) is not list:raise ContractError('output_index must be a list')
        rows=[];seen=set()
        for row in value['output_index']:
            c.object_fields(row,{'reference_time','evaluation_cutoff'},path='output_index')
            cutoff=c.normalize_time(row['evaluation_cutoff'],precision)
            reference=row['reference_time']
            if reference is not None:c.normalize_time(reference,precision)
            if cutoff not in cutoffs or (reference is not None and reference>cutoff):raise ContractError('Output index exceeds its cutoff')
            key=(cutoff,reference)
            if key in seen:raise ContractError('Duplicate output index')
            seen.add(key);rows.append({'reference_time':reference,'evaluation_cutoff':cutoff})
        result['output_index']=sorted(rows,key=lambda row:(row['evaluation_cutoff'],row['reference_time'] or ''))
    return result


def make_materialization_id_from_key(input_key):
    return 'MATERIALIZATION_'+i.digest({'identity_profile':IDENTITY_PROFILE,'kind':'materialization','input_key':normalize_execution_input_key(input_key)})


def normalize_observation(value, temporal_precision):
    c.object_fields(value,_OBSERVATION_FIELDS,path='feature observation')
    result=deepcopy(value)
    _identifier(result['materialization_id'],'MATERIALIZATION_')
    selection=c.normalize_selection({key:result[key] for key in ('measure','entity_id','dimensions')})
    result.update(selection)
    c.choice(result['status'],{'valid','missing','invalid'},'status')
    c.token(result['vintage_id'])
    result['lineage']=c.normalize_reference(result['lineage'])
    cutoff=c.normalize_time(result['evaluation_cutoff'],temporal_precision)
    available=c.normalize_time(result['available_at'],temporal_precision)
    reference=result['reference_time']
    if reference is None:
        if result['status']!='invalid':raise ContractError('Only invalid derived observations may lack a reference time')
    else:c.normalize_time(reference,temporal_precision)
    if available!=cutoff or (reference is not None and reference>cutoff):raise ContractError('Feature observation violates derived-at-cutoff availability')
    if result['status']=='valid':
        c.canonical_decimal(result['value'])
        if result['reason_code'] is not None:raise ContractError('Valid feature observation cannot have a failure reason')
    else:
        if result['value'] is not None:raise ContractError('Failed feature observation must be null')
        c.choice(result['reason_code'],c.REASON_CODES,'reason_code')
    return result


def observation_key(row):
    return {'entity_id':row['entity_id'],'reference_time':row['reference_time'],'evaluation_cutoff':row['evaluation_cutoff']}


def _sort_key(row):
    return (row['entity_id'],row['evaluation_cutoff'],row['reference_time'] or '')


def normalize_observations(rows, temporal_precision):
    if type(rows) is not list:raise ContractError('Observations must be a list')
    result=[normalize_observation(row,temporal_precision) for row in rows]
    keys=[_sort_key(row) for row in result]
    if len(keys)!=len(set(keys)):raise ContractError('Duplicate entity/reference/evaluation observation key')
    return sorted(result,key=_sort_key)


def semantic_rows_digest(rows, temporal_precision=None):
    if temporal_precision is None:
        # Public callers should provide precision; the records are not converted.
        if not rows:raise ContractError('Explicit precision required for an empty row set')
        temporal_precision='utc_timestamp' if 'T' in rows[0]['evaluation_cutoff'] else 'date'
    normalized=normalize_observations(rows,temporal_precision)
    return i.digest([{k:v for k,v in row.items() if k!='materialization_id'} for row in normalized])


def normalize_metadata(value):
    c.object_fields(value,_METADATA_FIELDS,path='materialization metadata')
    precision=c.choice(value['temporal_precision'],{'date','utc_timestamp'},'temporal_precision')
    cadence=c.normalize_cadence(value['cadence'])
    history=c.choice(value['history_mode'],c.HISTORY_MODES,'history_mode')
    if cadence['ordering']!=('evaluation_cutoff' if history=='emitted_history' else 'reference_time') or (history=='emitted_history' and cadence['frequency']!='event'):
        raise ContractError('Materialization cadence differs from history mode')
    if cadence['frequency']=='intraday' and precision!='utc_timestamp':raise ContractError('Intraday data requires timestamp precision')
    policies=i.normalize_bindings(value['source_policy_bindings'])
    if not policies:raise ContractError('Source policy bindings are required')
    return {'source_view':c.normalize_reference(value['source_view']),'dataset':c.normalize_reference(value['dataset']),
            'selection':c.normalize_selection(value['selection']),'unit':c.token(value['unit']),
            'value_semantics':c.choice(value['value_semantics'],c.VALUE_SEMANTICS,'value_semantics'),
            'cadence':cadence,'history_policy':c.normalize_reference(value['history_policy']),
            'source_policy_bindings':policies,'history_mode':history,'temporal_precision':precision,
            'availability_semantics':c.choice(value['availability_semantics'],{'derived_at_cutoff'},'availability_semantics')}


def _normalize_key(value,precision):
    c.object_fields(value,{'entity_id','reference_time','evaluation_cutoff'},path='partition key')
    result={'entity_id':c.token(value['entity_id']),'reference_time':value['reference_time'],
            'evaluation_cutoff':c.normalize_time(value['evaluation_cutoff'],precision)}
    if result['reference_time'] is not None:c.normalize_time(result['reference_time'],precision)
    if result['reference_time'] is not None and result['reference_time']>result['evaluation_cutoff']:raise ContractError('Invalid partition time range')
    return result


def normalize_partition(value,precision):
    c.object_fields(value,_PARTITION_FIELDS,path='partition')
    result={'role':c.choice(value['role'],{'feature_observations'},'partition.role'),
            'blob_sha256':_hash(value['blob_sha256']),'format':c.choice(value['format'],{'jsonl'},'partition.format'),
            'byte_count':_integer(value['byte_count'],1),'row_count':_integer(value['row_count'],1),
            'partition_key':c.token(value['partition_key']),'entity_id':c.token(value['entity_id']),
            'minimum_key':_normalize_key(value['minimum_key'],precision),'maximum_key':_normalize_key(value['maximum_key'],precision)}
    if any(result[name]['entity_id']!=result['entity_id'] for name in ('minimum_key','maximum_key')) or _sort_key(result['minimum_key'])>_sort_key(result['maximum_key']):raise ContractError('Invalid partition entity or key bounds')
    return result


def normalize_materialization(value, rows=None):
    fields={'schema_version','record_type','id','version','dataset_role','definition','identity_profile','input_key',
            'observation_schema_version','metadata','partitions','row_count','status_counts','semantic_rows_sha256','lineage'}
    _envelope(value,'materialization_manifest',fields)
    result=deepcopy(value)
    c.choice(result['dataset_role'],{'feature'},'dataset_role')
    c.choice(result['identity_profile'],{IDENTITY_PROFILE},'identity_profile')
    c.choice(result['observation_schema_version'],{OBSERVATION_SCHEMA_VERSION},'observation_schema_version')
    result['definition']=c.normalize_reference(result['definition'])
    result['input_key']=normalize_execution_input_key(result['input_key'])
    if 'output_index' not in result['input_key']:raise ContractError('Stored materializations require an explicit output index')
    if result['id']!=make_materialization_id_from_key(result['input_key']):raise ContractError('Materialization ID differs from its input key')
    if result['input_key']['recipe']!=result['definition']:raise ContractError('Definition and input-key recipe differ')
    result['metadata']=normalize_metadata(result['metadata']);precision=result['metadata']['temporal_precision']
    if precision!=result['input_key']['temporal_precision']:raise ContractError('Metadata/input temporal precision differs')
    if any(binding not in result['input_key']['policy_bindings'] for binding in result['metadata']['source_policy_bindings']):raise ContractError('Source policy is not pinned in the materialization input key')
    if not any(binding['artifact']==result['metadata']['history_policy'] for binding in result['input_key']['policy_bindings']):raise ContractError('History policy is not pinned in the materialization input key')
    if type(result['partitions']) is not list or not result['partitions']:raise ContractError('Complete materialization requires installed observation partitions')
    result['partitions']=[normalize_partition(part,precision) for part in result['partitions']]
    if len({p['partition_key'] for p in result['partitions']})!=len(result['partitions']):raise ContractError('Duplicate partition key')
    result['partitions'].sort(key=lambda part:(_sort_key(part['minimum_key']),part['partition_key']))
    total=_integer(result['row_count'],1)
    c.object_fields(result['status_counts'],{'valid','missing','invalid'},path='status_counts')
    counts={key:_integer(value,1 if key=='valid' else 0) for key,value in result['status_counts'].items()}
    result['status_counts']=counts
    if sum(counts.values())!=total or sum(p['row_count'] for p in result['partitions'])!=total or len(result['input_key']['output_index'])!=total:raise ContractError('Materialization row counts disagree')
    _hash(result['semantic_rows_sha256'])
    result['lineage']=c.normalize_references(result['lineage'])
    if not result['lineage']:raise ContractError('Materialization lineage is required')
    if rows is not None:
        normalized=normalize_observations(rows,precision)
        if len(normalized)!=total or any(row['materialization_id']!=result['id'] for row in normalized):raise ContractError('Observation count/materialization identity differs')
        if any({key:row[key] for key in ('measure','entity_id','dimensions')}!=result['metadata']['selection'] for row in normalized):raise ContractError('Observation selection differs from metadata')
        if any(row['lineage'] not in result['lineage'] for row in normalized):raise ContractError('Observation lineage is not in manifest closure')
        if {key:sum(row['status']==key for row in normalized) for key in counts}!=counts:raise ContractError('Observed validity counts disagree')
        if semantic_rows_digest(normalized,precision)!=result['semantic_rows_sha256']:raise ContractError('Semantic observation digest mismatch')
        index=[{'reference_time':row['reference_time'],'evaluation_cutoff':row['evaluation_cutoff']} for row in normalized]
        if index!=result['input_key']['output_index']:raise ContractError('Observation index differs from declared output coverage')
        offset=0
        for partition in result['partitions']:
            subset=normalized[offset:offset+partition['row_count']];offset+=partition['row_count']
            if not subset or observation_key(subset[0])!=partition['minimum_key'] or observation_key(subset[-1])!=partition['maximum_key'] or any(row['entity_id']!=partition['entity_id'] for row in subset):raise ContractError('Partition logical key bounds differ from observations')
    return result


def _field_values(values):
    if type(values) is not list or not values:raise ContractError('Native row selectors must be nonempty field/value lists')
    result=[]
    for item in values:
        c.object_fields(item,{'field','value'},path='native row selector')
        result.append({'field':c.token(item['field']),'value':c.text(item['value'])})
    if len({item['field'] for item in result})!=len(result):raise ContractError('Duplicate native row selector field')
    return sorted(result,key=lambda item:item['field'])


def _normalize_operand_body(value):
    fields={'dataset','source_view','pit_snapshot','raw_snapshot','source_policy_bindings','key','pit_row_key','pit_row_sha256',
            'pit_row_digest_profile','field_mapping','raw_cell','raw_row_mapping','temporal_precision'}
    c.object_fields(value,fields,path='PIT operand body')
    result={name:c.normalize_reference(value[name]) for name in ('dataset','source_view','pit_snapshot','raw_snapshot')}
    result['source_policy_bindings']=i.normalize_bindings(value['source_policy_bindings'])
    if not result['source_policy_bindings']:raise ContractError('Operand source policy bindings are required')
    precision=c.choice(value['temporal_precision'],{'date','utc_timestamp'},'temporal_precision')
    result['temporal_precision']=precision
    c.object_fields(value['key'],{'entity_id','measure','dimensions','reference_time','available_at'},path='PIT operand key')
    result['key']=c.normalize_selection({key:value['key'][key] for key in ('entity_id','measure','dimensions')})
    result['key'].update(reference_time=c.normalize_time(value['key']['reference_time'],precision),available_at=c.normalize_time(value['key']['available_at'],precision))
    result['pit_row_key']=_field_values(value['pit_row_key'])
    result['pit_row_sha256']=_hash(value['pit_row_sha256'])
    result['pit_row_digest_profile']=c.choice(value['pit_row_digest_profile'],{'canonical_stored_row_v1'},'pit_row_digest_profile')
    c.object_fields(value['field_mapping'],_FIELD_MAPPING_FIELDS,path='field mapping')
    result['field_mapping']={key:c.token(value['field_mapping'][key]) for key in sorted(_FIELD_MAPPING_FIELDS)}
    selectors={x['field']:x['value'] for x in result['pit_row_key']}
    for field in ('reference_time','available_at'):
        if selectors.get(result['field_mapping'][field])!=result['key'][field]:raise ContractError('Native selector differs from canonical operand time')
    c.object_fields(value['raw_cell'],{'blob_sha256','row_key','field'},path='raw cell')
    result['raw_cell']={'blob_sha256':_hash(value['raw_cell']['blob_sha256']),'row_key':_field_values(value['raw_cell']['row_key']),'field':c.token(value['raw_cell']['field'])}
    if type(value['raw_row_mapping']) is not list or not value['raw_row_mapping']:
        raise ContractError('Raw row mapping must be an explicit nonempty list')
    mapping=[]
    for item in value['raw_row_mapping']:
        c.object_fields(item,{'raw_field','pit_field'},path='raw row mapping')
        mapping.append({'raw_field':c.token(item['raw_field']),'pit_field':c.token(item['pit_field'])})
    if len({item['raw_field'] for item in mapping})!=len(mapping):raise ContractError('Duplicate raw row mapping field')
    raw_selectors={item['field']:item['value'] for item in result['raw_cell']['row_key']}
    if {item['raw_field'] for item in mapping}!=set(raw_selectors):raise ContractError('Raw row mapping does not cover exactly the raw cell selector')
    for item in mapping:
        if item['pit_field'] not in selectors or selectors[item['pit_field']]!=raw_selectors[item['raw_field']]:
            raise ContractError('Raw row selector differs from its explicitly mapped PIT selector')
    result['raw_row_mapping']=sorted(mapping,key=lambda item:item['raw_field'])
    return result


def make_pit_operand(body):
    result={'schema_version':SCHEMA_VERSION,'record_type':'pit_operand_record','version':'1.0.0','body':_normalize_operand_body(body)}
    result['id']='PIT_OPERAND_'+i.digest(result)
    return result


def normalize_pit_operand(value):
    _envelope(value,'pit_operand_record',{'schema_version','record_type','id','version','body'})
    result=deepcopy(value);result['body']=_normalize_operand_body(value['body'])
    return _identified(result,'PIT_OPERAND_')


def _relationships(values):
    if type(values) is not list:raise ContractError('relationship_results must be a list')
    result=[]
    for row in values:
        c.object_fields(row,{'relationship','trial_results','admission_results','validation_results','attempt_ids'},path='relationship results')
        item={'relationship':c.normalize_reference(row['relationship'])}
        for key in ('trial_results','admission_results','validation_results'):item[key]=c.normalize_references(row[key])
        if type(row['attempt_ids']) is not list or any(type(v) is not str or re.fullmatch(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',v) is None for v in row['attempt_ids']):raise ContractError('Invalid attempt UUID')
        if len(row['attempt_ids'])!=len(set(row['attempt_ids'])):raise ContractError('Duplicate attempt UUID')
        item['attempt_ids']=sorted(row['attempt_ids']);result.append(item)
    if len({row['relationship']['id'] for row in result})!=len(result):raise ContractError('Duplicate relationship result group')
    return sorted(result,key=lambda row:row['relationship']['id'])


def make_library_entry(feature, feature_materializations, *, relationship_results=(), supersedes=None):
    feature=c.normalize_reference(feature);_identifier(feature['id'],'FEATURE_')
    result={'schema_version':SCHEMA_VERSION,'record_type':'signal_library_entry','version':'1.0.0',
            'signal_id':'SIGNAL_'+feature['id'][len('FEATURE_'):],'feature':feature,
            'feature_materializations':c.normalize_references(list(feature_materializations)),
            'relationship_results':_relationships(list(relationship_results)),
            'supersedes':None if supersedes is None else c.normalize_reference(supersedes)}
    if not result['feature_materializations']:raise ContractError('Materialized Signal entry requires a materialization')
    result['id']='LIBRARYENTRY_'+i.digest(result)
    return result


def normalize_library_entry(value):
    _envelope(value,'signal_library_entry',{'schema_version','record_type','id','version','signal_id','feature','feature_materializations','relationship_results','supersedes'})
    if type(value['feature_materializations']) is not list or type(value['relationship_results']) is not list:raise ContractError('Library links must be JSON arrays')
    expected=make_library_entry(value['feature'],value['feature_materializations'],relationship_results=value['relationship_results'],supersedes=value['supersedes'])
    if expected['signal_id']!=value['signal_id'] or expected['id']!=value['id']:raise ContractError('Signal entry ID or Feature/Signal relationship mismatch')
    return expected


def normalize_execution_audit(value):
    """Validate an operational success event; never a scientific reference.

    Caller-supplied execution/completion clocks must be actual wall-clock readings.
    Historical source dates are not audit timestamps and are not compared here.
    """
    fields={'schema_version','record_type','attempt_id','state','executed_at','completed_at',
            'signal_id','feature','materialization','reused','row_count'}
    c.object_fields(value,fields,path='feature execution audit')
    c.choice(value['schema_version'],{SCHEMA_VERSION},'schema_version')
    c.choice(value['record_type'],{'feature_execution_audit'},'record_type')
    attempt=value['attempt_id']
    if type(attempt) is not str or re.fullmatch(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',attempt) is None:
        raise ContractError('Execution audit attempt_id must be a canonical UUID')
    feature=c.normalize_reference(value['feature']);_identifier(feature['id'],'FEATURE_')
    materialization=c.normalize_reference(value['materialization']);_identifier(materialization['id'],'MATERIALIZATION_')
    signal=_identifier(value['signal_id'],'SIGNAL_')
    if signal!='SIGNAL_'+feature['id'][len('FEATURE_'):]:raise ContractError('Execution audit Signal/Feature mismatch')
    if type(value['reused']) is not bool:raise ContractError('Execution audit reused must be boolean')
    executed=c.normalize_time(value['executed_at'],'utc_timestamp','audit.executed_at')
    completed=c.normalize_time(value['completed_at'],'utc_timestamp','audit.completed_at')
    if completed<executed:raise ContractError('Execution audit completion precedes execution')
    return {'schema_version':SCHEMA_VERSION,'record_type':'feature_execution_audit','attempt_id':attempt,
            'state':c.choice(value['state'],{'succeeded'},'state'),'executed_at':executed,'completed_at':completed,
            'signal_id':signal,'feature':feature,'materialization':materialization,
            'reused':value['reused'],'row_count':_integer(value['row_count'],1)}


def validate_record(record):
    if type(record) is not dict:raise ContractError('Record must be an object')
    dispatch={'materialization_manifest':normalize_materialization,'signal_library_entry':normalize_library_entry,'pit_operand_record':normalize_pit_operand,'feature_execution_audit':normalize_execution_audit}
    normalizer=dispatch.get(record.get('record_type'))
    if normalizer is None:raise ContractError('Unsupported feature-store record type')
    return normalizer(record)
