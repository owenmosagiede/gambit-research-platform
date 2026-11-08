"""No scans or writes; active identity requires heartbeat, held lock and event."""
import fcntl
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from api.live_activity import observe
from research.contracts import canonical,digest


class LiveActivityTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name).resolve()
        self.ops=self.root/'storage/catalog/operations';self.ops.mkdir(parents=True)
        self.rid='11111111-1111-4111-8111-111111111111';self.attempt='22222222-2222-4222-8222-222222222222'
        self.heartbeat={'workspace':str(self.root),'pid':os.getpid(),'session_id':'fixture','monotonic_ns':time.monotonic_ns(),'health':{'state':'running'},'activity':{'request_id':self.rid}}
        self.job={'request_id':self.rid,'attempt_id':self.attempt,'status':'p2','stage':'P2','plan':{'id':'fixture'},'updated_at':'2026-01-01T00:00:00Z','message':'Evaluating P2'}
        self.event={'request_id':self.rid,'sequence':4,'previous':'fixture','job':self.job}
        self.write('worker_service.json',self.heartbeat)
        self.write('jobs/'+self.rid+'.json',dict(self.job,sequence=4,event_sha256=digest(self.event)))
        event=self.root/f'storage/catalog/attempts/{self.attempt}/events/RESEVENT_{digest(self.event)}.json';event.parent.mkdir(parents=True);event.write_bytes(canonical(self.event)+b'\n')
        self.lock=(self.ops/'research-worker-service.lock').open('a+b');fcntl.flock(self.lock,fcntl.LOCK_EX|fcntl.LOCK_NB);self.addCleanup(self.lock.close)

    def write(self,name,value):
        path=self.ops/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value))

    def test_verified_current_event_and_preparation_without_scans_or_writes(self):
        self.write('preparation/'+self.rid+'.json',{'request_id':self.rid,'attempt_id':self.attempt,'plan':self.job['plan'],'phase':'P2','members_total':18,'members_completed':3})
        before={p:p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        with patch.object(Path,'glob',side_effect=AssertionError('scan')),patch.object(Path,'rglob',side_effect=AssertionError('scan')):
            result=observe(self.root)
        self.assertEqual(result['active']['request_id'],self.rid)
        self.assertEqual(result['active']['preparation']['members_completed'],3)
        self.assertEqual(before,{p:p.read_bytes() for p in self.root.rglob('*') if p.is_file()})

    def test_stale_session_missing_lock_or_corrupt_projection_never_claims_active(self):
        self.write('worker_service.json',dict(self.heartbeat,monotonic_ns=0));self.assertIsNone(observe(self.root)['active'])
        self.write('worker_service.json',self.heartbeat)
        fcntl.flock(self.lock,fcntl.LOCK_UN);self.assertEqual(observe(self.root)['worker']['state'],'unknown')
        fcntl.flock(self.lock,fcntl.LOCK_EX)
        self.write('jobs/'+self.rid+'.json',dict(self.job,sequence=4,event_sha256='a'*64))
        self.assertTrue(observe(self.root)['activity_unavailable'])

    def test_old_worker_and_wrong_attempt_progress_are_explicitly_unavailable(self):
        self.write('preparation/'+self.rid+'.json',{'request_id':self.rid,'attempt_id':self.rid,'plan':self.job['plan']})
        self.assertNotIn('preparation',observe(self.root)['active'])
        h=dict(self.heartbeat);h.pop('activity');self.write('worker_service.json',h)
        self.assertTrue(observe(self.root)['activity_unavailable'])

    def test_request_switch_during_read_drops_current_activity(self):
        from api import live_activity
        original=live_activity.read_document;calls=0
        def read(path,*args):
            nonlocal calls
            result=original(path,*args)
            if path.name=='worker_service.json':
                calls+=1
                if calls==2:result['activity']={'request_id':None}
            return result
        with patch.object(live_activity,'read_document',side_effect=read):
            self.assertIsNone(observe(self.root)['active'])
