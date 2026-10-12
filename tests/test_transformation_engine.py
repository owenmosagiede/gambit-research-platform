"""Independent, synthetic acceptance for composition and historical execution."""
from copy import deepcopy
from datetime import date, timedelta
import math
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from jsonschema import Draft202012Validator

from data.transformations.contracts import normalize_result, decimal_text, ContractError
from data.transformations.identity import reference, feature_id, signal_id
from data.transformations.registry import Registry
from data.transformations.engine import execute_recipe, execute_stages, RecipeError, InputError, ExecutionFailure
from test_transformation_numeric import NUMERICAL_EXAMPLES


def ref(identifier):
    return {'id':identifier,'version':'1.0.0','content_sha256':'a'*64}


def fixture(registry, values, *, times=None, frequency='daily', semantics='numeric_level'):
    times = times or [(date(2020,1,1)+timedelta(days=i)).isoformat() for i in range(len(values))]
    selection = {'measure':'VALUE','entity_id':'ENTITY_A','dimensions':[{'name':'adjustment','value':'none'}]}
    rows = [{**deepcopy(selection),'reference_time':time,'available_at':time,'vintage_id':'V_'+str(i),
             'value':None if value is None else decimal_text(value),'status':'missing' if value is None else 'valid',
             'reason_code':'SOURCE_MISSING' if value is None else None,'lineage':ref('LINEAGE_SOURCE_'+str(i))}
            for i,(time,value) in enumerate(zip(times,values))]
    return {'contract_version':'1.0.0','source_view':ref('VIEW_SYNTHETIC'),'source_snapshots':[ref('SNAPSHOT_SYNTHETIC')],
        'selection':selection,'unit':'units','value_semantics':semantics,
        'cadence':{'frequency':frequency,'ordering':'reference_time','gap_policy':'reject','calendar':'gregorian'},
        'history_policy':reference(registry.get_policy('POL_TRANSFORM_HISTORY')),
        'capabilities':['revision_history','release_events'],'temporal_precision':'date','provenance':{'provider':'Synthetic A'},
        'observations':rows,'release_events':[{'reference_time':r['reference_time'],'available_at':r['available_at'],'lineage':r['lineage']} for r in rows]}


def recipe_for(registry, source, specs, *, mode='resolved_state', unit='units'):
    steps=[]
    previous='source'
    for index,(identifier,parameters) in enumerate(specs):
        entry=registry.operator(identifier)
        typed=[]
        for spec in entry['body']['parameters']:
            if spec['name'] not in parameters: continue
            value=parameters[spec['name']]
            if spec['value_kind'] in ('integer','decimal'):value=decimal_text(value)
            typed.append({'name':spec['name'],'unit':spec['unit'],'value':{'kind':spec['value_kind'],'value':value}})
        node='step_'+str(index)
        steps.append({'node':node,'phase':'transformation','operator':reference(entry),'inputs':[previous],'parameters':typed})
        previous=node
    return {'sources':[{'alias':'source','source_view':source['source_view']}],'steps':steps,'output_node':previous,
            'output_unit':unit,'calculation_scope_requirement':'none','scope_policy':None,'selection':source['selection'],
            'history_mode':mode,'history_policy':source['history_policy'],
            'execution_policy':reference(registry.get_policy('POL_TRANSFORM_EXECUTION'))}


def final_value(result):
    return float(result['observations'][-1]['value'])


class TransformationEngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.registry=Registry()

    def run_recipe(self,source,recipe,cutoffs=None):
        return execute_recipe(source,recipe,cutoffs or [max(r['available_at'] for r in source['observations'])],registry=self.registry)

    def test_all_92_nonrelease_registrations_have_defined_independent_fixture(self):
        tested=[]
        for entry in self.registry.all_operators():
            c=entry['body']['execution_contract']
            if c['temporal_mode']!='reference_state':continue
            ex=NUMERICAL_EXAMPLES[c['kernel']]
            values,times=list(ex['values']),ex.get('reference_times')
            frequency=ex.get('frequency','daily')
            if c['kernel'].startswith('seasonal.'):
                by_date=dict(zip(times,values));start,end=date.fromisoformat(times[0]),date.fromisoformat(times[-1])
                times=[];current=start
                while current<=end:
                    times.append(current.isoformat());year=current.year+(current.month==12);month=current.month%12+1;current=date(year,month,1)
                values=[by_date.get(t) for t in times]
            source=fixture(self.registry,values,times=times,frequency=frequency,semantics='price' if entry['id'].startswith('TR_PRICE_') else 'numeric_level')
            rule=c['output_unit_rule']
            unit={'dimensionless':'dimensionless','observation_count':'observations','log_input':'log_units','per_observation':'units_per_observation'}.get(rule,'units')
            if rule=='change_basis' and ex['parameters']['basis']!='diff':unit='dimensionless'
            recipe=recipe_for(self.registry,source,[(entry['id'],ex['parameters'])],unit=unit)
            with self.subTest(operator=entry['id']):
                result=self.run_recipe(source,recipe)
                self.assertEqual(result['execution']['status'],'complete',result['observations'])
                self.assertAlmostEqual(final_value(result),ex['expected_last'],places=10)
                self.assertEqual(normalize_result(result),result)
                tested.append(entry['id'])
        self.assertEqual(len(tested),92)

    def test_all_six_release_registrations(self):
        mapping={'TR_RELEASE_level':'level.raw','TR_RELEASE_change_diff':'change.diff','TR_RELEASE_change_pct':'change.pct',
                 'TR_RELEASE_standard_zscore':'standard.zscore','TR_RELEASE_trend_ma_relative':'trend.ma_relative'}
        for identifier,kernel in mapping.items():
            ex=NUMERICAL_EXAMPLES[kernel];source=fixture(self.registry,ex['values'])
            unit='units' if kernel in ('level.raw','change.diff') else 'dimensionless'
            recipe=recipe_for(self.registry,source,[(identifier,ex['parameters'])],unit=unit)
            with self.subTest(operator=identifier):self.assertAlmostEqual(final_value(self.run_recipe(source,recipe)),ex['expected_last'],places=10)
        source=fixture(self.registry,[1,2,4,8,16])
        recipe=recipe_for(self.registry,source,[('TR_RELEASE_shock_change_zscore',{'k':1,'w':3,'basis':'diff'})],mode='emitted_history',unit='dimensionless')
        # Own-event changes are1,2,4,8. Prior mean7/3; sampleSDsqrt(7/3).
        self.assertAlmostEqual(final_value(self.run_recipe(source,recipe)),17/math.sqrt(21),places=12)

    def test_exact_composition_percent_smooth_standardize(self):
        source=fixture(self.registry,[10,20,60,240,1200,7200,50400])
        recipe=recipe_for(self.registry,source,[('TR_BASE_change_pct',{'k':1}),('TR_BASE_smooth_sma',{'w':2}),('TR_BASE_standard_zscore',{'w':3})],unit='dimensionless')
        # Declared fractional returns1..6; SMA1.5..5.5. Exclusive baseline2.5,3.5,4.5.
        self.assertAlmostEqual(final_value(self.run_recipe(source,recipe)),2)
        stages=execute_stages(source,recipe,['2020-01-07'],registry=self.registry)
        self.assertEqual(len(stages),3)
        self.assertEqual([s['value_semantics'] for s in stages],['fractional_change','fractional_change','score'])
        for stage in stages:self.assertEqual(normalize_result(stage),stage)
        self.assertNotEqual(stages[-1]['execution']['materialization_id'],self.run_recipe(source,recipe)['execution']['materialization_id'])

    def test_direct_distribution_composition_catches_double_difference(self):
        source=fixture(self.registry,[1,2,4,8,16])
        direct=recipe_for(self.registry,source,[('TR_BASE_change_diff',{'k':1}),('TR_CORE_input_distribution_iqr',{'w':4})])
        old=recipe_for(self.registry,source,[('TR_BASE_change_diff',{'k':1}),('TR_BASE_distribution_iqr',{'w':3})])
        self.assertEqual(final_value(self.run_recipe(source,direct)),3.25)
        self.assertEqual(final_value(self.run_recipe(source,old)),1.5)

    def test_cutoff_revision_leakage_and_emitted_history_distinction(self):
        source=fixture(self.registry,[10,20,30])
        changed=deepcopy(source);rev=deepcopy(source['observations'][0]);rev.update(available_at='2020-01-03',value='100',vintage_id='REVISION')
        changed['observations'].append(rev)
        specs=[('TR_BASE_level_raw',{}),('TR_CORE_core_rolling_sum',{'w':3})]
        current=recipe_for(self.registry,changed,specs)
        emitted=recipe_for(self.registry,changed,specs,mode='emitted_history')
        self.assertEqual(final_value(self.run_recipe(changed,current)),150)
        self.assertEqual(final_value(self.run_recipe(changed,emitted)),60)
        sma=recipe_for(self.registry,source,[('TR_BASE_smooth_sma',{'w':2})])
        earlier=self.run_recipe(source,sma,['2020-01-02'])
        future=self.run_recipe(changed,sma,['2020-01-02'])
        self.assertEqual(final_value(earlier),15);self.assertEqual(final_value(future),15)
        appended=fixture(self.registry,[10,20,30,999])
        self.assertEqual(final_value(self.run_recipe(appended,sma,['2020-01-02'])),15)

    def test_release_shock_keeps_own_release_changes_through_revision(self):
        source=fixture(self.registry,[1,2,4,8,16])
        recipe=recipe_for(self.registry,source,[('TR_RELEASE_shock_change_zscore',{'k':1,'w':3,'basis':'diff'})],mode='emitted_history',unit='dimensionless')
        revision=deepcopy(source['observations'][0]);revision.update(available_at='2020-01-05',value='1000',vintage_id='LATE_REVISION')
        source['observations'].append(revision)
        self.assertAlmostEqual(final_value(self.run_recipe(source,recipe)),17/math.sqrt(21),places=12)
        recipe['history_mode']='resolved_state'
        with self.assertRaisesRegex(RecipeError,'UNDECLARED_HISTORY_MODE'):self.run_recipe(source,recipe)

    def test_missing_periods_are_not_dropped(self):
        source=fixture(self.registry,[1,3],times=['2020-01-01','2020-01-03'])
        recipe=recipe_for(self.registry,source,[('TR_BASE_smooth_sma',{'w':2})])
        with self.assertRaisesRegex(InputError,'MISSING_PERIOD'):self.run_recipe(source,recipe)
        source['cadence']['gap_policy']='explicit_missing'
        with self.assertRaisesRegex(InputError,'MISSING_PERIOD'):self.run_recipe(source,recipe)
        source=fixture(self.registry,[1,None,3]);source['cadence']['gap_policy']='explicit_missing'
        result=self.run_recipe(source,recipe)
        self.assertEqual(result['execution']['status'],'no_valid_output')
        self.assertEqual(result['observations'][0]['reason_code'],'SOURCE_MISSING')
        source['cadence']['frequency']='irregular';source['observations'].pop(1)
        self.assertEqual(final_value(self.run_recipe(source,recipe)),2)

    def test_provider_labels_do_not_change_math_or_execution_identity(self):
        a=fixture(self.registry,[1,2,3]);b=deepcopy(a);b['provenance']={'provider':'Completely unrelated provider','dataset_label':'Test B'}
        recipe=recipe_for(self.registry,a,[('TR_BASE_change_diff',{'k':1})])
        ar,br=self.run_recipe(a,recipe),self.run_recipe(b,recipe)
        self.assertEqual(ar['observations'],br['observations'])
        self.assertEqual(ar['execution']['materialization_id'],br['execution']['materialization_id'])

    def test_isolation_and_selection_rejections(self):
        source=fixture(self.registry,[1,2,3]);recipe=recipe_for(self.registry,source,[('TR_BASE_level_raw',{})])
        for field,value in [('entity_id','ENTITY_B'),('measure','OTHER'),('dimensions',[{'name':'adjustment','value':'different'}])]:
            broken=deepcopy(source);broken['observations'][1][field]=value
            with self.subTest(field=field),self.assertRaises(ContractError):self.run_recipe(broken,recipe)
        wrong=deepcopy(recipe);wrong['selection']['entity_id']='OTHER'
        with self.assertRaises(RecipeError):self.run_recipe(source,wrong)

    def test_price_domain_and_recipe_compatibility(self):
        source=fixture(self.registry,[1,-2,4],semantics='price')
        recipe=recipe_for(self.registry,source,[('TR_PRICE_change_pct',{'k':1})],unit='dimensionless')
        result=self.run_recipe(source,recipe)
        self.assertEqual(result['observations'][0]['reason_code'],'NONPOSITIVE_INPUT')
        source['value_semantics']='numeric_level'
        with self.assertRaisesRegex(RecipeError,'INAPPLICABLE'):self.run_recipe(source,recipe)
        bad=recipe_for(self.registry,source,[('TR_BASE_change_pct',{'k':1})],unit='units')
        with self.assertRaisesRegex(RecipeError,'unit'):self.run_recipe(source,bad)

    def test_release_eligibility_and_explicit_anchor(self):
        source=fixture(self.registry,[1,2,4]);recipe=recipe_for(self.registry,source,[('TR_RELEASE_level',{})])
        result=self.run_recipe(source,recipe,['2020-01-04'])
        self.assertEqual(result['observations'][0]['reason_code'],'INAPPLICABLE')
        source['capabilities']=['resolved_state'];source.pop('release_events')
        with self.assertRaisesRegex(RecipeError,'capabilities'):self.run_recipe(source,recipe)

    def test_timestamp_precision_availability_and_no_execution_time_substitution(self):
        source=fixture(self.registry,[1,2])
        recipe=recipe_for(self.registry,source,[('TR_BASE_level_raw',{})])
        result=execute_recipe(source,recipe,['2019-12-31','2020-01-02'],registry=self.registry,executed_at='2026-10-08T12:00:00.000000Z')
        self.assertEqual(result['execution']['status'],'partial')
        self.assertIsNone(result['observations'][0]['reference_time'])
        self.assertEqual(result['observations'][1]['available_at'],'2020-01-02')
        with self.assertRaises(ContractError):self.run_recipe(source,recipe,['2020-01-02T00:00:00.000000Z'])

    def test_interactions_multi_series_and_temporal_switch_rejected(self):
        source=fixture(self.registry,[1,2,3]);recipe=recipe_for(self.registry,source,[('TR_BASE_level_raw',{})])
        bad=deepcopy(recipe);bad['steps'][0]['phase']='interaction'
        with self.assertRaises(ContractError):self.run_recipe(source,bad)
        bad=deepcopy(recipe);bad['sources'].append({'alias':'other','source_view':ref('OTHER')})
        with self.assertRaises(ContractError):self.run_recipe(source,bad)
        bad=recipe_for(self.registry,source,[('TR_BASE_level_raw',{}),('TR_RELEASE_level',{})])
        with self.assertRaisesRegex(RecipeError,'first step'):self.run_recipe(source,bad)

    def test_unexpected_failure_is_visible(self):
        source=fixture(self.registry,[1,2,3]);recipe=recipe_for(self.registry,source,[('TR_BASE_level_raw',{})])
        with patch('data.transformations.engine.numeric.calculate',side_effect=ExecutionFailure('sentinel defect')):
            with self.assertRaisesRegex(ExecutionFailure,'sentinel'):self.run_recipe(source,recipe)

    def test_logical_identity_stable_but_evidence_and_cutoff_distinguish_materializations(self):
        source=fixture(self.registry,[1,2,3]);recipe=recipe_for(self.registry,source,[('TR_BASE_level_raw',{})])
        before=self.run_recipe(source,recipe);changed=deepcopy(source);changed['observations'][-1]['value']='4'
        after=self.run_recipe(changed,recipe)
        self.assertEqual(feature_id(recipe).removeprefix('FEATURE_'),signal_id(recipe).removeprefix('SIGNAL_'))
        self.assertEqual(before['execution']['recipe'],after['execution']['recipe'])
        self.assertNotEqual(before['execution']['materialization_id'],after['execution']['materialization_id'])
        repeated=execute_recipe(source,recipe,['2020-01-03'],registry=self.registry,executed_at='2020-02-01T00:00:00.000000Z')
        self.assertEqual(before['execution']['materialization_id'],repeated['execution']['materialization_id'])

    def test_real_engine_outputs_and_lineage_conform_to_schemas(self):
        root=Path(__file__).resolve().parents[1]
        schema=json.loads((root/'specs/schemas/transformation_execution.schema.json').read_text())
        platform=json.loads((root/'specs/schemas/platform.schema.json').read_text())
        source=fixture(self.registry,[1,2,4,8,16])
        for mode,specs,unit in [('resolved_state',[('TR_BASE_change_diff',{'k':1}),('TR_BASE_smooth_sma',{'w':2})],'units'),
                                ('emitted_history',[('TR_RELEASE_shock_change_zscore',{'k':1,'w':3,'basis':'diff'})],'dimensionless')]:
            recipe=recipe_for(self.registry,source,specs,mode=mode,unit=unit)
            result=self.run_recipe(source,recipe)
            Draft202012Validator(schema).validate(result)
            for record in result['execution']['lineage_records']:Draft202012Validator(platform).validate(record)

    def test_absent_release_anchor_is_invalid_and_event_lineage_is_preserved(self):
        source=fixture(self.registry,[1,2,3]);recipe=recipe_for(self.registry,source,[('TR_RELEASE_level',{})])
        source['release_events'][-1]['lineage']=ref('LINEAGE_DISTINCT_RELEASE_EVENT')
        result=self.run_recipe(source,recipe)
        refs=[i['artifact'] for r in result['execution']['lineage_records'] for i in r['inputs']]
        self.assertIn(ref('LINEAGE_DISTINCT_RELEASE_EVENT'),refs)
        source['observations'].pop()
        result=self.run_recipe(source,recipe,['2020-01-03'])
        self.assertEqual(result['observations'][0]['reason_code'],'MISSING_REQUIRED_OBSERVATION')
        self.assertEqual(result['observations'][0]['reference_time'],'2020-01-03')

    def test_emitted_reference_dates_may_move_backwards_without_reordering_values(self):
        source=fixture(self.registry,[1,10,100])
        revision=deepcopy(source['observations'][0]);revision.update(value='2',available_at='2020-01-04',vintage_id='REV')
        source['observations'].append(revision)
        source['release_events'].append({'reference_time':'2020-01-01','available_at':'2020-01-04','lineage':ref('LINEAGE_REVISION_EVENT')})
        recipe=recipe_for(self.registry,source,[('TR_RELEASE_level',{}),('TR_CORE_core_rolling_sum',{'w':2})],mode='emitted_history')
        result=self.run_recipe(source,recipe)
        self.assertEqual(final_value(result),102)
        self.assertEqual(result['cadence']['ordering'],'evaluation_cutoff')
        self.assertEqual(result['observations'][0]['reference_time'],'2020-01-01')

    def test_utc_intraday_ordering_and_cadence_are_explicit(self):
        times=['2020-01-01T00:00:00.000000Z','2020-01-01T00:01:00.000000Z','2020-01-01T00:02:00.000000Z']
        source=fixture(self.registry,[1,2,3],times=times,frequency='intraday')
        source['temporal_precision']='utc_timestamp';source['cadence']['interval_seconds']='60'
        recipe=recipe_for(self.registry,source,[('TR_CORE_core_rolling_sum',{'w':2})])
        self.assertEqual(final_value(self.run_recipe(source,recipe)),5)
        source['observations'].pop(1)
        with self.assertRaisesRegex(InputError,'MISSING_PERIOD'):self.run_recipe(source,recipe)
        source=fixture(self.registry,[1],frequency='intraday');source['cadence']['interval_seconds']='60'
        recipe=recipe_for(self.registry,source,[('TR_BASE_level_raw',{})])
        with self.assertRaisesRegex(InputError,'UTC timestamp'):self.run_recipe(source,recipe)

    def test_month_ends_leap_day_and_no_business_calendar_inference(self):
        source=fixture(self.registry,[1,2,3],times=['2020-01-31','2020-02-29','2020-03-31'],frequency='monthly')
        recipe=recipe_for(self.registry,source,[('TR_CORE_core_rolling_sum',{'w':2})])
        self.assertEqual(final_value(self.run_recipe(source,recipe)),5)
        source['observations'][1]['reference_time']='2020-02-28'
        with self.assertRaisesRegex(InputError,'MISSING_PERIOD'):self.run_recipe(source,recipe)

    def test_future_reference_and_ambiguous_event_anchors_reject_or_stay_unavailable(self):
        source=fixture(self.registry,[1]);source['observations'][0]['reference_time']='2020-01-02';source.pop('release_events')
        recipe=recipe_for(self.registry,source,[('TR_BASE_level_raw',{})])
        result=self.run_recipe(source,recipe,['2020-01-01'])
        self.assertEqual(result['execution']['status'],'no_valid_output')
        source=fixture(self.registry,[1,2]);source['release_events'][1]['available_at']='2020-01-01'
        with self.assertRaises(InputError):self.run_recipe(source,recipe)

    def test_composition_rejects_mislabeled_derived_root(self):
        source=fixture(self.registry,[1,2,3]);recipe=recipe_for(self.registry,source,[('TR_BASE_level_raw',{})])
        output=self.run_recipe(source,recipe)
        with self.assertRaisesRegex(InputError,'Derived roots'):self.run_recipe(output,recipe)


if __name__=='__main__':unittest.main()
