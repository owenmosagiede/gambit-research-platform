"""Synthetic acceptance for additive date-preserving storage contracts."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import unittest

from jsonschema import Draft202012Validator,FormatChecker
from data import feature_store_contracts as f
from data.transformations import contracts as c,identity as i
from test_transformation_contracts import series_fixture,recipe_fixture,result_fixture,ref

ROOT=Path(__file__).resolve().parents[1]


def operand_fixture():
    source=series_fixture()
    return f.make_pit_operand({'dataset':ref('DS_FIXTURE'),'source_view':source['source_view'],'pit_snapshot':source['source_snapshots'][0],
        'raw_snapshot':ref('RAW_FIXTURE'),'source_policy_bindings':[{'role':'availability','artifact':ref('SOURCE_POLICY')}],
        'key':dict(source['selection'],reference_time='2000-01-01',available_at='2000-02-01'),
        'temporal_precision':'date','pit_row_digest_profile':'canonical_stored_row_v1','pit_row_sha256':'a'*64,
        'pit_row_key':[{'field':'observation_date','value':'2000-01-01'},{'field':'vintage_date','value':'2000-02-01'}],
        'field_mapping':{'reference_time':'observation_date','available_at':'vintage_date','value':'value','status':'status','entity_id':'entity_id',
          'raw_snapshot':'raw_snapshot','source_view':'source_view','raw_blob_sha256':'source_raw_blob_sha256','raw_value_field':'source_field','temporal_precision':'timing_precision'},
        'raw_row_mapping':[{'raw_field':'date','pit_field':'observation_date'}],
        'raw_cell':{'blob_sha256':'b'*64,'row_key':[{'field':'date','value':'2000-01-01'}],'field':'SERIES_20000201'}})


def materialization_fixture():
    source=series_fixture();recipe=recipe_fixture();feature=i.make_feature_definition(recipe);feature_ref=i.reference(feature)
    implementation=ref('FIXTURE_IMPLEMENTATION')
    bindings=[{'role':'source_availability','artifact':ref('SOURCE_POLICY')},{'role':'history','artifact':source['history_policy']}]
    index=[{'reference_time':'2000-01-01','evaluation_cutoff':'2000-03-01'}]
    key=i.execution_materialization_key(feature_ref,source,['2000-03-01'],implementation,bindings,output_index=index)
    identifier=f.make_materialization_id_from_key(key)
    row=dict(result_fixture()['observations'][0],materialization_id=identifier)
    rows=[row]
    payload=b''.join(i.canonical_bytes(r)+b'\n' for r in rows)
    partition={'role':'feature_observations','blob_sha256':hashlib.sha256(payload).hexdigest(),'format':'jsonl','byte_count':len(payload),'row_count':1,
       'partition_key':'P_fixture','entity_id':row['entity_id'],'minimum_key':f.observation_key(row),'maximum_key':f.observation_key(row)}
    metadata={'source_view':source['source_view'],'dataset':ref('DS_FIXTURE'),'selection':source['selection'],'unit':'fixture_unit',
       'value_semantics':'numeric_level','cadence':source['cadence'],'history_policy':source['history_policy'],
       'source_policy_bindings':[bindings[0]],'history_mode':'resolved_state','temporal_precision':'date','availability_semantics':'derived_at_cutoff'}
    manifest={'schema_version':'0.3.0','record_type':'materialization_manifest','id':identifier,'version':'1.0.0','dataset_role':'feature','definition':feature_ref,
       'identity_profile':'transformation_execution.1.0.0','input_key':key,'observation_schema_version':'0.3.0','metadata':metadata,'partitions':[partition],
       'row_count':1,'status_counts':{'valid':1,'missing':0,'invalid':0},'semantic_rows_sha256':f.semantic_rows_digest(rows,'date'),'lineage':[row['lineage']]}
    return manifest,rows,feature


class FeatureStoreContractsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema=json.loads((ROOT/'specs/schemas/feature_store.schema.json').read_text())
        Draft202012Validator.check_schema(cls.schema)
        cls.validator=Draft202012Validator(cls.schema,format_checker=FormatChecker())
        row_schema=deepcopy(cls.schema);row_schema.pop('oneOf');row_schema['$ref']='#/$defs/feature_observation'
        cls.row_validator=Draft202012Validator(row_schema,format_checker=FormatChecker())

    def test_manifest_row_operand_and_library_validate(self):
        manifest,rows,feature=materialization_fixture()
        self.assertEqual(f.normalize_materialization(manifest,rows),manifest)
        self.validator.validate(manifest)
        self.row_validator.validate(rows[0])
        operand=operand_fixture();self.assertEqual(f.normalize_pit_operand(operand),operand);self.validator.validate(operand)
        entry=f.make_library_entry(i.reference(feature),[i.reference(manifest)])
        self.assertEqual(f.normalize_library_entry(entry),entry);self.validator.validate(entry)
        self.assertEqual(entry['relationship_results'],[])

    def test_materialization_id_matches_existing_execution_domain(self):
        manifest,_,_=materialization_fixture()
        expected=hashlib.sha256(json.dumps({'identity_profile':'transformation_execution.1.0.0','kind':'materialization','input_key':manifest['input_key']},sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()).hexdigest()
        self.assertEqual(manifest['id'],'MATERIALIZATION_'+expected)
        self.assertEqual(f.make_materialization_id_from_key(manifest['input_key']),manifest['id'])

    def test_stored_manifest_requires_explicit_output_coverage(self):
        manifest,_,_=materialization_fixture();manifest['input_key'].pop('output_index');manifest['input_key']['output_projection']='latest_per_cutoff';manifest['id']=f.make_materialization_id_from_key(manifest['input_key'])
        with self.assertRaises(c.ContractError):f.normalize_materialization(manifest)
        self.assertTrue(list(self.validator.iter_errors(manifest)))

    def test_identity_integrity_and_definition_binding(self):
        for change in ['id','definition','input_hash']:
            manifest,_,_=materialization_fixture()
            if change=='id':manifest['id']='MATERIALIZATION_'+'0'*64
            elif change=='definition':manifest['definition']['content_sha256']='0'*64
            else:manifest['input_key']['input_series_sha256']='0'*64
            with self.assertRaises(c.ContractError,msg=change):f.normalize_materialization(manifest)

    def test_source_and_history_policies_are_pinned(self):
        for field in ['source_policy_bindings','history_policy']:
            manifest,_,_=materialization_fixture()
            if field=='source_policy_bindings':manifest['metadata'][field][0]['artifact']=ref('UNBOUND_POLICY')
            else:manifest['metadata'][field]=ref('UNBOUND_POLICY')
            with self.assertRaises(c.ContractError):f.normalize_materialization(manifest)

    def test_all_null_materialization_is_not_complete(self):
        manifest,rows,_=materialization_fixture();rows[0].update(value=None,status='invalid',reason_code='INSUFFICIENT_HISTORY')
        manifest['status_counts']={'valid':0,'missing':0,'invalid':1};manifest['semantic_rows_sha256']=f.semantic_rows_digest(rows,'date')
        with self.assertRaises(c.ContractError):f.normalize_materialization(manifest,rows)
        self.assertTrue(list(self.validator.iter_errors(manifest)))

    def test_counts_keys_selection_and_lineage_are_checked(self):
        for case in ['row_count','status_counts','partition_count','partition_bound','selection','lineage','digest']:
            manifest,rows,_=materialization_fixture()
            if case=='row_count':manifest['row_count']=2
            elif case=='status_counts':manifest['status_counts']['missing']=1
            elif case=='partition_count':manifest['partitions'][0]['row_count']=2
            elif case=='partition_bound':manifest['partitions'][0]['maximum_key']['reference_time']='2000-02-01'
            elif case=='selection':rows[0]['measure']='OTHER_MEASURE'
            elif case=='lineage':rows[0]['lineage']=ref('OTHER_LINEAGE')
            else:manifest['semantic_rows_sha256']='0'*64
            with self.assertRaises(c.ContractError,msg=case):f.normalize_materialization(manifest,rows)

    def test_revision_outputs_same_reference_keep_distinct_cutoffs(self):
        _,rows,_=materialization_fixture();second=deepcopy(rows[0]);second.update(evaluation_cutoff='2000-04-01',available_at='2000-04-01',value='4',vintage_id='DERIVED_LATER')
        normalized=f.normalize_observations([second,rows[0]],'date')
        self.assertEqual(len(normalized),2);self.assertEqual(normalized[0]['evaluation_cutoff'],'2000-03-01')
        with self.assertRaises(c.ContractError):f.normalize_observations(normalized+[deepcopy(second)],'date')

    def test_semantic_digest_omits_only_redundant_materialization_id(self):
        _,rows,_=materialization_fixture();other=deepcopy(rows);other[0]['materialization_id']='MATERIALIZATION_'+'b'*64
        self.assertEqual(f.semantic_rows_digest(rows,'date'),f.semantic_rows_digest(other,'date'))
        other[0]['lineage']['content_sha256']='0'*64
        self.assertNotEqual(f.semantic_rows_digest(rows,'date'),f.semantic_rows_digest(other,'date'))
        expected=hashlib.sha256(json.dumps([{k:v for k,v in rows[0].items() if k!='materialization_id'}],sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()).hexdigest()
        self.assertEqual(f.semantic_rows_digest(rows,'date'),expected)

    def test_precision_and_derived_availability_cannot_be_fabricated(self):
        for case in ['utc_for_date','mixed_times','old_availability','future_reference']:
            _,rows,_=materialization_fixture();row=rows[0]
            if case=='utc_for_date':row['evaluation_cutoff']='2000-03-01T00:00:00.000000Z'
            elif case=='mixed_times':row['reference_time']='2000-01-01T00:00:00.000000Z'
            elif case=='old_availability':row['available_at']='2000-02-01'
            else:row['reference_time']='2000-04-01'
            with self.assertRaises(c.ContractError):f.normalize_observation(row,'date')
        _,rows,_=materialization_fixture();rows[0].update(reference_time=None,value=None,status='invalid',reason_code='INSUFFICIENT_HISTORY')
        f.normalize_observation(rows[0],'date');self.row_validator.validate(rows[0])

    def test_emitted_metadata_requires_event_order(self):
        manifest,_,_=materialization_fixture();meta=manifest['metadata'];meta['history_mode']='emitted_history'
        with self.assertRaises(c.ContractError):f.normalize_metadata(meta)
        meta['cadence'].update(frequency='event',ordering='evaluation_cutoff');f.normalize_metadata(meta)

    def test_operand_record_is_a_locator_without_copied_observations(self):
        operand=operand_fixture();body=operand['body']
        self.assertNotIn('value',body);self.assertNotIn('status',body)
        self.assertEqual(body['pit_row_digest_profile'],'canonical_stored_row_v1')
        self.assertEqual(operand['id'],'PIT_OPERAND_'+i.digest({k:v for k,v in operand.items() if k!='id'}))
        changed=deepcopy(body);changed['pit_row_sha256']='c'*64
        self.assertNotEqual(operand['id'],f.make_pit_operand(changed)['id'])

    def test_operand_schema_is_closed_and_time_selector_matches(self):
        operand=operand_fixture();operand['body']['value']='12'
        with self.assertRaises(c.ContractError):f.normalize_pit_operand(operand)
        self.assertTrue(list(self.validator.iter_errors(operand)))
        operand=operand_fixture();operand['body']['pit_row_key'][0]['value']='1990-01-01'
        with self.assertRaises(c.ContractError):f.normalize_pit_operand(operand)

    def test_raw_cell_selector_requires_exact_explicit_pit_mapping(self):
        original=operand_fixture()['body']
        for case in ['missing','empty','duplicate','unmapped_raw','unmapped_pit','wrong_raw_coordinate','extra_field']:
            body=deepcopy(original)
            if case=='missing':body.pop('raw_row_mapping')
            elif case=='empty':body['raw_row_mapping']=[]
            elif case=='duplicate':body['raw_row_mapping'].append(deepcopy(body['raw_row_mapping'][0]))
            elif case=='unmapped_raw':body['raw_cell']['row_key'].append({'field':'series','value':'OTHER'})
            elif case=='unmapped_pit':body['raw_row_mapping'][0]['pit_field']='not_in_pit_key'
            elif case=='wrong_raw_coordinate':body['raw_cell']['row_key'][0]['value']='1900-01-01'
            else:body['raw_row_mapping'][0]['implicit']=True
            # Rehashing a false locator must not make it admissible.
            with self.assertRaises(c.ContractError,msg=case):f.make_pit_operand(body)
        body=deepcopy(original)
        body['raw_cell']['row_key'].append({'field':'vintage','value':'2000-02-01'})
        body['raw_row_mapping'].append({'raw_field':'vintage','pit_field':'vintage_date'})
        record=f.make_pit_operand(body);self.validator.validate(record)
        body['raw_row_mapping'].reverse();body['raw_cell']['row_key'].reverse()
        self.assertEqual(f.make_pit_operand(body),record)

    def test_operand_identity_rejects_tampering_and_normalizes_selector_order(self):
        operand=operand_fixture();body=deepcopy(operand['body']);body['pit_row_key'].reverse()
        self.assertEqual(f.make_pit_operand(body),operand)
        operand['body']['raw_cell']['blob_sha256']='0'*64
        with self.assertRaises(c.ContractError):f.normalize_pit_operand(operand)

    def test_signal_entry_needs_no_target_direction_or_research(self):
        manifest,_,feature=materialization_fixture();entry=f.make_library_entry(i.reference(feature),[i.reference(manifest)])
        self.assertEqual(entry['signal_id'],feature['body']['signal_id'])
        self.assertEqual(entry['relationship_results'],[])
        for key in ['target','expected_direction','research_spec','metrics','scientific_status']:self.assertNotIn(key,entry)
        entry['scientific_status']='validated'
        with self.assertRaises(c.ContractError):f.normalize_library_entry(entry)
        self.assertTrue(list(self.validator.iter_errors(entry)))

    def test_signal_entry_rejects_wrong_parent_empty_materializations_and_duplicate_links(self):
        manifest,_,feature=materialization_fixture();entry=f.make_library_entry(i.reference(feature),[i.reference(manifest)])
        entry['signal_id']='SIGNAL_'+'0'*64
        with self.assertRaises(c.ContractError):f.normalize_library_entry(entry)
        with self.assertRaises(c.ContractError):f.make_library_entry(i.reference(feature),[])
        with self.assertRaises(c.ContractError):f.make_library_entry(i.reference(feature),[i.reference(manifest),i.reference(manifest)])

    def test_evaluation_policy_is_optional_but_identity_bearing(self):
        original=recipe_fixture();before=i.feature_id(original)
        recipe=deepcopy(original);recipe['evaluation_policy']=ref('EVALUATION_POLICY')
        self.assertNotEqual(i.feature_id(recipe),before)
        self.assertEqual(i.normalize_recipe(recipe)['evaluation_policy'],recipe['evaluation_policy'])
        changed=deepcopy(recipe);changed['evaluation_policy']['version']='2.0.0'
        self.assertNotEqual(i.feature_id(recipe),i.feature_id(changed))
        self.assertEqual(i.signal_id(recipe)[len('SIGNAL_'):],i.feature_id(recipe)[len('FEATURE_'):])
        self.assertEqual(i.feature_id(original),before)
        platform=json.loads((ROOT/'specs/schemas/platform.schema.json').read_text())
        Draft202012Validator(platform,format_checker=FormatChecker()).validate(i.make_feature_definition(recipe))
        recipe['evaluation_policy']={'id':'UNPINNED'}
        with self.assertRaises(c.ContractError):i.normalize_recipe(recipe)

    def test_library_record_does_not_coerce_array_types(self):
        manifest,_,feature=materialization_fixture();entry=f.make_library_entry(i.reference(feature),[i.reference(manifest)])
        for field in ['relationship_results','feature_materializations']:
            wrong=deepcopy(entry);wrong[field]=tuple(wrong[field])
            with self.assertRaises(c.ContractError):f.normalize_library_entry(wrong)

    def test_operational_execution_audit_is_closed_and_separate(self):
        manifest,_,feature=materialization_fixture()
        audit={'schema_version':'0.3.0','record_type':'feature_execution_audit',
               'attempt_id':'12345678-1234-4123-8123-123456789abc','state':'succeeded',
               'executed_at':'2026-10-09T12:00:00.000000Z','completed_at':'2026-10-09T12:00:01.000000Z',
               'signal_id':feature['body']['signal_id'],'feature':i.reference(feature),'materialization':i.reference(manifest),
               'reused':False,'row_count':1}
        self.assertEqual(f.normalize_execution_audit(audit),audit)
        self.assertEqual(f.validate_record(audit),audit);self.validator.validate(audit)
        self.assertNotIn('id',audit);self.assertNotIn('version',audit)
        repeated=deepcopy(audit);repeated['reused']=True;f.validate_record(repeated)
        for field,bad in [('id','AUDIT_123'),('version','1.0.0'),('attempt_id','not-a-uuid'),('state','validated'),
                          ('executed_at','2026-10-09'),('completed_at','2026-10-09T11:59:59.000000Z'),
                          ('reused',1),('row_count',0),('row_count',True),('signal_id','SIGNAL_'+'0'*64)]:
            value=deepcopy(audit);value[field]=bad
            with self.assertRaises(c.ContractError,msg=field):f.validate_record(value)
        value=deepcopy(audit);value['scientific_state']='validated'
        self.assertTrue(list(self.validator.iter_errors(value)))

    def test_wrong_schema_and_unknown_record_types_reject(self):
        record=operand_fixture();record['schema_version']='0.2.0'
        with self.assertRaises(c.ContractError):f.validate_record(record)
        with self.assertRaises(c.ContractError):f.validate_record({'record_type':'unknown'})
        for record in [operand_fixture(),materialization_fixture()[0]]:self.assertEqual(f.validate_record(record),record)


if __name__=='__main__':unittest.main()
