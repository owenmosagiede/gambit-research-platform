"""Durable queue order, read-only metadata, and submissions during real worker execution."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json, threading, time, unittest
from runtime.research_jobs import ResearchJobs
from test_research_runtime import Adapter, KernelSpy, intent, profile

FIRST='f0000000-0000-4000-8000-000000000001'
SECOND='10000000-0000-4000-8000-000000000002'
THIRD='20000000-0000-4000-8000-000000000003'

class QueueTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.root=Path(self.temp.name)
        (self.root/'config').mkdir();(self.root/'config/research_execution.json').write_text(json.dumps(profile()))
        self.jobs=ResearchJobs(self.root,adapter=Adapter(),kernels=KernelSpy())
    def tearDown(self):
        self.jobs.close();self.temp.cleanup()
    def submit(self,rid):return self.jobs.submit(intent(rid=rid,mode='TS'))
    def test_creation_order_not_uuid_and_restart_retains_queue(self):
        self.submit(FIRST);self.submit(SECOND)
        self.assertEqual(self.jobs._pending(),[FIRST,SECOND])
        fresh=ResearchJobs(self.root)
        self.assertEqual(fresh._pending(),[FIRST,SECOND])
        listing=fresh.list_jobs()
        self.assertEqual([i['job']['request_id'] for i in listing['items']],[FIRST,SECOND])
        self.assertEqual([i['queue_position'] for i in listing['items']],[1,2])
        self.assertEqual(listing['items'][0]['intent']['scope']['id'],'SCOPE_TS')
        self.assertEqual(self.jobs.adapter.resolve_calls,0)
    def test_old_job_without_queue_timestamp_and_running_recovery(self):
        self.submit(FIRST);self.submit(SECOND)
        j=self.jobs._read_job(FIRST);j.pop('queued_at');self.jobs._save(j)
        self.assertEqual(self.jobs._pending(),[FIRST,SECOND])
        self.jobs._update(SECOND,status='p1')
        self.assertEqual(self.jobs._pending(),[SECOND,FIRST])
    def test_cancel_waiting_and_resume_joins_back_without_changing_intent(self):
        self.submit(FIRST);self.submit(SECOND)
        frozen=self.jobs._submission_path(FIRST).read_bytes()
        self.jobs.cancel(FIRST)
        self.assertEqual(self.jobs._pending(),[SECOND])
        self.jobs.resume(FIRST)
        self.assertEqual(self.jobs._pending(),[SECOND,FIRST])
        self.assertEqual(frozen,self.jobs._submission_path(FIRST).read_bytes())
    def test_corruption_is_visible_without_hiding_valid_jobs(self):
        self.submit(FIRST);self.submit(SECOND)
        self.jobs._submission_path(FIRST).write_text('broken')
        listing=self.jobs.list_jobs()
        bad=next(i for i in listing['items'] if i['job']['request_id']==FIRST)
        self.assertTrue(bad['job']['operational_failure']);self.assertIsNone(bad['intent'])
        self.assertEqual(self.jobs._pending(),[SECOND])
    def test_real_worker_accepts_second_job_during_first_and_runs_sequentially(self):
        entered=threading.Event();release=threading.Event();order=[]
        original=self.jobs.adapter.resolve_plan
        def resolve(root,request,policy):
            order.append(request['scope']['id']);return original(root,request,policy)
        self.jobs.adapter.resolve_plan=resolve
        calls=[]
        def hold_first():
            calls.append(1)
            if len(calls)==1:entered.set();release.wait(10)
        self.jobs.adapter.on_prepare=hold_first
        self.submit(FIRST);self.jobs.start()
        try:
            self.assertTrue(entered.wait(5))
            self.submit(SECOND);self.submit(THIRD);self.jobs.cancel(THIRD)
            self.assertEqual(self.jobs.get(SECOND)['status'],'queued')
            self.assertEqual(len(order),1)
            release.set();deadline=time.monotonic()+20
            while time.monotonic()<deadline:
                if self.jobs.get(SECOND)['status']=='succeeded':break
                time.sleep(.05)
            self.assertEqual(self.jobs.get(FIRST)['status'],'succeeded')
            self.assertEqual(self.jobs.get(SECOND)['status'],'succeeded')
            self.assertEqual(len(order),2)
            self.assertEqual(self.jobs.get(THIRD)['status'],'cancelled')
        finally:release.set()
