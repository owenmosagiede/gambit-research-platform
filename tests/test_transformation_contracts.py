"""Independent contract and canonical-identity checks; synthetic inputs only."""
from copy import deepcopy
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import unittest

from jsonschema import Draft202012Validator, FormatChecker
from data.transformations import contracts as c
from data.transformations import identity as i

ROOT = Path(__file__).resolve().parents[1]


def ref(name, version='1.0.0'):
    return {'id':name, 'version':version, 'content_sha256':hashlib.sha256(name.encode()).hexdigest()}


def series_fixture():
    selection = {'measure':'test_measure', 'entity_id':'test_entity', 'dimensions':[{'name':'adjustment','value':'seasonal'}]}
    return {'contract_version':'1.0.0', 'source_view':ref('FIXTURE_SOURCE_VIEW'),
            'source_snapshots':[ref('FIXTURE_SNAPSHOT')], 'selection':selection,
            'unit':'fixture_unit', 'value_semantics':'numeric_level',
            'cadence':{'frequency':'monthly','ordering':'reference_time','gap_policy':'reject','calendar':'gregorian'},
            'history_policy':ref('FIXTURE_HISTORY_POLICY'), 'capabilities':['revision_history'],
            'temporal_precision':'date', 'provenance':{'provider':'SYNTHETIC_PROVIDER'},
            'observations':[dict(selection,reference_time='2000-01-01',available_at='2000-02-01',vintage_id='VINTAGE_ONE',value='3',status='valid',reason_code=None,lineage=ref('FIXTURE_LINEAGE'))]}


def recipe_fixture():
    return {'sources':[{'alias':'source','source_view':ref('FIXTURE_SOURCE_VIEW')}],
            'steps':[{'node':'step1','phase':'transformation','operator':ref('FIXTURE_MEAN'),
                      'inputs':['source'],'parameters':[{'name':'window','unit':'observations','value':{'kind':'integer','value':'3'}}],
                      'grid_policy':ref('FIXTURE_GRID')}],
            'output_node':'step1','output_unit':'fixture_unit','calculation_scope_requirement':'none','scope_policy':None,
            'selection':deepcopy(series_fixture()['selection']), 'history_mode':'resolved_state',
            'history_policy':ref('FIXTURE_HISTORY_POLICY'),'execution_policy':ref('FIXTURE_EXECUTION_POLICY')}


def result_fixture():
    source=series_fixture()
    recipe_ref=i.reference(i.make_feature_definition(recipe_fixture()))
    implementation=ref('FIXTURE_IMPLEMENTATION')
    lineage={'schema_version':'0.2.0','record_type':'lineage_manifest','version':'1.0.0',
             'inputs':[{'role':'source_snapshot','artifact':source['source_snapshots'][0]}],
             'operation':recipe_ref,'implementation':implementation,
             'policy_bindings':[{'role':'history','artifact':source['history_policy']}]}
    lineage['id']='LINEAGE_'+i.digest(lineage)
    lineage_ref=i.reference(lineage)
    output=deepcopy(source)
    output['observations'][0].update(available_at='2000-03-01',evaluation_cutoff='2000-03-01',vintage_id='DERIVED_ONE',lineage=lineage_ref)
    output['execution']={'recipe':recipe_ref,
            'materialization_id':i.execution_materialization_id(recipe_ref,source,['2000-03-01'],implementation),
            'identity_profile':'transformation_execution.1.0.0','implementation':implementation,
            'executed_at':'2000-03-02T13:00:00.000000Z','cutoffs':['2000-03-01'],'status':'complete',
            'availability_semantics':'derived_at_cutoff','history_mode':'resolved_state',
            'lineage':[lineage_ref],'lineage_records':[lineage]}
    return output


def independent_sha(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()).hexdigest()


class TransformationContractsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema=json.loads((ROOT/'specs/schemas/transformation_execution.schema.json').read_text())
        Draft202012Validator.check_schema(cls.schema)
        cls.validator=Draft202012Validator(cls.schema,format_checker=FormatChecker())

    def assertRejected(self, value, result=False):
        with self.assertRaises(c.ContractError):
            (c.normalize_result if result else c.normalize_input)(value)

    def test_input_output_share_one_envelope(self):
        raw=series_fixture(); result=result_fixture()
        self.assertEqual(c.normalize_input(raw),raw)
        self.assertEqual(c.normalize_input(result),c.normalize_result(result))
        self.validator.validate(raw); self.validator.validate(result)

    def test_input_is_not_mutated(self):
        raw=series_fixture(); before=deepcopy(raw)
        c.normalize_input(raw); i.input_series_digest(raw)
        self.assertEqual(raw,before)

    def test_partition_contamination_rejected(self):
        for key,value in [('entity_id','other'),('measure','other'),('dimensions',[])]:
            with self.subTest(key=key):
                raw=series_fixture(); raw['observations'][0][key]=value
                self.assertRejected(raw)

    def test_duplicate_temporal_keys_rejected_even_when_vintage_name_differs(self):
        raw=series_fixture(); second=deepcopy(raw['observations'][0]); second['vintage_id']='VINTAGE_TWO'
        raw['observations'].append(second); self.assertRejected(raw)

    def test_revision_history_permits_same_reference_at_later_availability(self):
        raw=series_fixture(); second=deepcopy(raw['observations'][0]); second.update(available_at='2000-03-01',value='4',vintage_id='VINTAGE_TWO')
        raw['observations'].insert(0,second)
        self.assertEqual([r['value'] for r in c.normalize_input(raw)['observations']],['3','4'])

    def test_dimensions_sort_without_ambiguous_names(self):
        raw=series_fixture()
        dims=[{'name':'z','value':'two'},{'name':'a','value':'one'}]
        raw['selection']['dimensions']=dims; raw['observations'][0]['dimensions']=deepcopy(dims)
        self.assertEqual(c.normalize_input(raw)['selection']['dimensions'][0]['name'],'a')
        raw['selection']['dimensions'].append({'name':'a','value':'different'})
        self.assertRejected(raw)

    def test_noncanonical_and_nonfinite_values_are_not_silently_coerced(self):
        for value in [3,3.0,True,'NaN','Infinity','-Infinity','1.0','01','1e2','-0','0.0','+1']:
            with self.subTest(value=value):
                raw=series_fixture(); raw['observations'][0]['value']=value
                self.assertRejected(raw)
        for value in ['0','-3','0.25','-0.25','2000000000000000000000001']:
            raw=series_fixture(); raw['observations'][0]['value']=value
            c.normalize_input(raw)

    def test_decimal_formatting_is_an_explicit_separate_boundary(self):
        self.assertEqual(c.decimal_text(Decimal('1.2000')),'1.2')
        self.assertEqual(c.decimal_text(Decimal('-0.000')),'0')
        for value in [True,float('nan'),Decimal('Infinity')]:
            with self.assertRaises(c.ContractError): c.decimal_text(value)

    def test_strict_json_rejects_duplicate_keys_and_nonfinite_tokens(self):
        for text in ['{"x":1,"x":2}','{"x":NaN}','{"x":Infinity}']:
            with self.assertRaises((c.ContractError,ValueError)): c.load_json_strict(text)

    def test_unknown_fields_and_invalid_status_pairs_rejected(self):
        raw=series_fixture();raw['unrecorded_transform']='mean';self.assertRejected(raw)
        for status,value,reason in [('valid',None,None),('valid','3','ZERO_VARIANCE'),('missing','3','SOURCE_MISSING'),('invalid',None,None),('missing',None,'SILENT_DROP')]:
            with self.subTest(status=status,value=value,reason=reason):
                raw=series_fixture();raw['observations'][0].update(status=status,value=value,reason_code=reason);self.assertRejected(raw)
        raw=series_fixture();raw['observations'][0].update(status='missing',value=None,reason_code='SOURCE_MISSING')
        c.normalize_input(raw);self.validator.validate(raw)

    def test_date_precision_is_never_promoted_to_midnight(self):
        for field in ['reference_time','available_at']:
            raw=series_fixture();raw['observations'][0][field]='2000-02-01T00:00:00.000000Z';self.assertRejected(raw)
        with self.assertRaises(c.ContractError): c.normalize_cutoffs(['2000-02-01T00:00:00.000000Z'],'date')
        self.assertEqual(c.normalize_cutoffs(['2000-03-01','2000-02-01'],'date'),['2000-02-01','2000-03-01'])
        for value in ['2000-02-30','2000-2-01','2000-02-01\n']:
            with self.assertRaises(c.ContractError): c.normalize_time(value,'date')

    def test_utc_precision_requires_explicit_canonical_utc(self):
        raw=series_fixture();raw['temporal_precision']='utc_timestamp'
        raw['observations'][0].update(reference_time='2000-01-01T00:00:00.000000Z',available_at='2000-02-01T12:00:00.123456Z')
        c.normalize_input(raw);self.validator.validate(raw)
        for value in ['2000-02-01','2000-02-01T00:00:00Z','2000-02-01T00:00:00.000000+00:00']:
            raw['observations'][0]['available_at']=value;self.assertRejected(raw)

    def test_cadence_domains_and_intraday_interval(self):
        expected={'tick','intraday','daily','weekly','monthly','quarterly','semiannual','annual','irregular','event'}
        self.assertEqual(c.FREQUENCIES,expected)
        for frequency in expected:
            raw=series_fixture();raw['cadence']['frequency']=frequency
            if frequency=='intraday':raw['cadence']['interval_seconds']='60'
            c.normalize_input(raw);self.validator.validate(raw)
        for interval in [None,'0','-60','01',60,'60.0']:
            raw=series_fixture();raw['cadence']['frequency']='intraday'
            if interval is not None:raw['cadence']['interval_seconds']=interval
            self.assertRejected(raw);self.assertTrue(list(self.validator.iter_errors(raw)))
        raw=series_fixture();raw['cadence']['interval_seconds']='60';self.assertRejected(raw)
        raw=series_fixture();raw['cadence']['frequency']='yearly';self.assertRejected(raw)

    def test_structural_validation_does_not_probe_future_calendar_gaps(self):
        raw=series_fixture();later=deepcopy(raw['observations'][0]);later.update(reference_time='2001-11-01',available_at='2001-12-01',vintage_id='FUTURE')
        raw['observations'].append(later)
        self.assertEqual(len(c.normalize_input(raw)['observations']),2)

    def test_release_anchors_require_capability_and_preserve_time(self):
        raw=series_fixture();raw['release_events']=[{'reference_time':'2000-01-01','available_at':'2000-02-01','lineage':ref('RELEASE_LINEAGE')}]
        self.assertRejected(raw)
        raw['capabilities'].append('release_events');c.normalize_input(raw);self.validator.validate(raw)
        raw['release_events'].append(deepcopy(raw['release_events'][0]));self.assertRejected(raw)

    def test_pinned_evidence_cannot_be_absent_or_conflicting(self):
        raw=series_fixture();raw['source_snapshots']=[];self.assertRejected(raw)
        raw=series_fixture();duplicate=deepcopy(raw['source_snapshots'][0]);duplicate['content_sha256']='0'*64;raw['source_snapshots'].append(duplicate);self.assertRejected(raw)
        raw=series_fixture();raw['capabilities']=['release_events'];self.assertRejected(raw)

    def test_result_requires_cutoff_and_conservative_availability(self):
        for change in ['absent','future','old_availability','unknown_lineage']:
            result=result_fixture();row=result['observations'][0]
            if change=='absent':row.pop('evaluation_cutoff')
            if change=='future':row['reference_time']='2000-04-01'
            if change=='old_availability':row['available_at']='2000-02-01'
            if change=='unknown_lineage':row['lineage']=ref('OTHER_LINEAGE')
            self.assertRejected(result,result=True)

    def test_no_reference_is_representable_only_for_failed_derived_output(self):
        result=result_fixture();result['observations'][0].update(reference_time=None,value=None,status='invalid',reason_code='INSUFFICIENT_HISTORY');result['execution']['status']='no_valid_output'
        c.normalize_result(result);self.validator.validate(result)
        result['execution']['status']='complete';self.assertRejected(result,result=True)
        raw=series_fixture();raw['observations'][0].update(reference_time=None,value=None,status='invalid',reason_code='INSUFFICIENT_HISTORY');self.assertRejected(raw)

    def test_result_status_describes_actual_valid_rows(self):
        result=result_fixture();second=deepcopy(result['observations'][0]);second.update(reference_time='2000-02-01',value=None,status='invalid',reason_code='ZERO_VARIANCE');result['observations'].append(second)
        self.assertRejected(result,result=True)
        result['execution']['status']='partial';c.normalize_result(result)
        result['observations']=[];result['execution']['status']='no_valid_output';c.normalize_result(result)

    def test_emitted_result_orders_by_cutoff_not_economic_reference(self):
        result=result_fixture();result['execution']['history_mode']='emitted_history'
        self.assertRejected(result,result=True)
        result['cadence'].update(frequency='event',ordering='evaluation_cutoff')
        c.normalize_result(result);self.validator.validate(result)
        second=deepcopy(result['observations'][0]);second.update(reference_time='1999-01-01',available_at='2000-04-01',evaluation_cutoff='2000-04-01',vintage_id='OLDER_REFERENCE_RELEASE')
        result['observations'].insert(0,second);result['execution']['cutoffs'].append('2000-04-01')
        normalized=c.normalize_result(result)
        self.assertEqual([row['reference_time'] for row in normalized['observations']],['2000-01-01','1999-01-01'])
        raw=series_fixture();raw['cadence'].update(frequency='event',ordering='evaluation_cutoff')
        self.assertRejected(raw);self.assertTrue(list(self.validator.iter_errors(raw)))
        result['cadence']['frequency']='monthly';self.assertRejected(result,result=True)

    def test_same_reference_may_repeat_at_distinct_requested_cutoffs(self):
        result=result_fixture();row=deepcopy(result['observations'][0]);row.update(available_at='2000-04-01',evaluation_cutoff='2000-04-01',vintage_id='DERIVED_TWO');result['observations'].append(row);result['execution']['cutoffs'].append('2000-04-01')
        c.normalize_result(result)
        result['observations'].append(deepcopy(row));self.assertRejected(result,result=True)

    def test_lineage_manifest_hash_is_checked(self):
        result=result_fixture();result['execution']['lineage_records'][0]['inputs'][0]['artifact']['content_sha256']='0'*64
        self.assertRejected(result,result=True)

    def test_json_schema_is_closed_and_handles_failure_boundaries(self):
        failures=[]
        raw=series_fixture();raw['unknown']=False;failures.append(raw)
        raw=series_fixture();raw['observations'][0]['value']=4;failures.append(raw)
        raw=series_fixture();raw['observations'][0]['status']='missing';failures.append(raw)
        raw=series_fixture();raw['observations'][0]['reference_time']=None;failures.append(raw)
        raw=series_fixture();raw['observations'][0]['available_at']='2000-02-30';failures.append(raw)
        raw=series_fixture();raw['observations'][0]['lineage']['id']='x\n';failures.append(raw)
        for raw in failures:self.assertTrue(list(self.validator.iter_errors(raw)))


