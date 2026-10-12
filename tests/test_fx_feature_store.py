"""Bounded FX Feature persistence on isolated synthetic captured price states.

The existing FX source verifier is separately covered by test_fx_targets. Here
only that read-only source boundary is replaced with an exact synthetic state;
the real recipe builder/validator, numeric kernels, immutable store, lineage,
publication and independent Feature reader are exercised together.
"""
from copy import deepcopy
from datetime import date, timedelta
import json
import math
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from data.feature_store import FeatureStore, PublicationError, retrieve_signal, materialization_path
from data.fx_feature_store import prepare_fx_feature, read_fx_materialization, _dates
from data.fx_feature_recipes import _policy_records, build_fx_feature, _typed_parameters
from data.fx_records import make_record
from data.transformations.identity import reference, digest, canonical_bytes
from data.transformations.registry import Registry
from test_feature_store import _copy_metadata_closure
from test_fx_targets import approve

PROJECT=Path(__file__).resolve().parents[1]


class FXFeatureStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        shutil.copytree(PROJECT/'specs/schemas',self.root/'specs/schemas')
        registry=Registry(PROJECT)
        _copy_metadata_closure(self.root,[registry.operator(name) for name in
            ('TR_BASE_level_log','TR_BASE_change_diff','TR_BASE_vol_downside','TR_BASE_distribution_skew')]+
            [registry.get_policy(name) for name in ('POL_TRANSFORM_EXECUTION','POL_TRANSFORM_HISTORY')])
        self.store=FeatureStore(self.root)
        self.batch=approve(self.store,{'approval_state':'approved','representation':'simple','horizons':[1,7,21,63,252],
            'calendar_id':'RESEARCH_WEEKDAYS','calendar_version':'1.0.0','clock':'scheduled_bars',
            'entry':{'rule':'anchor_mark','delay':{'amount':0,'unit':'calendar_days'}},
            'endpoint':{'rule':'exact','tolerance':{'amount':0,'unit':'calendar_days'}}})
        (self.root/'config').mkdir()
        (self.root/'config/fx_retrospective_completion.json').write_text(json.dumps({'return_policy':self.batch}))
        policy,evidence,payload,_=_policy_records(self.root,'ISOLATED SYNTHETIC TEST APPROVAL ONLY.',{'fixture':True})
        self.store.io.blob(payload,'json','fixture_policy',None)
        self.store.install_record(evidence);self.store.install_record(policy)
        self.meta={'unit':'USD_per_EUR','base_currency':'EUR','quote_currency':'USD','price_field':'close','price_basis':'unknown'}
        dataset=self.install('dataset_definition',{'kind':'fx_constructed_dataset','instrument_id':'EURUSD',
            'source_metadata':self.meta},'Synthetic EURUSD')
        self.view=self.install('source_view_definition',{'kind':'fx_constructed_view','dataset':dataset,
            'source_metadata':self.meta})
        self.days=list(_dates('2024-01-02','2024-04-30'))[:80]
        self.prices=[]
        for index,day in enumerate(self.days):
            if index==17: continue # Missing weekday stays a gap, not a shorter clock.
            row={'reference_time':day,'value':str(100+3*math.sin(index*.3)+index*.1),'status':'valid',
                'reason_code':None,'available_at':None,'input_dependencies':[{'original_ingested_at':'2024-05-01T12:00:00Z'}]}
            row['id']='FXPRICE_'+digest(row);self.prices.append(row)
        self.snapshot_record=make_record('snapshot_manifest',{'kind':'fx_constructed_prices','instrument_id':'EURUSD',
            'economic_id':'FX_EUR_USD','definition':self.view,'source_metadata':self.meta})
        self.snapshot=self.store.install_record(self.snapshot_record)
        self.source_mock=patch('data.fx_feature_store._price_snapshot',side_effect=self.load_price)
        self.source_mock.start()
        self.feature=self.build_recipe('TR_BASE_change_diff',{'k':5})

    def tearDown(self):
        self.source_mock.stop();self.temp.cleanup()

    def install(self,kind,body,name=None):
        return self.store.install_record(make_record(kind,body,name))

    def load_price(self,store,binding,policy):
        self.assertEqual(binding,self.snapshot)
        return store.resolve(binding),deepcopy(self.prices)

    def build_recipe(self,identifier,parameters):
        registry=Registry(self.root);entry=registry.operator(identifier)
        variant={'operator':reference(entry),'mode':'internal_log_basis' if 'basis' in parameters else 'log_first',
            'parameters':_typed_parameters(entry,parameters),'grid_policy':entry['body']['execution_contract']['grid_profile'],
            'parameter_frequency':'daily'}
        feature=build_fx_feature(self.root,{'instrument_id':'EURUSD','price_snapshot':self.snapshot},variant,registry=registry)
        self.store.install_record(feature)
        return feature

    def prepare(self,feature=None,**kwargs):
        defaults={'price_snapshot':self.snapshot,'batch_policy':self.batch,'knowledge_cutoff':'2024-05-02',
            'start':self.days[0],'end':self.days[-1]}
        defaults.update(kwargs)
        return prepare_fx_feature(self.root,reference(feature or self.feature),**defaults)

    def test_block_lineage_hashes_invariant_inputs_once_and_preserves_references(self):
        from data import fx_feature_store as fx
        from data.fx_feature_contracts import lineage_record
        input_record, dates, prices = fx._scheduled_input(self.snapshot_record, self.prices, '2024-05-01', self.days[-1])
        compiled = fx._compile(self.root, self.feature, self.snapshot_record, self.batch)
        points = fx._calculate(compiled, dates, prices)
        bindings = fx._bindings(self.feature['body']['recipe'], self.batch)
        implementation = {'id': 'IMPLEMENTATION_' + 'a' * 64, 'version': '1.0.0', 'content_sha256': 'b' * 64}
        with patch.object(fx, 'reference', wraps=reference) as hashed:
            rows, lineages = fx._rows(self.feature, 'MATERIALIZATION_' + 'c' * 64, input_record,
                dates, points, dates[10], '2024-05-01', implementation, bindings)
        self.assertEqual(sum(call.args[0] is input_record for call in hashed.call_args_list), 1)
        self.assertEqual(sum(call.args[0] is self.feature for call in hashed.call_args_list), 1)
        for index, (row, lineage) in enumerate(zip(rows, lineages), start=10):
            expected = lineage_record('fx_feature_lineage_record', {
                'profile': fx.PROFILE, 'scheduled_input': reference(input_record),
                'prefix_count': index + 1, 'reference_time': dates[index],
                'evaluation_cutoff': '2024-05-01', 'operation': reference(self.feature),
                'implementation': implementation, 'policy_bindings': bindings,
                'dependency_semantics': 'causal_prefix_audit_superset'})
            self.assertEqual(canonical_bytes(lineage), canonical_bytes(expected))
            self.assertEqual(row['lineage'], reference(expected))
            self.assertEqual(row['value'], points[index]['value'])
        # Returned rows keep independent reference dictionaries as before.
        self.assertIsNot(lineages[0]['body']['scheduled_input'], lineages[1]['body']['scheduled_input'])

    def test_log_difference_numbers_weekday_gaps_and_unknown_availability(self):
        saved=self.prepare();item=read_fx_materialization(self.root,saved['materialization']['id'])
        rows=item['observations'];prices={row['reference_time']:float(row['value']) for row in self.prices}
        self.assertEqual(len(rows),80)
        for index in (10,30,79):
            self.assertAlmostEqual(float(rows[index]['value']),math.log(prices[self.days[index]])-math.log(prices[self.days[index-5]]),places=12)
        self.assertEqual((rows[17]['value'],rows[17]['reason_code']),(None,'MISSING_PERIOD'))
        self.assertEqual((rows[22]['value'],rows[22]['reason_code']),(None,'MISSING_PERIOD'))
        self.assertTrue(all(row['available_at'] is None and not row['historical_eligibility_certified'] for row in rows))
        self.assertEqual({row['evaluation_cutoff'] for row in rows},{'2024-05-02'})
        self.assertEqual(item['manifest']['readiness_capabilities']['historical_replay']['decision'],'blocked')

    def test_internal_log_basis_and_distribution_have_no_extra_difference(self):
        feature=self.build_recipe('TR_BASE_vol_downside',{'basis':'log','w':5})
        saved=self.prepare(feature,start=self.days[-1]);item=read_fx_materialization(self.root,saved['materialization']['id'])
        prices={row['reference_time']:float(row['value']) for row in self.prices}
        changes=[math.log(prices[self.days[i]]/prices[self.days[i-1]]) for i in range(75,80)]
        expected=math.sqrt(sum(min(value,0)**2 for value in changes)/5)
        self.assertAlmostEqual(float(item['observations'][0]['value']),expected,places=12)
        self.assertEqual(len(feature['body']['recipe']['steps']),1)
        feature=self.build_recipe('TR_BASE_distribution_skew',{'w':21})
        saved=self.prepare(feature,start=self.days[-1]);item=read_fx_materialization(self.root,saved['materialization']['id'])
        changes=[math.log(prices[self.days[i]]/prices[self.days[i-1]]) for i in range(59,80)]
        mean=sum(changes)/21;sd=math.sqrt(sum((v-mean)**2 for v in changes)/20)
        expected=21/(20*19)*sum(((v-mean)/sd)**3 for v in changes)
        self.assertAlmostEqual(float(item['observations'][0]['value']),expected,places=10)

    def test_bounded_output_retains_prior_warmup_and_exact_compact_lineage(self):
        saved=self.prepare(start=self.days[60],end=self.days[64])
        item=retrieve_signal(self.root,saved['signal_id'],saved['materialization']['id'])
        self.assertEqual(len(item['observations']),5)
        operand=next(iter(item['operands'].values()))['record']
        self.assertEqual(len(operand['body']['scheduled_inputs']),65)
        self.assertIsNone(operand['body']['scheduled_inputs'][17]['price_row_id'])
        lineage=self.store.resolve(item['observations'][0]['lineage'])
        self.assertEqual(lineage['body']['prefix_count'],61)
        self.assertEqual(lineage['body']['scheduled_input'],reference(operand))
        self.assertEqual(lineage['body']['operation'],reference(self.feature))
        self.assertEqual(item['materialization_state'],'materialized')
        self.assertEqual(item['scientific_state'],'untested')

    def test_repeat_reuses_and_registered_only_does_not_become_selectable(self):
        other=self.build_recipe('TR_BASE_vol_downside',{'basis':'log','w':5})
        first=self.prepare(start=self.days[60]);before={str(p.relative_to(self.root)):p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        second=self.prepare(start=self.days[60])
        self.assertTrue(second['reused']);self.assertEqual(first['materialization'],second['materialization'])
        after={str(p.relative_to(self.root)):p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(before,after)
        self.assertFalse((self.root/'storage/catalog/signal_library/entries'/other['body']['signal_id']).exists())

    def test_payload_tamper_and_self_consistent_numeric_tamper_are_rejected(self):
        saved=self.prepare(start=self.days[60]);mid=saved['materialization']['id']
        item=read_fx_materialization(self.root,mid);manifest=item['manifest'];rows=item['observations']
        rows[0]['value']='999';data=b''.join(canonical_bytes(row)+b'\n' for row in rows)
        manifest['partitions']=[self.store.io.blob(data,'jsonl','fx_feature_observations',len(rows))]
        manifest['semantic_content_sha256']=digest(rows)
        (self.root/materialization_path(mid)).write_bytes(canonical_bytes(manifest)+b'\n')
        with self.assertRaisesRegex(PublicationError,'do not reproduce'):read_fx_materialization(self.root,mid)

    def test_changed_source_or_lineage_is_detected(self):
        saved=self.prepare(start=self.days[60]);self.prices[0]['value']='99'
        with self.assertRaisesRegex(PublicationError,'Scheduled source lineage'):read_fx_materialization(self.root,saved['materialization']['id'])

    def test_incompatible_recipe_and_future_capture_fail_without_materialization(self):
        bad=deepcopy(self.feature);bad['body']['recipe']['steps'][0]['parameters']=[{'name':'k','unit':'observations','value':{'kind':'integer','value':'5'}}]
        from data.transformations.identity import make_feature_definition
        bad=make_feature_definition(bad['body']['recipe'],'Wrong log parameters');self.store.install_record(bad)
        with self.assertRaises(ValueError):self.prepare(bad)
        self.prices[0]['input_dependencies'][0]['original_ingested_at']='2025-01-01T00:00:00Z'
        with self.assertRaisesRegex(PublicationError,'not known'):self.prepare()
        self.assertEqual(list(self.root.glob('storage/catalog/feature_store/*/manifest.json')),[])

    def test_all_null_is_not_published_and_interruption_resumes(self):
        with self.assertRaisesRegex(PublicationError,'No valid'):self.prepare(end=self.days[3])
        self.assertEqual(list(self.root.glob('storage/catalog/signal_library/entries/SIGNAL_*')),[])
        with self.assertRaisesRegex(PublicationError,'interruption'):self.prepare(fail_at='payloads')
        self.assertEqual(list(self.root.glob('storage/catalog/feature_store/*/manifest.json')),[])
        self.assertEqual(list(self.root.glob('storage/catalog/signal_library/entries/SIGNAL_*')),[])
        self.assertFalse(self.prepare()['reused'])

    def test_verification_service_does_not_allow_unbounded_materialization(self):
        with self.assertRaisesRegex(PublicationError,'366 calendar days'):
            self.prepare(start='2023-01-01',end='2024-04-30')
        self.assertEqual(list(self.root.glob('storage/catalog/feature_store/*/manifest.json')),[])

    def test_preparation_must_retain_exact_recipe_approval_bindings(self):
        different=approve(self.store,dict(self.batch,horizons=[1]))
        with self.assertRaisesRegex(PublicationError,'recipe approval bindings'):
            self.prepare(batch_policy=different)

    def test_self_consistent_adversarial_recipes_cannot_change_execution_geometry(self):
        from data.fx_feature_recipes import validate_fx_recipe
        from data.transformations.identity import feature_id,signal_id
        mutations={
            'bypass_log':lambda r:r['steps'][-1].update(inputs=['source']),
            'output_intermediate':lambda r:r.update(output_node='log_price'),
            'second_source':lambda r:r['sources'].append({'alias':'other','source_view':self.view}),
            'emitted_history':lambda r:r.update(history_mode='emitted_history'),
            'bound_scope':lambda r:r.update(calculation_scope_requirement='bound_at_materialization',scope_policy=r['history_policy']),
            'interaction_phase':lambda r:r['steps'][0].update(phase='interaction'),
        }
        for name,mutate in mutations.items():
            with self.subTest(name=name):
                recipe=deepcopy(self.feature['body']['recipe']);mutate(recipe)
                # The wider canonical identity contract intentionally supports
                # more shapes than the bounded execution profile. Recompute
                # identity so rejection cannot merely be a stale-hash check.
                value={'schema_version':'0.2.0','record_type':'feature_definition','id':feature_id(recipe),
                    'version':'1.0.0','display_name':'Adversarial '+name,'body':{'signal_id':signal_id(recipe),'recipe':recipe}}
                with self.assertRaises(ValueError):validate_fx_recipe(self.root,value)

    def test_alias_renaming_cannot_create_duplicate_fx_recipe_variants(self):
        from data.fx_feature_recipes import validate_fx_recipe
        from data.transformations.identity import make_feature_definition
        recipe=deepcopy(self.feature['body']['recipe'])
        recipe['sources'][0]['alias']='renamed';recipe['steps'][0]['inputs']=['renamed']
        value=make_feature_definition(recipe,'Renamed duplicate')
        with self.assertRaises(ValueError):validate_fx_recipe(self.root,value)

    def test_new_output_period_reuses_parent_and_requires_explicit_materialization(self):
        first=self.prepare(start=self.days[50],end=self.days[54])
        second=self.prepare(start=self.days[55],end=self.days[59])
        self.assertEqual(first['feature'],second['feature']);self.assertEqual(first['signal_id'],second['signal_id'])
        self.assertNotEqual(first['materialization'],second['materialization'])
        with self.assertRaisesRegex(PublicationError,'explicit materialization'):
            retrieve_signal(self.root,first['signal_id'])
        self.assertEqual(len(retrieve_signal(self.root,first['signal_id'],first['materialization']['id'])['observations']),5)

    def test_weekend_source_row_does_not_change_approved_weekday_operands(self):
        row=deepcopy(self.prices[0]);row.update(reference_time='2024-01-06',value='9999')
        row['id']='FXPRICE_'+digest({k:v for k,v in row.items() if k!='id'})
        self.prices.append(row);self.prices.sort(key=lambda r:r['reference_time'])
        saved=self.prepare(start=self.days[5],end=self.days[5]);item=read_fx_materialization(self.root,saved['materialization']['id'])
        prices={r['reference_time']:float(r['value']) for r in self.prices}
        self.assertAlmostEqual(float(item['observations'][0]['value']),math.log(prices[self.days[5]])-math.log(prices[self.days[0]]),places=12)
        self.assertEqual(len(next(iter(item['operands'].values()))['record']['body']['scheduled_inputs']),6)


if __name__=='__main__':unittest.main()
