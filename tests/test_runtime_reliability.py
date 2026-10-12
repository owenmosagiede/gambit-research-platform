"""Isolated runtime supervision/quarantine tests; no production stores."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import hashlib,json,threading,time,unittest,uuid
from runtime.research_jobs import ResearchJobs
from research.contracts import canonical,ResearchConflict
from test_research_runtime import Adapter,KernelSpy,intent,profile

class ThreadLoss(BaseException):pass

class ReliabilityTests(unittest.TestCase):
 def setUp(self):
  self.temp=TemporaryDirectory();self.root=Path(self.temp.name);(self.root/'config').mkdir()
  (self.root/'config/research_execution.json').write_bytes(canonical(profile()))
  self.jobs=ResearchJobs(self.root,adapter=Adapter(),kernels=KernelSpy());self.jobs.RESTART_DELAYS=(.03,.04,.05)
 def tearDown(self):self.jobs.close();self.temp.cleanup()
 def wait(self,fn,timeout=12):
  until=time.monotonic()+timeout
  while time.monotonic()<until:
   result=fn()
   if result:return result
   time.sleep(.01)
  self.fail('Condition timed out: '+repr(self.jobs.health()))
 def finish(self,r):return self.wait(lambda:self.jobs.get(r['request_id'])['status']=='succeeded')
 def test_idle_and_stopped_health(self):
  self.assertFalse(self.jobs.health()['healthy']);self.jobs.start()
  self.wait(lambda:self.jobs.health()['healthy']);self.assertEqual(self.jobs.health()['state'],'idle')
  self.assertFalse((self.root/'storage').exists());self.jobs.close();self.assertFalse(self.jobs.health()['healthy'])
 def test_scheduler_fault_recovers_and_executes_queued_work(self):
  original=self.jobs._loop;entered=threading.Event();release=threading.Event()
  def fail_once():
   if not entered.is_set():entered.set();release.wait(3);raise RuntimeError('scheduler fixture')
   original()
  self.jobs._loop=fail_once;r=intent();self.jobs.submit(r);self.jobs.start();self.assertTrue(entered.wait(2))
  release.set();self.finish(r);self.assertEqual(self.jobs.restarts,1)
  codes=[json.loads(p.read_text())['code'] for p in (self.root/'storage/catalog/operations/worker_events').glob('*/*.json')]
  self.assertIn('WORKER_TERMINATED',codes);self.assertIn('WORKER_RECOVERED',codes)
 def test_bounded_permanent_failure_and_durable_acceptance(self):
  def fail():raise OSError('permanent scheduler failure')
  self.jobs._loop=fail;r=intent();self.jobs.submit(r);self.jobs.start()
  self.wait(lambda:self.jobs.health()['state']=='failed' and not self.jobs.supervisor.is_alive())
  self.assertEqual(self.jobs.restarts,3);self.assertFalse(self.jobs.health()['healthy'])
  self.assertEqual(self.jobs.get(r['request_id'])['status'],'queued')
  self.assertTrue(self.jobs._submission_path(r['request_id']).exists())
 def test_loss_after_commit_reuses_authority(self):
  original=self.jobs.store.put;saved={}
  def put(kind,key,body):
   result=original(kind,key,body)
   if kind=='trial' and not saved:
    path=self.jobs.store.path('trial',result['id']);saved['path']=path;saved['hash']=hashlib.sha256(path.read_bytes()).hexdigest()
    raise ThreadLoss('abrupt thread termination after durable trial')
   return result
  self.jobs.store.put=put;r=intent();self.jobs.submit(r);self.jobs.start();self.finish(r)
  self.assertEqual(hashlib.sha256(saved['path'].read_bytes()).hexdigest(),saved['hash'])
  self.assertEqual(len(self.jobs.kernels.calls),10);self.assertEqual(len(set(self.jobs.kernels.calls)),10)
  self.assertEqual(len(list((self.root/'storage/catalog/trial_ledger/records').glob('*.json'))),10)
 def test_corruption_idempotent_and_healthy_work_continues(self):
  bad=intent();self.jobs.submit(bad);p=self.jobs._submission_path(bad['request_id']);p.write_bytes(b'{broken')
  good=intent();self.jobs.submit(good);self.jobs.start();self.finish(good)
  failure=self.jobs.get(bad['request_id']);self.assertTrue(failure['operational_failure']);self.assertFalse(failure['resumable'])
  self.assertEqual(failure['horizons'],[]);self.assertEqual(failure['results'],[])
  self.assertEqual((self.root/failure['incident']['evidence_path']).read_bytes(),b'{broken');self.assertEqual(p.read_bytes(),b'{broken')
  self.jobs._pending();self.jobs._pending()
  self.assertEqual(len(self.jobs.operational_status()['submission_incidents']),1)
  self.assertEqual(self.jobs.submit(bad)[0],failure)
  with self.assertRaises(ResearchConflict):self.jobs.resume(bad['request_id'])
 def test_invalid_filename_and_recoverable_envelope_identity(self):
  directory=self.root/'storage/catalog/submissions';directory.mkdir(parents=True)
  rid=str(uuid.uuid4());p=directory/'not-a-uuid.json';p.write_text(json.dumps({'request_id':rid}))
  self.jobs._pending();record=self.jobs.operational_status()['submission_incidents'][0]
  self.assertIsNone(record['request_id']);self.assertEqual(record['envelope_request_id'],rid)
  self.assertEqual(record['storage_path'],'storage/catalog/submissions/not-a-uuid.json')
 def test_incomplete_checksum_and_unreadable_inputs(self):
  for raw in (b'{}',b'[]',b'null'):
   r=intent();self.jobs.submit(r);self.jobs._submission_path(r['request_id']).write_bytes(raw)
   self.assertTrue(self.jobs.get(r['request_id'])['operational_failure'])
  r=intent();self.jobs.submit(r);p=self.jobs._submission_path(r['request_id']);p.unlink();p.mkdir()
  self.jobs._pending();record=self.jobs.get(r['request_id'])['incident'];self.assertEqual(record['read_error'],'IsADirectoryError');self.assertTrue(p.is_dir())
 def test_missing_accepted_envelope_is_incident(self):
  r=intent();self.jobs.submit(r);self.jobs._submission_path(r['request_id']).unlink()
  self.jobs._pending();self.assertEqual(self.jobs.get(r['request_id'])['incident']['read_error'],'FileNotFoundError')
 def test_quarantine_survives_restart_without_reparsing_original(self):
  r=intent();self.jobs.submit(r);p=self.jobs._submission_path(r['request_id']);p.write_bytes(b'{broken')
  first=self.jobs.get(r['request_id']);self.jobs.close()
  self.jobs=ResearchJobs(self.root,adapter=Adapter(),kernels=KernelSpy())
  with patch.object(self.jobs,'_submission',side_effect=AssertionError('Quarantined original reprocessed')):
   self.assertEqual(self.jobs.get(r['request_id']),first);self.jobs._pending()
 def test_incident_publication_failure_never_silently_skips_request(self):
  r=intent();self.jobs.submit(r);self.jobs._submission_path(r['request_id']).write_bytes(b'{bad')
  directory=self.root/'storage/catalog/operations/submission_incidents';directory.write_text('storage obstruction')
  self.jobs.start()
  self.wait(lambda:self.jobs.health()['state']=='failed' and not self.jobs.supervisor.is_alive())
  self.assertFalse(self.jobs.health()['healthy']);self.assertEqual(self.jobs.restarts,3)
  self.assertEqual(self.jobs.kernels.calls,[])
 def test_quarantine_does_not_modify_committed_scientific_records(self):
  r=intent();self.jobs.submit(r);self.jobs.run_pending_once()
  ledger=self.root/'storage/catalog/trial_ledger/records'
  before={p.name:p.read_bytes() for p in ledger.glob('*.json')}
  self.jobs._submission_path(r['request_id']).write_bytes(b'{damaged after completion')
  failure=self.jobs.get(r['request_id']);self.assertTrue(failure['operational_failure'])
  self.assertEqual(before,{p.name:p.read_bytes() for p in ledger.glob('*.json')})
  self.assertEqual(len(self.jobs.store.results_for_recipe(r['feature']['id'])),5)
 def test_diagnostic_storage_failure_is_exposed_in_memory(self):
  directory=self.root/'storage/catalog/operations/worker_events';directory.mkdir(parents=True);(directory/self.jobs.session_id).write_text('obstruction')
  with self.assertLogs('runtime.research_jobs',level='ERROR'):
   self.jobs._diagnostic('TEST_FAILURE')
  self.assertIn('diagnostic_write_error',self.jobs.health()['last_diagnostic'])

if __name__=='__main__':unittest.main()
