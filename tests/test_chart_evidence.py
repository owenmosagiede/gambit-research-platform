"""Saved chart parity, bounded rendering and source preservation."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from test_feature_research_dashboard import fixture
from research.contracts import ref, digest
from research.store import ResearchStore
from read_model.projector import build as metadata
from read_model.chart_evidence import project_trial, build, read_evidence, MAX_POINTS, MAX_AGE
from read_model.storage import Unavailable, atomic, encoded


class ChartEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name).resolve();self.root=self.base/'source';self.output=self.base/'serving'

    def inventory(self):
        return {str(p.relative_to(self.root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in self.root.rglob('*') if p.is_file()}

    def test_exact_saved_chart_and_metrics_unchanged_and_http_does_not_read_source(self):
        trials=fixture(self.root,p2='FAILED');metadata(self.root,self.output);before=self.inventory()
        result=build(self.root,self.output)
        self.assertEqual(result['issues'],[]);self.assertEqual(result['published'],2)
        # Serving must survive an unavailable source store; only cache + metadata.
        moved=self.base/'offline';self.root.rename(moved)
        try:
            data=read_evidence(self.output,trials[0]['id'])
            self.assertEqual(data['authority'],ref(trials[0]))
            self.assertEqual([p['y'] for p in data['chart']['points']],[.5,.25])
            self.assertEqual(data['chart']['total_count'],2)
            self.assertNotIn('usable_dates',data['artifacts']['scheduled_hac'])
        finally:moved.rename(self.root)
        self.assertEqual(before,self.inventory())

    def test_scatter_is_bounded_and_keeps_endpoints_without_recalculating_statistics(self):
        t=fixture(self.root,mode='TS')[0];before=self.inventory();value=project_trial(self.root,t)
        chart=value['chart'];self.assertLessEqual(len(chart['points']),MAX_POINTS)
        self.assertEqual(chart['total_count'],1301);self.assertEqual(chart['points'][-1]['x'],1.3)
        self.assertEqual(chart['points'][0]['x'],0);self.assertEqual(before,self.inventory())
        self.assertNotIn('metrics',value)

    def test_hash_corruption_revokes_old_summary_and_never_changes_trial(self):
        t=fixture(self.root)[0];metadata(self.root,self.output);build(self.root,self.output)
        cache=self.output/'charts'/f"{t['id']}.json"
        wrapper=json.loads(cache.read_text());wrapper['value']['verified_epoch']-=MAX_AGE
        wrapper['sha256']=digest(wrapper['value']);atomic(cache.parent,cache.name,wrapper)
        artifact=ResearchStore(self.root).verify_artifact(t['body']['artifact_manifests'][0])
        member=next(m for m in artifact['members'] if m['role']=='cross_sectional_ic_history');sha=member['blob_sha256']
        (self.root/f'storage/payloads/sha256/{sha[:2]}/{sha}.json').write_text('[]')
        self.assertTrue(build(self.root,self.output)['issues'])
        with self.assertRaises(Unavailable):read_evidence(self.output,t['id'])
        self.assertEqual(ResearchStore(self.root).get('trial',t['id']),t)

    def test_missing_cache_expired_cache_wrong_trial_and_changed_summary_fail_closed(self):
        t=fixture(self.root)[0];metadata(self.root,self.output)
        with self.assertRaises(Unavailable):read_evidence(self.output,t['id'])
        build(self.root,self.output);path=self.output/'charts'/f"{t['id']}.json";good=json.loads(path.read_text())
        for mutation in ('expired','wrong_trial','checksum'):
            wrapper=deepcopy(good)
            if mutation=='expired':wrapper['value']['verified_epoch']-=MAX_AGE+1
            if mutation=='wrong_trial':wrapper['value']['authority']['id']='TRIAL_'+'f'*64
            if mutation!='checksum':wrapper['sha256']=digest(wrapper['value'])
            else:wrapper['value']['chart']['points'][0]['y']=42
            atomic(path.parent,path.name,wrapper)
            with self.assertRaises(Unavailable):read_evidence(self.output,t['id'])

    def test_stream_parser_trailing_or_oversized_payload_and_budget_are_rejected(self):
        from read_model.chart_evidence import _rows
        import io
        for value in ('[{"a":1},]','[{"a":1}] false','[NaN]','["'+('x'*1100000)+'"]'):
            with self.assertRaises((ValueError,Unavailable)):list(_rows(io.StringIO(value)))
        t=fixture(self.root)[0]
        with self.assertRaises(TimeoutError):project_trial(self.root,t,deadline=time.monotonic()-1)
        with self.assertRaises(ValueError):build(self.root,self.root/'nested')

    def test_cumulative_sum_keeps_all_usable_dates_when_display_is_thinned(self):
        from datetime import date,timedelta
        store=ResearchStore(self.root);t=fixture(self.root)[0];key=dict(t['scientific_key'],display_fixture=True)
        rows=[{'anchor_date':str(date(2000,1,1)+timedelta(days=i)),'rank_ic':'.01'} for i in range(4000)]
        a=store.artifact(key,{'cross_sectional_ic_history':rows})
        trial=store.put('trial',key,dict(t['body'],artifact_manifests=[ref(a)]))
        c=project_trial(self.root,trial)['chart'];self.assertEqual(c['total_count'],4000)
        self.assertLessEqual(c['display_count'],MAX_POINTS);self.assertAlmostEqual(c['points'][-1]['y'],40)
        self.assertEqual(c['points'][-1]['date'],rows[-1]['anchor_date'])

    def test_runtime_guard_rejects_source_write_and_commands(self):
        from read_model.chart_evidence import source_read_only
        import subprocess
        self.root.mkdir()
        with source_read_only(self.root):
            with self.assertRaises(PermissionError):(self.root/'forbidden').write_text('no')
            with self.assertRaises(PermissionError):subprocess.run(['true'],check=True)
        self.assertFalse((self.root/'forbidden').exists())

    def test_http_chart_route_uses_only_serving_cache(self):
        from api.application import ApplicationRoutes
        t=fixture(self.root)[0];metadata(self.root,self.output);build(self.root,self.output)
        original=Path.open
        def no_source(path,*a,**kw):
            if path.resolve().is_relative_to(self.root):raise AssertionError('HTTP opened research source')
            return original(path,*a,**kw)
        with patch.object(Path,'open',no_source):
            for _ in range(3):
                route=ApplicationRoutes(self.root,None,None,'GET','/api/read-model/v1/evidence/'+t['id'],read_model_dir=self.output)
                route.read(False);self.assertEqual(route.response[0],200)
                self.assertEqual(json.loads(route.response[1])['authority'],ref(t))