class TransformationIdentityTests(unittest.TestCase):
    def test_existing_feature_and_materialization_vectors_are_unchanged(self):
        records=json.loads((ROOT/'tests/fixtures/specification_v0_2/catalog_records.json').read_text())
        for record in records:
            if record['record_type']=='feature_definition':
                recipe=record['body']['recipe']
                self.assertEqual(i.feature_id(recipe),record['id'])
                self.assertEqual(i.signal_id(recipe),record['body']['signal_id'])
            if record['record_type']=='materialization_manifest':
                key={field:record[field] for field in i.MATERIALIZATION_FIELDS}
                self.assertEqual(i.materialization_id(key),record['id'])
                self.assertEqual(i.materialization_id(key),'MATERIALIZATION_'+independent_sha({'identity_profile':'0.2.0','kind':'materialization','input_key':key}))

    def test_profile_projection_and_shared_signal_suffix(self):
        recipe=recipe_fixture();normalized=i.normalize_recipe(recipe)
        expected=independent_sha({'identity_profile':'0.2.0','kind':'predictor_recipe','recipe':normalized})
        self.assertEqual(i.feature_id(recipe),'FEATURE_'+expected)
        self.assertEqual(i.signal_id(recipe),'SIGNAL_'+expected)

    def test_labels_are_outside_definition_identity(self):
        a=i.make_feature_definition(recipe_fixture(),'Display A');b=i.make_feature_definition(recipe_fixture(),'Display B')
        self.assertEqual(a['id'],b['id']);self.assertEqual(i.reference(a),i.reference(b))
        a['body']['recipe']['steps'][0]['operator']['content_sha256']='0'*64
        self.assertNotEqual(i.reference(a),i.reference(b))

    def test_new_data_changes_execution_not_logical_feature_identity(self):
        recipe=recipe_fixture();old=series_fixture();new=deepcopy(old);new['observations'][0]['value']='4'
        feature=i.make_feature_definition(recipe);feature_ref=i.reference(feature);implementation=ref('IMPLEMENTATION')
        original=i.execution_materialization_id(feature_ref,old,['2000-03-01'],implementation)
        self.assertEqual(i.feature_id(recipe),feature['id'])
        self.assertNotEqual(original,i.execution_materialization_id(feature_ref,new,['2000-03-01'],implementation))
        new=deepcopy(old);new['source_snapshots'][0]['content_sha256']='0'*64
        self.assertNotEqual(original,i.execution_materialization_id(feature_ref,new,['2000-03-01'],implementation))

    def test_execution_input_digest_excludes_provider_labels_and_wall_clock(self):
        old=series_fixture();new=deepcopy(old);new['provenance']['provider']='RENAMED_PROVIDER'
        self.assertEqual(i.input_series_digest(old),i.input_series_digest(new))
        old=result_fixture();new=deepcopy(old);new['execution']['executed_at']='2000-03-04T11:00:00.000000Z'
        self.assertEqual(i.input_series_digest(old),i.input_series_digest(new))
        new['observations'][0]['value']='4';self.assertNotEqual(i.input_series_digest(old),i.input_series_digest(new))

    def test_transient_execution_key_preserves_date_and_is_separate_domain(self):
        recipe_ref=i.reference(i.make_feature_definition(recipe_fixture()));source=series_fixture();implementation=ref('IMPLEMENTATION')
        key=i.execution_materialization_key(recipe_ref,source,['2000-03-01'],implementation)
        self.assertEqual(key['evaluation_cutoffs'],['2000-03-01']);self.assertEqual(key['temporal_precision'],'date')
        expected='MATERIALIZATION_'+independent_sha({'identity_profile':'transformation_execution.1.0.0','kind':'materialization','input_key':key})
        self.assertEqual(i.execution_materialization_id(recipe_ref,source,['2000-03-01'],implementation),expected)
        self.assertNotEqual(expected,'MATERIALIZATION_'+independent_sha({'identity_profile':'0.2.0','kind':'materialization','input_key':key}))
        schema=json.loads((ROOT/'specs/schemas/transformation_execution.schema.json').read_text());schema['$ref']='#/$defs/execution_materialization_key';Draft202012Validator(schema,format_checker=FormatChecker()).validate(key)

    def test_output_coverage_is_part_of_materialization_identity(self):
        source=series_fixture();recipe_ref=i.reference(i.make_feature_definition(recipe_fixture()));implementation=ref('IMPLEMENTATION')
        latest=[{'reference_time':'2000-02-01','evaluation_cutoff':'2000-03-01'}]
        history=latest+[{'reference_time':'2000-01-01','evaluation_cutoff':'2000-03-01'}]
        def identity(index):return i.execution_materialization_id(recipe_ref,source,['2000-03-01'],implementation,output_index=index)
        self.assertNotEqual(identity(latest),identity(history))
        self.assertEqual(identity(history),identity(list(reversed(history))))
        self.assertNotEqual(identity(None),identity(latest))
        self.assertNotEqual(identity([]),identity([{'reference_time':None,'evaluation_cutoff':'2000-03-01'}]))
        for invalid in [latest+latest,[{'reference_time':'2000-04-01','evaluation_cutoff':'2000-03-01'}],[{'reference_time':'2000-02-01','evaluation_cutoff':'2000-04-01'}]]:
            with self.assertRaises(c.ContractError):identity(invalid)

    def test_cutoff_and_implementation_change_materialization(self):
        source=series_fixture();recipe_ref=i.reference(i.make_feature_definition(recipe_fixture()));implementation=ref('IMPLEMENTATION')
        original=i.execution_materialization_id(recipe_ref,source,['2000-03-01'],implementation)
        self.assertNotEqual(original,i.execution_materialization_id(recipe_ref,source,['2000-04-01'],implementation))
        self.assertNotEqual(original,i.execution_materialization_id(recipe_ref,source,['2000-03-01'],ref('IMPLEMENTATION','2.0.0')))

    def test_recipe_execution_policy_history_selection_and_grid_are_semantic(self):
        original=recipe_fixture();baseline=i.feature_id(original)
        for change in ['history_mode','history_policy','execution_policy','selection','grid_policy','operator_version','operator_digest','parameter']:
            recipe=deepcopy(original)
            if change=='history_mode':recipe['history_mode']='emitted_history'
            elif change in ['history_policy','execution_policy']:recipe[change]['version']='2.0.0'
            elif change=='selection':recipe['selection']['entity_id']='OTHER_ENTITY'
            elif change=='grid_policy':recipe['steps'][0]['grid_policy']['version']='2.0.0'
            elif change=='operator_version':recipe['steps'][0]['operator']['version']='2.0.0'
            elif change=='operator_digest':recipe['steps'][0]['operator']['content_sha256']='0'*64
            else:recipe['steps'][0]['parameters'][0]['value']['value']='5'
            self.assertNotEqual(baseline,i.feature_id(recipe),change)

    def test_parameter_order_is_normalized_but_step_order_is_semantic(self):
        recipe=recipe_fixture();recipe['steps'][0]['parameters'].append({'name':'alpha','unit':'dimensionless','value':{'kind':'decimal','value':'0.5'}})
        permuted=deepcopy(recipe);permuted['steps'][0]['parameters'].reverse()
        self.assertEqual(i.feature_id(recipe),i.feature_id(permuted))
        second=deepcopy(recipe['steps'][0]);second.update(node='step2',inputs=['step1'],operator=ref('FIXTURE_DIFFERENCE'));recipe['steps'].append(second);recipe['output_node']='step2'
        permuted=deepcopy(recipe);permuted['steps'][0]['operator'],permuted['steps'][1]['operator']=permuted['steps'][1]['operator'],permuted['steps'][0]['operator']
        self.assertNotEqual(i.feature_id(recipe),i.feature_id(permuted))

    def test_generic_profile_normalizes_source_order_but_execution_rejects_interactions(self):
        recipe=recipe_fixture();recipe['sources'].append({'alias':'second','source_view':ref('SECOND_SOURCE')})
        recipe['steps'][0]['phase']='interaction';recipe['steps'][0]['inputs']=['source','second']
        second=deepcopy(recipe['steps'][0]);second.update(node='step2',phase='transformation',inputs=['step1']);recipe['steps'].append(second);recipe['output_node']='step2'
        permuted=deepcopy(recipe);permuted['sources'].reverse()
        self.assertEqual(i.feature_id(recipe),i.feature_id(permuted))
        permuted['steps'][0]['inputs'].reverse();self.assertNotEqual(i.feature_id(recipe),i.feature_id(permuted))
        with self.assertRaises(c.ContractError):i.normalize_recipe(recipe)

    def test_execution_recipe_requires_explicit_one_mode_and_closed_parameters(self):
        for case in ['missing_policy','step_mode','unknown_param_field','duplicate_parameter','numeric_parameter','bound_scope']:
            recipe=recipe_fixture()
            if case=='missing_policy':recipe.pop('history_policy')
            elif case=='step_mode':recipe['steps'][0]['history_mode']='emitted_history'
            elif case=='unknown_param_field':recipe['steps'][0]['parameters'][0]['default']=3
            elif case=='duplicate_parameter':recipe['steps'][0]['parameters'].append(deepcopy(recipe['steps'][0]['parameters'][0]))
            elif case=='numeric_parameter':recipe['steps'][0]['parameters'][0]['value']['value']=3
            else:recipe.update(calculation_scope_requirement='bound_at_materialization',scope_policy=ref('SCOPE_POLICY'))
            with self.assertRaises(c.ContractError,msg=case):i.normalize_recipe(recipe)

    def test_canonical_serializer_rejects_float_and_nonstring_keys(self):
        for value in [{'x':3.0},{3:'x'},{'x':Decimal('3')}]:
            with self.assertRaises(c.ContractError):i.canonical_bytes(value)
        self.assertEqual(i.canonical_bytes({'b':2,'a':1}),b'{"a":1,"b":2}')


if __name__=='__main__':unittest.main()
