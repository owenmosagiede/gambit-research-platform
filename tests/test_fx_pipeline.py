"""Real shared-store integration using explicitly isolated small source fixtures."""
from pathlib import Path
import tempfile
import unittest
from data.fx_onboarding import onboard
from data.fx_pipeline import register_and_construct,list_instruments
from data.feature_store import FeatureStore
from data.fx_records import read_rows
from data.transformations.fx import INSTRUMENTS,DIRECT,INVERSE,CROSS
from test_fx_onboarding import build_fixture

class FXPipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root,self.legacy,self.audit,_=build_fixture(Path(self.temp.name))
        self.sources=onboard(self.root,self.legacy,self.audit,migration_time='2026-10-09T10:00:00Z')
    def test_pending_scientific_choices_preserve_all_unblocked_outputs(self):
        result=register_and_construct(self.root,self.sources)
        self.assertEqual({x['instrument_id'] for x in result['instruments']},set(INSTRUMENTS))
        built=[x for x in result['instruments'] if x['price_snapshot']]
        self.assertEqual({x['instrument_id'] for x in built},set(DIRECT+INVERSE))
        self.assertEqual(sum(x['price_row_count'] for x in built),72)
        self.assertEqual(list(self.root.glob('definitions/targets/*/*.json')),[])
        self.assertTrue(all(x['price_snapshot'] is None for x in result['instruments'] if x['instrument_id'] in CROSS))
        store=FeatureStore(self.root)
        for item in built:
            manifest=store.resolve(item['price_snapshot']);store.verify_closure([manifest])
            rows=read_rows(store,manifest['body']['members'])
            self.assertEqual(len(rows),4);self.assertTrue(all(r['available_at'] is None for r in rows))
            self.assertTrue(manifest['body']['implementation'])
        self.assertEqual(len(list_instruments(self.root)),43)
    def test_repeat_reuses_manifest_ids_and_payload_bytes(self):
        first=register_and_construct(self.root,self.sources)
        saved={str(p):p.stat().st_mtime_ns for p in self.root.glob('storage/payloads/sha256/*/*')}
        second=register_and_construct(self.root,self.sources)
        self.assertEqual(first,second)
        for path,mtime in saved.items():self.assertEqual(Path(path).stat().st_mtime_ns,mtime)

    def test_completion_preserves_exact_sources_prices_and_reusable_legs(self):
        from test_fx_targets import approve
        first=register_and_construct(self.root,self.sources)
        store=FeatureStore(self.root)
        policy=approve(store,{'approval_state':'approved','representation':'simple','horizons':[1,7,21,63,252],
            'calendar_id':'RESEARCH_WEEKDAYS','calendar_version':'1.0.0','clock':'scheduled_bars',
            'entry':{'rule':'anchor_mark','delay':{'amount':0,'unit':'calendar_days'}},
            'endpoint':{'rule':'exact','tolerance':{'amount':0,'unit':'calendar_days'}}})
        alignment={'id':'FX_RETROSPECTIVE_DATES','version':'1.0.0','mode':'retrospective_date_label',
            'approval_state':'approved','approval_evidence':policy['approval_evidence'],
            'max_date_gap':0,'max_valuation_gap_seconds':None}
        second=register_and_construct(self.root,self.sources,alignment_policy=alignment,preserve_completion=first['completion'])
        before={r['instrument_id']:r for r in first['instruments']}
        expected_legs={}
        for item in first['instruments']:
            if item['price_snapshot']:
                for leg in store.resolve(item['price_snapshot'])['body']['normalized_legs']:
                    expected_legs[store.resolve(leg)['body']['currency']]=leg
        for item in second['instruments']:
            self.assertIsNotNone(item['price_snapshot'])
            if item['instrument_id'] in DIRECT+INVERSE:self.assertEqual(item,before[item['instrument_id']])
            snapshot=store.resolve(item['price_snapshot'])
            for leg in snapshot['body']['normalized_legs']:
                self.assertEqual(leg,expected_legs[store.resolve(leg)['body']['currency']])
        files={str(p):p.stat().st_mtime_ns for p in self.root.glob('storage/payloads/sha256/*/*')}
        repeat=register_and_construct(self.root,self.sources,alignment_policy=alignment,preserve_completion=first['completion'])
        self.assertEqual(second,repeat)
        for path,mtime in files.items():self.assertEqual(Path(path).stat().st_mtime_ns,mtime)
        changed=dict(self.sources,sources=self.sources['sources'][:-1])
        with self.assertRaisesRegex(ValueError,'exact source snapshots'):
            register_and_construct(self.root,changed,alignment_policy=alignment,preserve_completion=first['completion'])

if __name__=='__main__':unittest.main()
