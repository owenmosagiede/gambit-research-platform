"""Currency orientation and persisted price replay in isolated provider fixtures."""
from copy import deepcopy
from decimal import Decimal
from pathlib import Path
import shutil
import tempfile
import unittest
from data.feature_store import FeatureStore
from data.fx_currency_catalog import publish_prices,resolve_prices
from data.transformations.identity import reference
from data.transformations import fx_currency as currency
from data.targets.fx import _price_snapshot
from test_fx_onboarding import build_fixture
from test_fx_targets import approve
from data.fx_onboarding import onboard

class CurrencyPriceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.temp.cleanup)
        cls.root,legacy,audit,_=build_fixture(Path(cls.temp.name))
        sources=onboard(cls.root,legacy,audit,migration_time='2026-10-09T10:00:00Z')['sources']
        cls.sources={s['symbol']:s['pit_snapshot'] for s in sources}
        cls.policy=approve(FeatureStore(cls.root),{'approval_state':'approved','representation':'simple','horizons':[1,7,21,63,252],
            'calendar_id':'RESEARCH_WEEKDAYS','calendar_version':'1.0.0','clock':'scheduled_bars',
            'entry':{'rule':'anchor_mark','delay':{'amount':0,'unit':'calendar_days'}},
            'endpoint':{'rule':'exact','tolerance':{'amount':0,'unit':'calendar_days'}}})
        cls.catalog=publish_prices(cls.root,cls.sources,cls.policy,'ISOLATED TEST: replace the old CS universes')
        _,cls.instruments=resolve_prices(cls.root,reference(cls.catalog),verify_rows=True)

    def test_all_seven_memberships_are_fixed(self):
        self.assertEqual(len(currency.CURRENCIES),19)
        self.assertEqual(len(self.instruments),126)
        for q in currency.REFERENCES:
            members=currency.members(q)
            self.assertEqual(len(members),18)
            self.assertEqual(members,sorted(members))
            self.assertNotIn(q+q,members)
            self.assertIn('NZD'+q,members)
            self.assertIn('CNH'+q,members)
            self.assertNotIn('CNY'+q,members)
        self.assertIn('MXNUSD',self.instruments)
        self.assertIn('NOKGBP',self.instruments)

    def test_reciprocal_and_cross_orientation(self):
        store=FeatureStore(self.root)
        def value(s):
            _,rows=_price_snapshot(store,self.instruments[s]['price_snapshot'],self.policy)
            return Decimal(rows[0]['value'])
        self.assertAlmostEqual(float(value('EURUSD')*value('USDEUR')),1)
        self.assertAlmostEqual(float(value('MXNEUR')),float(value('MXNUSD')/value('EURUSD')))
        self.assertAlmostEqual(float(value('NOKGBP')),float(value('NOKUSD')/value('GBPUSD')))

    def test_catalog_rerun_is_identical(self):
        again=publish_prices(self.root,self.sources,self.policy,'ISOLATED TEST: replace the old CS universes')
        self.assertEqual(again,self.catalog)

    def test_incomplete_sources_do_not_shrink_universe(self):
        with self.assertRaises(ValueError):publish_prices(self.root,{},self.policy,'test')

    def test_source_mismatch_is_rejected(self):
        bad=deepcopy(self.sources);bad['EUR/USD']=bad['GBP/USD']
        with self.assertRaises(ValueError):publish_prices(self.root,bad,self.policy,'test')

class CurrencyReleaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import json
        from data.fx_currency_release import stage
        from data.scopes import register_fx_scopes
        from test_scopes import metadata_fixture,WHEN
        from test_research_inputs import approved_profile
        cls.temp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.temp.cleanup)
        cls.root,legacy,audit,_=build_fixture(Path(cls.temp.name),days=('2020-01-02','2020-01-03','2020-01-06','2020-01-07','2020-01-08','2020-01-09','2020-01-10'))
        project=Path(__file__).resolve().parents[1]
        shutil.copytree(project/'definitions',cls.root/'definitions',dirs_exist_ok=True)
        shutil.rmtree(cls.root/'definitions/scopes')
        for path in (cls.root/'definitions/policies').glob('POLICY_FX_FIXED_RESEARCH_*'):shutil.rmtree(path)
        shutil.copytree(project/'storage',cls.root/'storage',dirs_exist_ok=True)
        sources=onboard(cls.root,legacy,audit,migration_time='2026-10-09T10:00:00Z')['sources']
        cls.sources={s['symbol']:s['pit_snapshot'] for s in sources}
        cls.policy=approve(FeatureStore(cls.root),{'approval_state':'approved','representation':'simple','horizons':[1,7,21,63,252],
            'calendar_id':'RESEARCH_WEEKDAYS','calendar_version':'1.0.0','clock':'scheduled_bars',
            'entry':{'rule':'anchor_mark','delay':{'amount':0,'unit':'calendar_days'}},
            'endpoint':{'rule':'exact','tolerance':{'amount':0,'unit':'calendar_days'}}})
        p=approved_profile();p['periods']={'P1':{'start_inclusive':'2020-01-02','end_exclusive':'2022-01-01'},
            'P2':{'start_inclusive':'2022-01-01','end_exclusive':'2023-01-01'}}
        p['target_selection']['knowledge_cutoff']='2026-10-09';p['exposure_classification']='previously_exposed'
        (cls.root/'config/research_execution.json').write_text(json.dumps(p))
        (cls.root/'config/fx_retrospective_completion.json').write_text(json.dumps({'knowledge_cutoff':'2026-10-09','return_policy':cls.policy}))
        metadata_fixture(cls.root);register_fx_scopes(cls.root,'isolated scopes',registered_at=WHEN)
        cls.release=stage(cls.root,cls.sources,cls.policy,'ISOLATED TEST: implement currency migration and delete legacy CS history')

    def test_complete_migration_and_frozen_inputs(self):
        from data.fx_currency_migration import plan,apply,check_staged_request,verify_applied
        from data.fx_currency_release import load_profile
        from data.scopes import list_scopes,resolve_scope
        from data.fx_currency_features import records
        from research.inputs import resolve_plan
        from research.feature_applications import resolve,ApplicationBlocked
        # Staging does not expose the seven new Scopes prematurely.
        self.assertEqual(list_scopes(self.root)['scope_count'],61)
        request={'source_snapshots':self.sources,'return_policy':self.policy}
        self.assertEqual(check_staged_request(self.root,reference(self.release),request),self.release)
        changed=deepcopy(request);changed['return_policy']['representation']='log'
        with self.assertRaisesRegex(ValueError,'frozen'):check_staged_request(self.root,reference(self.release),changed)
        manifest=plan(self.root,reference(self.release))
        self.assertEqual(manifest['blockers'],[])
        self.assertEqual(len(manifest['protected_ts']),86)
        apply(self.root,manifest,manifest['sha256'])
        verified=verify_applied(self.root,manifest)
        self.assertEqual(verified['active_ts_scopes'],43)
        self.assertEqual(verified['active_cs_scopes'],7)
        self.assertTrue(verified['sample_target_read'])
        result=list_scopes(self.root)
        self.assertEqual(result['issues'],[])
        self.assertEqual(result['scope_count'],50)
        self.assertEqual(sum(s['kind']=='universe' for s in result['scopes']),7)
        recipe=next(r for r in records(self.root).values() if r['body']['steps'][-1]['operator']['id']=='TR_BASE_change_diff'
            and r['body']['steps'][-1]['parameters']==[{'name':'k','unit':'observations','value':{'kind':'integer','value':'5'}}])
        selection={k:recipe[k] for k in ('id','version')}
        with self.assertRaises(ApplicationBlocked):resolve(self.root,selection,resolve_scope(self.root,'EURUSD','1.0.0'))
        intent={'feature':selection,'scope':{'id':'FX_CCY_VS_USD','version':'1.0.0'},'target_family':'price_return','expected_direction':'NEGATIVE'}
        frozen=resolve_plan(self.root,intent,load_profile(self.root))
        self.assertEqual(frozen['mode'],'CS');self.assertEqual(len(frozen['members']),18)
        self.assertEqual(frozen['scope']['reference_currency'],'USD')
        self.assertEqual(frozen['intent']['expected_direction'],'NEGATIVE')
        self.assertEqual(frozen['horizons'],[1,7,21,63,252])
        from research.feature_applications import validate_frozen
        damaged=deepcopy(frozen['scope']);damaged['reference_currency']='EUR'
        with self.assertRaises(ApplicationBlocked):validate_frozen(frozen['feature_application'],frozen['recipe'],damaged,'CS')
        from data.fx_feature_store import prepare_fx_feature,read_fx_materialization
        member=frozen['members'][0]
        saved=prepare_fx_feature(self.root,member['feature'],price_snapshot=member['price_snapshot'],
            batch_policy=frozen['batch_policy'],knowledge_cutoff=frozen['knowledge_cutoff'],start='2020-01-02',end='2020-01-10')
        output=read_fx_materialization(self.root,saved['materialization']['id'])
        self.assertEqual(output['manifest']['input_key']['source_snapshots'],[member['price_snapshot']])
        self.assertTrue(all(r['entity_id']==member['instrument_id'] for r in output['observations']))
        import math
        _,prices=_price_snapshot(FeatureStore(self.root),member['price_snapshot'],frozen['batch_policy'])
        self.assertAlmostEqual(float(output['observations'][-1]['value']),math.log(float(prices[-1]['value'])/float(prices[1]['value'])))
        self.assertTrue(apply(self.root,manifest,manifest['sha256'])['reused'])

    def test_momentum_catalog_preserves_inputs_without_numerical_replay(self):
        from unittest.mock import patch
        from data.fx_currency_features import build_momentum_catalog,records,bindings
        from data.fx_currency_catalog import activate,add
        from data.fx_currency_release import validate_release
        from data.fx_feature_recipes import MOMENTUM_CONFIGURATION_PROFILE
        from data.fx_records import make_record
        store=FeatureStore(self.root)
        original=store.resolve(self.release['body']['feature_catalog'])
        catalog=build_momentum_catalog(self.root,reference(original))
        self.assertEqual(catalog['body']['configuration_profile'],MOMENTUM_CONFIGURATION_PROFILE)
        self.assertEqual(len(catalog['body']['recipes']),53)
        self.assertEqual(len(catalog['body']['bindings']),6678)
        self.assertEqual(catalog['body']['price_catalog'],original['body']['price_catalog'])
        self.assertTrue(all(b in original['body']['bindings'] for b in catalog['body']['bindings']))
        store.install_record(catalog)
        body=deepcopy(self.release['body']);body['feature_catalog']=reference(catalog)
        release=add(store,'onboarding_evidence',body);activate(self.root,release)
        self.addCleanup(activate,self.root,self.release)
        with patch('data.fx_currency_release.read_materialization',side_effect=AssertionError('Bulk numerical replay forbidden in metadata mode')):
            validate_release(self.root,release,numerical=False)
        self.assertEqual(len(records(self.root)),53)
        first=catalog['body']['recipes'][0]['recipe']
        self.assertEqual(len(bindings(self.root,first)),126)
        self.assertEqual(release['body']['research_spec'],self.release['body']['research_spec'])
        bad_body=deepcopy(catalog['body']);bad_body['recipes'].pop()
        bad=make_record('onboarding_evidence',bad_body);store.install_record(bad)
        bad_release=add(store,'onboarding_evidence',dict(body,feature_catalog=reference(bad)))
        activate(self.root,bad_release)
        with self.assertRaisesRegex(ValueError,'Incomplete currency Feature family'):records(self.root)

class CurrencySemanticsTests(unittest.TestCase):
    def test_downside_is_recomputed_on_inverse_price_not_sign_flipped(self):
        from data.transformations.numeric import calculate
        prices=[10.,8.,12.,9.,13.]
        inverse=[1/p for p in prices]
        params={'w':4,'basis':'log'}
        downside=calculate('vol.downside',prices,params)[-1]['value']
        inverse_downside=calculate('vol.downside',inverse,params)[-1]['value']
        upside=calculate('vol.upside',prices,params)[-1]['value']
        self.assertAlmostEqual(inverse_downside,upside)
        self.assertNotAlmostEqual(inverse_downside,-downside)

    def test_simple_inverse_return_is_not_negative_forward_return(self):
        initial,final=10.,12.
        forward=final/initial-1
        inverse=(1/final)/(1/initial)-1
        self.assertAlmostEqual(inverse,-forward/(1+forward))
        self.assertNotAlmostEqual(inverse,-forward)
