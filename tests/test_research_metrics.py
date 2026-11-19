"""Operational counters: exact window, stable snapshots, bounds and no writes."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from api.catalog_cache import CatalogCache
from api.application import ApplicationRoutes
from api.research_metrics import observe_counts
from read_model.storage import Unavailable
from research.contracts import canonical, digest

NOW=datetime(2026,11,19,12,tzinfo=timezone.utc)

class ResearchMetricsTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve();(self.root/'storage/catalog/operations/jobs').mkdir(parents=True)
    def job(self,n,status,updated=None):
        rid=f'{n:08d}-1111-4111-8111-111111111111';aid=f'{n:08d}-2222-4222-8222-222222222222'
        body={'request_id':rid,'attempt_id':aid,'status':status,'updated_at':(updated or NOW).isoformat(),'progress':{'completed':4,'total':4}}
        event={'request_id':rid,'sequence':n,'job':body};sha=digest(event)
        p=self.root/f'storage/catalog/attempts/{aid}/events/RESEVENT_{sha}.json';p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(canonical(event))
        p=self.root/f'storage/catalog/operations/jobs/{rid}.json';p.write_bytes(canonical(dict(body,sequence=n,event_sha256=sha)))
        return p
    def files(self):return {p.relative_to(self.root).as_posix():p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
    def test_exact_last_hour_job_counts_not_horizons_or_scientific_passes(self):
        self.job(1,'queued');self.job(2,'p1');self.job(3,'p2');self.job(4,'cancelled');self.job(5,'failed');self.job(6,'blocked')
        self.job(7,'succeeded',NOW-timedelta(minutes=60));self.job(8,'succeeded',NOW);self.job(9,'succeeded',NOW-timedelta(minutes=60,seconds=1));self.job(10,'succeeded',NOW+timedelta(seconds=1))
        before=self.files();v=observe_counts(self.root,now=NOW)
        self.assertEqual((1,2),(v['queued'],v['completed_last_hour']));self.assertEqual(10,v['jobs_observed']);self.assertEqual(before,self.files())
        self.assertEqual((NOW-timedelta(hours=1)).isoformat(),v['window_start']);self.assertEqual(NOW.isoformat(),v['window_end'])
    def test_empty_initialized_queue_is_zero_but_missing_store_unavailable(self):
        self.assertEqual(0,observe_counts(self.root,now=NOW)['queued'])
        (self.root/'storage/catalog/operations/jobs').rmdir()
        with self.assertRaises(Unavailable):observe_counts(self.root,now=NOW)
    def test_projection_mismatch_and_symlink_never_return_partial_counts(self):
        p=self.job(1,'queued');p.write_bytes(p.read_bytes().replace(b'queued',b'failed'))
        with self.assertRaises(ValueError):observe_counts(self.root,now=NOW)
        p.unlink();p.symlink_to(self.root/'outside.json');(self.root/'outside.json').write_text('{}')
        with self.assertRaises(Unavailable):observe_counts(self.root,now=NOW)
    def test_bounds_fail_without_source_mutation(self):
        self.job(1,'queued');self.job(2,'succeeded');before=self.files()
        for name,value in [('MAX_JOBS',1),('MAX_RECORD_BYTES',1),('MAX_TOTAL_BYTES',1),('MAX_SECONDS',0)]:
            with self.subTest(name=name),patch('api.research_metrics.'+name,value):
                with self.assertRaises(Unavailable):observe_counts(self.root,now=NOW)
        self.assertEqual(before,self.files())
    def test_advancing_projection_retries_one_stable_capture(self):
        from api import research_metrics as m
        self.job(1,'queued');original=m.read_document;changed=False
        def read(path,*args):
            nonlocal changed
            value=original(path,*args)
            if path.parent.name=='jobs' and not changed:
                changed=True;self.job(1,'succeeded')
            return value
        with patch.object(m,'read_document',side_effect=read):v=m.observe_counts(self.root,now=NOW)
        self.assertEqual((0,1),(v['queued'],v['completed_last_hour']))
    def test_persistent_churn_is_unavailable(self):
        from api import research_metrics as m
        self.job(1,'queued');original=m.read_document;sequence=0
        def read(path,*args):
            nonlocal sequence
            value=original(path,*args)
            if path.parent.name=='jobs':
                sequence+=1;self.job(1,'p1' if sequence%2 else 'queued')
            return value
        with patch.object(m,'read_document',side_effect=read),self.assertRaises(Unavailable):m.observe_counts(self.root,now=NOW)
    def test_warm_refresh_reuses_only_unchanged_verified_metadata(self):
        from api import research_metrics as m
        self.job(1,'queued');original=m.read_document
        with patch.object(m,'read_document',wraps=original) as reads:
            self.assertEqual(1,m.observe_counts(self.root,now=NOW)['queued'])
            self.assertEqual(2,reads.call_count)
            self.assertEqual(1,m.observe_counts(self.root,now=NOW)['queued'])
            self.assertEqual(2,reads.call_count)
            self.job(1,'succeeded')
            self.assertEqual(1,m.observe_counts(self.root,now=NOW)['completed_last_hour'])
            self.assertEqual(4,reads.call_count)
        job=json.loads(next((self.root/'storage/catalog/operations/jobs').glob('*.json')).read_bytes())
        event=self.root/('storage/catalog/attempts/'+job['attempt_id']+'/events/RESEVENT_'+job['event_sha256']+'.json')
        event.write_bytes(b'{}')
        with self.assertRaises((ValueError,KeyError)):m.observe_counts(self.root,now=NOW)

    def test_http_counts_are_cached_read_only_and_independent_of_read_model(self):
        cache=CatalogCache();self.job(1,'queued');before=self.files()
        from api import research_metrics as m
        original=m.observe_counts
        with patch.object(m,'observe_counts',wraps=original) as calls:
            for method in ('GET','HEAD'):
                r=ApplicationRoutes(self.root,None,cache,method,'/api/research-metrics');r.read(method=='HEAD')
                self.assertEqual(200,r.response[0]);self.assertEqual(1,json.loads(r.response[1])['queued'])
            self.assertEqual(1,calls.call_count)
        r=ApplicationRoutes(self.root,None,cache,'GET','/api/research-metrics?status=queued');r.read();self.assertEqual(400,r.response[0])
        r=ApplicationRoutes(self.root,None,cache,'POST','/api/research-metrics');r.write(b'{}');self.assertIn(r.response[0],(404,405))
        self.assertEqual(before,self.files())
    def test_cache_override_does_not_extend_other_catalog_ttls(self):
        now=[0];cache=CatalogCache(clock=lambda:now[0]);calls=[]
        def read():calls.append(True);return {'n':len(calls)}
        self.assertEqual(1,cache.get('metrics',read,ttl=30)['n']);now[0]=10
        self.assertEqual(1,cache.get('metrics',read,ttl=30)['n']);cache.get('other',read);now[0]=16
        self.assertEqual(3,cache.get('other',read)['n']);now[0]=31
        self.assertEqual(4,cache.get('metrics',read,ttl=30)['n'])
