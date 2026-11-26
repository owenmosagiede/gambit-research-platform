"""Projection parity over real persisted research metadata, without payload reads."""
from copy import deepcopy
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
import zipfile
from unittest.mock import patch
from api.signal_summaries import list_signal_summaries
from data.feature_store import FeatureStore
from data.transformations.identity import reference
from research.contracts import ref
from research.store import ResearchStore
from read_model.projector import build
from read_model.query import page, detail
import test_signal_recipe_summaries as fixtures
from test_signal_recipe_summaries import fake_reference


class BranchProjectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.SignalRecipeSummaryTests.setUpClass()
        cls.addClassCleanup(fixtures.SignalRecipeSummaryTests.doClassCleanups)

    def setUp(self):
        self.fixture=fixtures.SignalRecipeSummaryTests('test_non_fx_summary_and_verified_detail_are_preserved')
        self.fixture.setUp(); self.addCleanup(self.fixture.doCleanups)
        self.root=self.fixture.root.resolve()
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.output=Path(self.temp.name).resolve()/'serving'

    def test_parity_partial_branch_deduplication_and_trial_metadata(self):
        self.fixture.record_research(horizons=(1,21),decision='rejected')
        self.fixture.record_research(horizons=(7,),decision='admitted',validation='FAILED')
        expected=list_signal_summaries(self.root)
        before={p:p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        with patch.object(ResearchStore,'verify_artifact',side_effect=AssertionError('payload read')):
            meta=build(self.root,self.output)
        self.assertEqual(meta['issue_count'],0)
        cards=page(self.output,'recipes')['items']
        self.assertEqual(len(cards),len(expected['entries']))
        self.assertEqual(cards[0]['research']['relationship_count'],3)
        rid=cards[0]['id']; actual=page(self.output,'branches',recipe=rid)['items']
        old=expected['entries'][0]['research']['relationships']
        for row in actual:
            previous=next(x for x in old if x['projection']==row['projection'])
            for key in previous:self.assertEqual(row[key],previous[key])
            self.assertFalse(row['p2_evaluation_ran']);self.assertFalse(row['research_stage_pass'])
            trial=detail(self.output,'trial',row['trial_results'][0]['id'])['record']
            self.assertEqual(ref(trial),row['trial_results'][0])
        self.assertEqual(before,{p:p.read_bytes() for p in self.root.rglob('*') if p.is_file()})

    def test_full_trial_metadata_is_not_retained_for_every_branch(self):
        import hashlib
        import tracemalloc
        store=ResearchStore(self.root); recipe=self.fixture.arguments['feature']
        body={'recipe':reference(recipe),'scope':fake_reference('SCOPE_','USD'),
              'mode':'CS','horizon':21,'expected_direction':'POSITIVE','target_family':'price_return'}
        relation=store.put('relationship',body,body)
        # Real immutable metadata, deliberately much larger than the compact
        # branch summaries. No numerical evaluation or artifact payloads.
        for branch in range(64):
            key={'relationship':ref(relation),'stage':'P1','horizon':21,
                 'research_spec':fake_reference('RSPEC_','spec'),'branch':branch}
            trial=store.put('trial',key,{'stage':'P1','admission':'rejected','execution_status':'completed',
                'metrics':{'diagnostic_fixture':'x'*(512*1024)},'sample':{},'artifact_manifests':[]})
            admission=store.put('admission',{'trial':ref(trial)},
                {'relationship':ref(relation),'trial':ref(trial),'decision':'rejected'})
            link={'relationship':ref(relation),'trial_results':[ref(trial)],
                  'admission_results':[ref(admission)],'validation_results':[]}
            store.put('link',link,link)
        expected=list_signal_summaries(self.root)['entries'][0]['research']['relationships']
        source_hashes=lambda:{str(p.relative_to(self.root)):hashlib.sha256(p.read_bytes()).hexdigest()
                              for p in self.root.rglob('*') if p.is_file()}
        before=source_hashes(); projections=[]
        for iteration in range(2):
            tracemalloc.start()
            try:
                with patch.object(ResearchStore,'verify_artifact',side_effect=AssertionError('payload read')):
                    meta=build(self.root,self.output)
                peak=tracemalloc.get_traced_memory()[1]
            finally:tracemalloc.stop()
            self.assertLess(peak,16*1024*1024,'Full trial bodies accumulated across branches')
            self.assertEqual(meta['issue_count'],0);projections.append(meta['projection_sha256'])
            if iteration:self.assertEqual(meta['extraction']['rebuilt'],{})
        self.assertEqual(projections[0],projections[1])
        rows=page(self.output,'branches',{'limit':'100'},recipe=recipe['id'])['items']
        self.assertEqual(len(rows),64)
        for row in rows:
            old=next(r for r in expected if r['projection']==row['projection'])
            for key in old:self.assertEqual(row[key],old[key])
            record=detail(self.output,'trial',row['trial_results'][0]['id'])['record']
            self.assertEqual(record,store.get('trial',record['id']))
        self.assertEqual(source_hashes(),before)

    def validated(self,direction='NEGATIVE',effect='-0.1',evaluated=True):
        store=ResearchStore(self.root);recipe=self.fixture.arguments['feature']
        body={'recipe':reference(recipe),'scope':fake_reference('SCOPE_','USD'), 'mode':'CS','horizon':21,
              'expected_direction':direction,'target_family':'price_return'}
        relation=store.put('relationship',body,body)
        p1key={'relationship':ref(relation),'stage':'P1','research_spec':fake_reference('RSPEC_','spec'),'horizon':21}
        p1=store.put('trial',p1key,{'stage':'P1','admission':'admitted','execution_status':'completed','metrics':{'primary_effect':effect},'sample':{},'artifact_manifests':[]})
        admission=store.put('admission',{'trial':ref(p1)},{'relationship':ref(relation),'trial':ref(p1),'decision':'admitted'})
        partial={'relationship':ref(relation),'trial_results':[ref(p1)],'admission_results':[ref(admission)],'validation_results':[]}
        store.put('link',partial,partial)
        p2key={**p1key,'stage':'P2','discovery_trial':ref(p1)}
        p2=store.put('trial',p2key,{'stage':'P2','decision':'VALIDATED','execution_status':'completed','sample':{'validation_data_accessed':evaluated},'metrics':{'primary_effect':effect},'artifact_manifests':[]})
        val=store.put('validation',{'discovery':ref(p1),'evaluation':ref(p2)},{'relationship':ref(relation),'discovery_trial':ref(p1),'evaluation_trial':ref(p2),'decision':'VALIDATED'})
        full={'relationship':ref(relation),'trial_results':[ref(p1),ref(p2)],'admission_results':[ref(admission)],'validation_results':[ref(val)]}
        store.put('link',full,full)
        return relation

    def test_negative_and_positive_passes_require_real_matching_evaluations(self):
        self.validated();self.validated('POSITIVE','0.1')
        meta=build(self.root,self.output)
        self.assertEqual(meta['issue_count'],0)
        card=page(self.output,'recipes')['items'][0]
        self.assertEqual(card['research']['branch_count'],2) # partial links superseded
        self.assertEqual(card['research']['research_stage_pass_count'],2)
        rows=page(self.output,'branches',recipe=card['id'])['items']
        self.assertEqual({r['expected_direction'] for r in rows},{'POSITIVE','NEGATIVE'})
        self.assertTrue(all(r['p2_evaluation_ran'] for r in rows))

    def test_bad_pass_does_not_disappear_into_a_success_count(self):
        self.validated(effect='0.1') # contradicts NEGATIVE discovery
        meta=build(self.root,self.output)
        self.assertEqual(meta['issue_count'],1)
        card=page(self.output,'recipes')['items'][0]
        self.assertEqual(card['research']['research_stage_pass_count'],0)
        self.assertEqual(card['research']['p2_counts'],{'not_run':1})
        self.assertFalse(page(self.output,'recipes')['freshness']['complete'])

    def test_metadata_append_is_incremental_and_unrelated_payload_not_scanned(self):
        self.fixture.record_research(horizons=(21,)); build(self.root,self.output)
        (self.root/'storage/payloads/irrelevant').write_text('not research metadata')
        second=build(self.root,self.output)
        self.assertEqual(second['extraction']['rebuilt'],{})
        self.fixture.record_research(horizons=(7,))
        third=build(self.root,self.output)
        self.assertEqual(third['extraction']['rebuilt']['branch'],1)
        self.assertEqual(page(self.output,'recipes')['items'][0]['research']['relationship_count'],2)


class MacroRecipeGroupTests(unittest.TestCase):
    def setUp(self):
        from data import panel_import as panels
        from test_panel_import import fixture, CAP
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name).resolve(); self.root = base/'source'; self.root.mkdir()
        self.output = base/'serving'; folder = base/'macro'
        fixture(folder, 'macro')
        with sqlite3.connect(folder/'panels.sqlite') as db:
            db.executescript("""
                INSERT INTO currencies VALUES(2,'EUR'),(3,'AUD');
                INSERT INTO features VALUES(1,'different_inflation_gap','C06','yoy','Inflation differential');
                INSERT INTO country_features SELECT mode_id,asof_id,feature_id,2,
                    candidate_value,model_value,period_ordinal,frequency,lineage_id,missing_mask,blocker_mask,warning_mask FROM country_features WHERE currency_id=0;
                INSERT INTO country_features SELECT mode_id,asof_id,feature_id,3,
                    candidate_value,model_value,period_ordinal,frequency,lineage_id,missing_mask,blocker_mask,warning_mask FROM country_features WHERE currency_id=1;
                INSERT INTO country_features SELECT mode_id,asof_id,1,currency_id,
                    candidate_value,model_value,period_ordinal,frequency,lineage_id,missing_mask,blocker_mask,warning_mask FROM country_features;
                INSERT INTO pair_features_data SELECT mode_id,asof_id,feature_id,0,2,
                    candidate_value,model_value,missing_mask,blocker_mask,warning_mask FROM pair_features_data;
                INSERT INTO pair_features_data SELECT mode_id,asof_id,feature_id,3,1,
                    candidate_value,model_value,missing_mask,blocker_mask,warning_mask FROM pair_features_data WHERE quote_id=1;
                INSERT INTO pair_features_data SELECT mode_id,asof_id,1,base_id,quote_id,
                    candidate_value,model_value,missing_mask,blocker_mask,warning_mask FROM pair_features_data;
                INSERT INTO modes VALUES(2,'retrospective');
                INSERT INTO country_features SELECT 2,asof_id,feature_id,currency_id,
                    candidate_value,model_value,period_ordinal,frequency,lineage_id,missing_mask,blocker_mask,warning_mask FROM country_features WHERE mode_id=0;
                INSERT INTO pair_features_data SELECT 2,asof_id,feature_id,base_id,quote_id,
                    candidate_value,model_value,missing_mask,blocker_mask,warning_mask FROM pair_features_data WHERE mode_id=0;
            """)
        archive = folder.with_suffix('.zip')
        with zipfile.ZipFile(archive, 'w') as bundle:
            for p in folder.iterdir(): bundle.write(p,folder.name+'/'+p.name)
        plan = panels.make_plan([panels.package_plan(folder,'macro',archive)])
        with patch.dict(os.environ, GAMBIT_ISOLATED_TEST='1'):
            panels.install(self.root,plan,plan['plan_sha256'],isolated=True)
        self.features = [json.loads(p.read_text()) for p in (self.root/'definitions/features').glob('*/*.json')]

    def feature(self, pair='JPYUSD', field='inflation_gap', layer='archive'):
        return next(f for f in self.features if (p:=f['body']['projection'])['pair']==pair and p['field']==field and p['layer']==layer)

    def record(self, feature=None, pair='USDJPY', target='price_return', p1='rejected', p2=None, horizon=21):
        feature = feature or self.feature(); store = ResearchStore(self.root)
        body = {'recipe':reference(feature),'scope':dict(fake_reference('SCOPE_',pair),id=pair),
                'mode':'TS','horizon':horizon,'target_family':target,'expected_direction':'POSITIVE'}
        rel = store.put('relationship',body,body)
        key = {'relationship':ref(rel),'stage':'P1','horizon':horizon,'research_spec':fake_reference('RSPEC_','macro'),
               'period':{'start_inclusive':'2010-01-01','end_exclusive':'2020-01-01'}}
        discovery = store.put('trial',key,{'stage':'P1','admission':p1,'execution_status':'completed',
                              'metrics':{'primary_effect':'0.1'},'sample':{},'artifact_manifests':[]})
        admission = store.put('admission',{'trial':ref(discovery)},
                              {'relationship':ref(rel),'trial':ref(discovery),'decision':p1})
        trials = [ref(discovery)]; validations = []
        if p2:
            evaluation = store.put('trial',{**key,'stage':'P2','discovery_trial':ref(discovery),
                'period':{'start_inclusive':'2020-01-01','end_exclusive':'2022-01-01'}},
                {'stage':'P2','decision':p2,'execution_status':'completed','metrics':{'primary_effect':'0.1'},
                 'sample':{'validation_data_accessed':True},'artifact_manifests':[]})
            trials.append(ref(evaluation))
            validations.append(ref(store.put('validation',{'discovery':ref(discovery),'evaluation':ref(evaluation)},
                {'relationship':ref(rel),'discovery_trial':ref(discovery),'evaluation_trial':ref(evaluation),'decision':p2})))
        link = {'relationship':ref(rel),'trial_results':trials,'admission_results':[ref(admission)],'validation_results':validations}
        store.put('link',link,link)
        return rel

    def build(self):
        with patch('data.panel_import.read',side_effect=AssertionError('Metadata grouping decoded observations')):
            result = build(self.root,self.output)
        self.assertEqual(result['issue_count'],0)
        return page(self.output,'recipes')['items']

    def test_macro_pairs_share_one_card_with_exact_targets_and_reverse_input_preserved(self):
        self.record(p1='admitted',p2='VALIDATED')
        self.record(target='total_return',p1='admitted',p2='FAILED')
        self.record(self.feature('JPYEUR'),pair='EURJPY',p1='unresolved')
        self.record(self.feature('AUDUSD'),pair='AUDUSD')
        before = {p:p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        cards = self.build(); self.assertEqual(len(cards),1)
        card = cards[0]; self.assertEqual(card['name'],'Inflation differential [archive]')
        self.assertEqual(card['kind'],'macro_recipe_group'); self.assertTrue(card['id'].startswith('MACRO_FEATURE_'))
        self.assertNotIn('recipe',card)  # Display group never impersonates a scientific definition.
        self.assertEqual(card['pair_count'],3); self.assertEqual(card['research']['relationship_count'],4)
        self.assertEqual(card['research']['research_stage_pass_count'],1)
        pairs = {p['pair']:p for p in card['pairs']}
        self.assertEqual(pairs['USDJPY']['p2_counts'],{'FAILED':1,'VALIDATED':1})
        self.assertEqual(pairs['EURJPY']['p1_counts'],{'unresolved':1})
        self.assertEqual(pairs['USDJPY']['inputs'],[{'feature':reference(self.feature()),'source_pair':'JPYUSD'}])
        rows = page(self.output,'branches',{'scope':'USDJPY'},recipe=card['id'])['items']
        self.assertEqual(len(rows),2); self.assertEqual({r['target_family'] for r in rows},{'price_return','total_return'})
        for row in rows:
            self.assertEqual(row['recipe'],reference(self.feature()))
            self.assertEqual(detail(self.output,'relationship',row['relationship']['id'])['record']['body']['recipe'],row['recipe'])
        self.assertEqual(before,{p:p.read_bytes() for p in self.root.rglob('*') if p.is_file()})

    def test_identical_titles_different_fields_and_history_layers_remain_separate(self):
        self.record()
        self.record(self.feature(field='different_inflation_gap'))
        self.record(self.feature(layer='retrospective'))
        cards = self.build(); self.assertEqual(len(cards),3)
        self.assertEqual(sum(c['name']=='Inflation differential [archive]' for c in cards),2)
        self.assertEqual(len({c['id'] for c in cards}),3)

    def test_new_pair_updates_same_group_and_pair_cursor_remains_pinned(self):
        self.record(); first = self.build()[0]
        self.record(horizon=63); self.record(self.feature('AUDUSD'),pair='AUDUSD')
        second = self.build()[0]
        self.assertEqual(first['id'],second['id']); self.assertEqual(second['pair_count'],2)
        a = page(self.output,'branches',{'scope':'USDJPY','limit':'1'},recipe=second['id'])
        b = page(self.output,'branches',{'scope':'USDJPY','limit':'1','cursor':a['next_cursor']},recipe=second['id'])
        self.assertEqual(a['total'],2); self.assertEqual(b['total'],2)
        self.assertEqual({r['horizon'] for r in a['items']+b['items']},{21,63})
        from read_model.query import InvalidQuery
        with self.assertRaises(InvalidQuery):
            page(self.output,'branches',{'scope':'AUDUSD','limit':'1','cursor':a['next_cursor']},recipe=second['id'])

    def test_group_branch_http_route_uses_pair_filter_without_source_scan(self):
        from api.application import ApplicationRoutes
        from api.catalog_cache import CatalogCache
        self.record(); card = self.build()[0]
        route = ApplicationRoutes(self.root,None,CatalogCache(),'GET',
            '/api/read-model/v1/recipes/'+card['id']+'/branches?scope=USDJPY',read_model_dir=self.output)
        with patch('data.feature_store.FeatureStore',side_effect=AssertionError('Request scanned source')):
            route.read(False)
        self.assertEqual(route.response[0],200)
        self.assertEqual(json.loads(route.response[1])['total'],1)
