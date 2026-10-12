"""Read-only Feature/Scope resolution over isolated synthetic stored outputs.

Catalog and Scope membership boundaries are supplied as fixed synthetic fixtures;
the existing recipe validator, immutable Feature records, Signal projections and
independent materialization reader remain real. No production observations enter
these tests and no selection path is permitted to call a storage writer.
"""
from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from data.alfred_onboarding import Store
from data.feature_store import FeatureStore, materialization_path, record_path
from data.feature_resolution import resolve_feature_scope
from data.fx_feature_recipes import build_fx_feature, get_fx_policy
from data.fx_records import make_record
from data.reusable_features import _definition, _project_legacy, ReusableRecipeNotFound
from data.transformations.fx import INSTRUMENTS
from data.transformations.identity import reference
from data.transformations.registry import Registry
from test_feature_store import _copy_metadata_closure
import test_fx_feature_store as fixture_module

PROJECT=fixture_module.PROJECT


class FeatureScopeResolutionTests(unittest.TestCase):
    def setUp(self):
        self.fx=fixture_module.FXFeatureStoreTests(methodName='runTest');self.fx.setUp()
        self.root=self.fx.root;self.store=self.fx.store
        # The shared publisher fixture predates the reusable input profile.
        # Add a distinct synthetic profile-bearing view, preserving its old
        # records, so full reusable source compatibility is exercised here.
        dataset=self.store.install_record(make_record('dataset_definition',{'kind':'fx_constructed_dataset','profile':'fx_price.1.0.0',
            'instrument_id':'EURUSD','source_metadata':self.fx.meta},'Synthetic EURUSD reusable input'))
        self.fx.view=self.store.install_record(make_record('source_view_definition',{'kind':'fx_constructed_view','profile':'fx_price.1.0.0',
            'dataset':dataset,'source_metadata':self.fx.meta}))
        body=deepcopy(self.fx.snapshot_record['body']);body.update(profile='fx_price.1.0.0',definition=self.fx.view)
        self.fx.snapshot_record=make_record('snapshot_manifest',body)
        self.fx.snapshot=self.store.install_record(self.fx.snapshot_record)
        _copy_metadata_closure(self.root,[Registry(PROJECT).operator('TR_BASE_momentum_skip_diff')])
        self.fx.feature=self.fx.build_recipe('TR_BASE_momentum_skip_diff',{'k':21,'s':5})
        unmaterialized=self.fx.build_recipe('TR_BASE_vol_downside',{'basis':'log','w':5})
        registry=Registry(self.root);policy=get_fx_policy(self.root)
        self.recipes={};self.bindings={};self.current=[];self.snapshots={}
        variants={}
        for name,feature in [('momentum',self.fx.feature),('unmaterialized',unmaterialized)]:
            step=feature['body']['recipe']['steps'][-1]
            variant={'operator':step['operator'],'parameters':step['parameters'],'grid_policy':step['grid_policy'],
                'mode':'log_first' if len(feature['body']['recipe']['steps'])==2 else 'internal_log_basis',
                'parameter_frequency':'daily'}
            variants[name]=variant
            recipe=_definition(registry,policy,variant);self.recipes[name]=recipe;self.bindings[recipe['id']]=[]
        for symbol in sorted(INSTRUMENTS):
            if symbol=='EURUSD':snapshot=self.fx.snapshot_record
            else:
                meta=dict(self.fx.meta,base_currency=symbol[:3],quote_currency=symbol[3:],unit=symbol[3:]+'_per_'+symbol[:3])
                dataset=self.store.install_record(make_record('dataset_definition',{'kind':'fx_constructed_dataset','profile':'fx_price.1.0.0',
                    'instrument_id':symbol,'source_metadata':meta},'Synthetic '+symbol))
                view=self.store.install_record(make_record('source_view_definition',{'kind':'fx_constructed_view','profile':'fx_price.1.0.0',
                    'dataset':dataset,'source_metadata':meta}))
                snapshot=make_record('snapshot_manifest',{'kind':'fx_constructed_prices','profile':'fx_price.1.0.0',
                    'instrument_id':symbol,'economic_id':'FX_'+symbol[:3]+'_'+symbol[3:],
                    'definition':view,'source_metadata':meta})
                self.store.install_record(snapshot)
            self.snapshots[symbol]=snapshot
            instrument={'instrument_id':symbol,'price_snapshot':reference(snapshot)}
            self.current.append(instrument)
            for name,variant in variants.items():
                feature=build_fx_feature(self.root,instrument,variant,registry=registry,evaluation_policy=policy)
                self.store.install_record(feature)
                self.bindings[self.recipes[name]['id']].append({'configuration_id':'FXCONFIG_'+'1'*64,'instrument_id':symbol,
                    'feature':reference(feature),'price_snapshot':reference(snapshot),'source_view':snapshot['body']['definition']})
        config={'return_policy':self.fx.batch,'knowledge_cutoff':'2024-05-02'}
        (self.root/'config/fx_retrospective_completion.json').write_text(json.dumps(config))
        self.config=config
        self.unavailable_source=None
        self.patches=[patch('data.reusable_features.load_reusable_recipe',side_effect=self.load_recipe),
            patch('data.reusable_features.legacy_bindings_for_recipe',side_effect=self.load_bindings),
            patch('data.reusable_features.legacy_recipe_projector',side_effect=self.projector),
            patch('data.feature_resolution.resolve_scope',side_effect=self.load_scope),
            patch('data.feature_resolution.list_instruments',side_effect=lambda root:deepcopy(self.current)),
            patch('data.feature_resolution._price_snapshot',side_effect=self.current_snapshot)]
        for replacement in self.patches:replacement.start()

    def tearDown(self):
        for replacement in reversed(self.patches):replacement.stop()
        self.fx.tearDown()

    def load_recipe(self,root,identifier,version):
        found=next((record for record in self.recipes.values() if record['id']==identifier and version=='1.0.0'),None)
        if found is None:raise ReusableRecipeNotFound('Unknown synthetic recipe')
        return deepcopy(found)

    def load_bindings(self,root,binding,*,verify_features=True):
        self.assertFalse(verify_features)
        return deepcopy(self.bindings[binding['id']])

    def projector(self,root,recipe):
        # Supply the fixture's approved catalog set, retaining the actual full
        # per-member canonical/source/unit projection validation.
        registry=Registry(root);policy=get_fx_policy(root);store=FeatureStore(root)
        return lambda feature:_project_legacy(store,feature,registry,policy,{recipe['id']:recipe})

    def load_scope(self,root,identifier,version):
        members=sorted(INSTRUMENTS) if identifier=='FTMO_UNIVERSE' else [identifier]
        return {'id':identifier,'version':version,'display_name':identifier,'reference':{'id':identifier,'version':version,'content_sha256':'a'*64},
            'membership_snapshot':{'id':'SNAPSHOT_'+'b'*64,'version':'1.0.0','content_sha256':'c'*64},
            'member_count':len(members),'members':members}

    def current_snapshot(self,store,binding,policy,*,verify_rows=False):
        self.assertFalse(verify_rows)
        snapshot=store.resolve(binding)
        if snapshot['body']['instrument_id']==self.unavailable_source:
            raise ValueError('Synthetic unavailable source metadata')
        return snapshot,None

    def resolve(self,recipe='momentum',scope='FTMO_UNIVERSE'):
        return resolve_feature_scope(self.root,self.recipes[recipe]['id'],scope,'1.0.0')

    def materialize(self):
        return self.fx.prepare(start=self.fx.days[16],end=self.fx.days[79])

    def member(self,result,symbol='EURUSD'):
        return next(row for row in result['members'] if row['instrument_id']==symbol)

    def test_one_of_43_is_materialized_and_actual_period_is_preserved(self):
        saved=self.materialize();result=self.resolve()
        self.assertEqual(result['member_count'],43)
        self.assertEqual(result['summary'],{'materialized_member_count':1,'missing_member_count':42,'blocked_member_count':0})
        member=self.member(result);output=member['materializations'][0]
        self.assertEqual(output['reference'],saved['materialization']);self.assertEqual(output['row_count'],64)
        self.assertEqual(output['coverage']['reference_start'],self.fx.days[16])
        self.assertEqual(output['coverage']['reference_end'],self.fx.days[79])
        self.assertEqual(output['knowledge_cutoff'],'2024-05-02')
        self.assertEqual(result['recipe']['kind'],'reusable_fx_recipe')
        self.assertEqual(member['readiness']['historical_replay']['decision'],'blocked')
        self.assertEqual(result['preparation_context']['output_period_requested'],None)
        self.assertTrue(all(row['preparation_binding']['period_required'] for row in result['members']))
        self.assertEqual(member['preparation_binding']['batch_policy'],self.fx.batch)

    def test_unmaterialized_recipe_stays_zero_of_43(self):
        self.materialize();result=self.resolve('unmaterialized')
        self.assertEqual(result['summary'],{'materialized_member_count':0,'missing_member_count':43,'blocked_member_count':0})
        self.assertTrue(all(not row['materializations'] for row in result['members']))
        self.assertTrue(all(row['preparation_binding'] is not None for row in result['members']))

    def test_scope_change_keeps_recipe_identity_and_no_writes_are_allowed(self):
        self.materialize();before={str(path.relative_to(self.root)):path.read_bytes() for path in self.root.rglob('*') if path.is_file()}
        with (patch.object(Store,'install',side_effect=AssertionError('Selection attempted a write')),
              patch.object(Store,'blob',side_effect=AssertionError('Selection attempted a payload write'))):
            universe=self.resolve();single=self.resolve(scope='EURUSD');empty=self.resolve(scope='AUDUSD')
        after={str(path.relative_to(self.root)):path.read_bytes() for path in self.root.rglob('*') if path.is_file()}
        self.assertEqual(before,after)
        self.assertEqual(universe['recipe']['reference'],single['recipe']['reference'])
        self.assertEqual(single['recipe']['reference'],empty['recipe']['reference'])
        self.assertEqual(single['summary']['materialized_member_count'],1)
        self.assertEqual(empty['summary']['materialized_member_count'],0)
        self.assertTrue(universe['selection_read_only']);self.assertFalse(universe['preparation_performed'])

    def test_changed_current_source_keeps_stale_output_explicit(self):
        self.materialize()
        changed=deepcopy(self.fx.snapshot_record);changed['body']['fixture_capture']='new_capture'
        changed=make_record('snapshot_manifest',changed['body']);binding=self.store.install_record(changed)
        next(row for row in self.current if row['instrument_id']=='EURUSD')['price_snapshot']=binding
        result=self.resolve();member=self.member(result)
        self.assertEqual(member['state'],'blocked');self.assertEqual(member['reason_code'],'STALE_SOURCE_SNAPSHOT')
        self.assertEqual(result['summary'],{'materialized_member_count':0,'missing_member_count':42,'blocked_member_count':1})
        self.assertEqual(member['unavailable_materializations'][0]['code'],'STALE_SOURCE_SNAPSHOT')
        self.assertEqual(member['preparation_binding']['price_snapshot'],binding)

    def test_changed_source_view_does_not_offer_wrong_preparation_binding(self):
        symbol='AUDUSD';old=self.snapshots[symbol];body=deepcopy(old['body'])
        view=self.store.resolve(body['definition']);view['body']['fixture_new_view']='changed'
        view=make_record('source_view_definition',view['body']);body['definition']=self.store.install_record(view)
        snapshot=make_record('snapshot_manifest',body);binding=self.store.install_record(snapshot)
        next(row for row in self.current if row['instrument_id']==symbol)['price_snapshot']=binding
        result=self.resolve();member=self.member(result,symbol)
        self.assertEqual(member['state'],'blocked');self.assertIsNone(member['preparation_binding'])
        self.assertEqual(member['reason_code'],'STALE_SOURCE_VIEW')

    def test_corrupt_member_does_not_hide_healthy_members(self):
        self.materialize()
        binding=next(row for row in self.bindings[self.recipes['momentum']['id']] if row['instrument_id']=='AUDUSD')
        feature=self.store.resolve(binding['feature']);path=self.root/record_path(feature)
        path.write_text('{corrupt')
        result=self.resolve()
        self.assertEqual(result['summary'],{'materialized_member_count':1,'missing_member_count':41,'blocked_member_count':1})
        self.assertEqual(self.member(result,'AUDUSD')['state'],'blocked')
        self.assertEqual(self.member(result)['state'],'materialized')
        self.assertTrue(any(issue.get('instrument_id')=='AUDUSD' for issue in result['issues']))

    def test_corrupt_materialization_is_visible_and_never_counts_ready(self):
        saved=self.materialize();path=self.root/materialization_path(saved['materialization']['id'])
        path.write_text('{corrupt')
        result=self.resolve();member=self.member(result)
        self.assertEqual(member['state'],'blocked');self.assertFalse(member['materializations'])
        self.assertEqual(member['unavailable_materializations'][0]['code'],'UNAVAILABLE_MATERIALIZATION')
        self.assertEqual(result['summary']['missing_member_count'],42)

    def test_current_policy_and_cutoff_mismatch_are_not_reused(self):
        self.materialize();config=deepcopy(self.config);config['knowledge_cutoff']='2024-05-03'
        (self.root/'config/fx_retrospective_completion.json').write_text(json.dumps(config))
        result=self.resolve();self.assertEqual(self.member(result)['reason_code'],'STALE_KNOWLEDGE_CUTOFF')
        config=deepcopy(self.config);config['return_policy']['horizons']=[1]
        (self.root/'config/fx_retrospective_completion.json').write_text(json.dumps(config))
        result=self.resolve();self.assertEqual(result['summary']['blocked_member_count'],43)
        self.assertEqual(result['issues'][0]['code'],'PREPARATION_CONFIGURATION_UNAVAILABLE')

    def test_current_coverage_does_not_hide_an_older_incompatible_output(self):
        first=self.materialize()
        second=self.fx.prepare(start=self.fx.days[16],end=self.fx.days[79],knowledge_cutoff='2024-05-03')
        result=self.resolve();member=self.member(result)
        self.assertEqual(member['state'],'materialized')
        self.assertEqual([row['reference'] for row in member['materializations']],[first['materialization']])
        self.assertEqual(member['unavailable_materializations'][0]['reference'],second['materialization'])
        self.assertEqual(member['unavailable_materializations'][0]['code'],'STALE_KNOWLEDGE_CUTOFF')
        self.assertEqual(result['summary']['materialized_member_count'],1)

    def test_one_unavailable_current_source_does_not_hide_healthy_coverage(self):
        self.materialize();self.unavailable_source='AUDUSD'
        result=self.resolve()
        self.assertEqual(result['summary'],{'materialized_member_count':1,'missing_member_count':41,'blocked_member_count':1})
        self.assertEqual(self.member(result)['state'],'materialized')
        unavailable=self.member(result,'AUDUSD')
        self.assertEqual(unavailable['reason_code'],'CURRENT_PRICE_UNAVAILABLE')
        self.assertIsNone(unavailable['preparation_binding'])
        self.assertEqual(len(result['members']),43)

    def test_missing_current_config_keeps_recipe_registered_and_every_member_explicit(self):
        self.materialize();(self.root/'config/fx_retrospective_completion.json').unlink()
        before={str(path.relative_to(self.root)):path.read_bytes() for path in self.root.rglob('*') if path.is_file()}
        result=self.resolve()
        self.assertEqual(result['registration_state'],'registered')
        self.assertEqual(result['recipe']['reference'],reference(self.recipes['momentum']))
        self.assertEqual(result['summary'],{'materialized_member_count':0,'missing_member_count':0,'blocked_member_count':43})
        self.assertEqual(len(result['members']),43)
        self.assertTrue(all(member['reason_code']=='PREPARATION_CONFIGURATION_UNAVAILABLE' for member in result['members']))
        after={str(path.relative_to(self.root)):path.read_bytes() for path in self.root.rglob('*') if path.is_file()}
        self.assertEqual(before,after)


if __name__=='__main__':unittest.main()
