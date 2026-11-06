"""Projection parity over real persisted research metadata, without payload reads."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
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
