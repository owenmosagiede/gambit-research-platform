"""Real orchestration with isolated fixture data; no production research."""
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import threading
import unittest
from api.preparation_progress import ObservedResearchJobs
from runtime.research_jobs import ResearchJobs, implementation
from test_research_runtime import Adapter, intent, profile, KernelSpy

class BatchAdapter(Adapter):
    def __init__(self):super().__init__();self.checkpoint=None;self.break_batch=False
    def prepare_phase(self,root,plan,phase,progress=None,**kwargs):
        for member in plan['members']:
            for start,end in [('2018-01-01','2018-12-31'),('2019-01-01','2019-12-31')]:
                progress({'stage':phase,'action':'preparing_feature','instrument':member['instrument_id'],'start':start,'end':end})
                if self.checkpoint:self.checkpoint(phase)
                if self.break_batch:raise RuntimeError('isolated batch failure')
        return super().prepare_phase(root,plan,phase,progress=progress,**kwargs)

class PreparationProgressTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        (self.root/'config').mkdir();(self.root/'config/research_execution.json').write_text(json.dumps(profile()))
    def test_observation_preserves_results_and_freezes_identity(self):
        adapter=BatchAdapter();jobs=ObservedResearchJobs(self.root,adapter=adapter,kernels=KernelSpy());r=intent();seen=[]
        adapter.checkpoint=lambda phase:seen.append(jobs.get(r['request_id'])['preparation_progress'])
        before=implementation();jobs.submit(r);jobs.run_pending_once();job=jobs.get(r['request_id'])
        self.assertEqual(job['status'],'succeeded');self.assertEqual(implementation(),before)
        self.assertEqual(seen[0]['batches_completed'],0);self.assertEqual(seen[1]['batches_completed'],1)
        self.assertEqual(seen[2]['members_completed'],1);self.assertEqual(seen[2]['instrument'],'BBB')
        self.assertEqual(seen[10]['phase'],'P2');self.assertEqual(seen[10]['batches_completed'],0)
        self.assertEqual(job['preparation_progress']['state'],'complete')
        self.assertEqual(job['preparation_progress']['batches_completed'],10)
        self.assertEqual(job['preparation_progress']['members_completed'],5)
        self.assertTrue(all(h['p2_status']=='VALIDATED' for h in job['horizons']))
        self.assertEqual(len(jobs.store.results_for_recipe(r['feature']['id'])),5)
        self.assertIs(jobs.adapter,adapter)
        # A restarted service can read the sidecar, but another attempt cannot.
        fresh=ObservedResearchJobs(self.root,adapter=adapter)
        self.assertEqual(fresh.get(r['request_id'])['preparation_progress'],job['preparation_progress'])
        changed=deepcopy(job);changed['attempt_id']='different'
        self.assertNotIn('preparation_progress',fresh.public(changed))
    def test_failed_batch_is_not_counted_completed(self):
        adapter=BatchAdapter();adapter.break_batch=True;jobs=ObservedResearchJobs(self.root,adapter=adapter,kernels=KernelSpy());r=intent()
        jobs.submit(r);jobs.run_pending_once();job=jobs.get(r['request_id'])
        self.assertEqual(job['status'],'failed');self.assertEqual(job['preparation_progress']['batches_completed'],0)
        self.assertEqual(job['preparation_progress']['state'],'interrupted')
    def test_real_kernels_match_uninstrumented_execution(self):
        request=intent(mode='TS');observed=ObservedResearchJobs(self.root,adapter=Adapter())
        observed.submit(request);observed.run_pending_once()
        first=observed.store.results_for_recipe(request['feature']['id'])
        with TemporaryDirectory() as folder:
            root=Path(folder);(root/'config').mkdir();(root/'config/research_execution.json').write_text(json.dumps(profile()))
            baseline=ResearchJobs(root,adapter=Adapter());baseline.submit(request);baseline.run_pending_once()
            second=baseline.store.results_for_recipe(request['feature']['id'])
        extract=lambda rows:[(r['horizon'],r['p1_status'],r['p2_status'],[x['metrics'] for x in r['results']]) for r in rows]
        self.assertEqual(extract(first),extract(second))

    def test_http_submit_progress_and_completion_use_actual_worker(self):
        import http.client
        from time import monotonic, sleep
        from api.server import make_server
        adapter=BatchAdapter();entered=threading.Event();release=threading.Event()
        def checkpoint(phase):
            if not entered.is_set():entered.set();release.wait(5)
        adapter.checkpoint=checkpoint
        jobs=ObservedResearchJobs(self.root,adapter=adapter,start_worker=True)
        server=make_server(self.root,port=0,research_jobs=jobs)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        address=server.server_address;r=intent(mode='TS')
        def request(method,path,value=None):
            conn=http.client.HTTPConnection(*address,timeout=5)
            headers={'Content-Type':'application/json','Origin':f'http://127.0.0.1:{address[1]}'}
            try:
                conn.request(method,path,json.dumps(value) if value is not None else None,headers)
                response=conn.getresponse();return response.status,json.loads(response.read())
            finally:conn.close()
        try:
            status,_=request('POST','/api/experiments',r);self.assertIn(status,(200,201,202))
            self.assertTrue(entered.wait(3))
            status,body=request('GET','/api/experiments/'+r['request_id'])
            self.assertEqual(status,200);self.assertEqual(body['job']['preparation_progress']['instrument'],'AAA')
            # Submission connection is closed; the independent worker continues.
            release.set();deadline=monotonic()+10
            while monotonic()<deadline:
                _,body=request('GET','/api/experiments/'+r['request_id'])
                if body['job']['status'] in ('succeeded','failed','blocked'):break
                sleep(.05)
            self.assertEqual(body['job']['status'],'succeeded',body)
            _,results=request('GET','/api/research-results/'+r['feature']['id'])
            self.assertEqual(len(results['relationships']),5)
        finally:
            release.set();server.shutdown();server.server_close();thread.join(3)

    def test_native_submit_thread_keeps_adapter_none(self):
        jobs=ObservedResearchJobs(self.root);jobs._progress_context.request_id='synthetic'
        seen=[];t=threading.Thread(target=lambda:seen.append(jobs.adapter));t.start();t.join()
        self.assertEqual(seen,[None]);del jobs._progress_context.request_id
        self.assertIsNone(jobs.adapter)
    def test_cancellation_check_precedes_progress_and_no_new_calculation(self):
        adapter=BatchAdapter();jobs=ObservedResearchJobs(self.root,adapter=adapter,kernels=KernelSpy());r=intent()
        adapter.checkpoint=lambda phase:jobs.cancel(r['request_id'])
        jobs.submit(r);jobs.run_pending_once();job=jobs.get(r['request_id'])
        self.assertEqual(job['status'],'cancelled');self.assertFalse(adapter.loads)
    def test_no_callback_phase_reports_members_without_invented_batch_counts(self):
        jobs=ObservedResearchJobs(self.root,adapter=Adapter(),kernels=KernelSpy());r=intent()
        jobs.submit(r);jobs.run_pending_once();p=jobs.get(r['request_id'])['preparation_progress']
        self.assertEqual(p['members_completed'],5);self.assertEqual(p['batches_completed'],0)
