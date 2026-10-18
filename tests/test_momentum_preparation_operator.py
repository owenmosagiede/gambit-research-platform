import importlib.util,unittest,tempfile,json,subprocess,sys,os
from unittest.mock import patch
from types import SimpleNamespace
from pathlib import Path
spec=importlib.util.spec_from_file_location('preparation_operator',Path(__file__).resolve().parents[1]/'tools/prepare_momentum_population.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class GeometryTests(unittest.TestCase):
 def test_phase_and_scope_cuts_partition_every_weekday_exactly_once(self):
  start,end='1989-10-16','2022-01-01';cuts=['2003-12-01','2020-04-14']
  windows=m.windows(start,end,cuts);seen=[]
  from datetime import date,timedelta
  for a,b in windows:
   self.assertTrue(m.compatible_window({'start_inclusive':a,'end_inclusive':b},start,end,cuts))
   self.assertLess((date.fromisoformat(b)-date.fromisoformat(a)).days,366)
   seen.extend(m.days(a,(date.fromisoformat(b)+timedelta(days=1)).isoformat()))
  self.assertEqual(seen,list(m.days(start,end)));self.assertEqual(len(seen),len(set(seen)))
 def test_phase_leak_and_scope_straddling_rejected(self):
  for a,b in [('2021-12-01','2022-01-03'),('2003-11-28','2003-12-05'),('1980-01-01','1990-01-01')]:
   self.assertFalse(m.compatible_window({'start_inclusive':a,'end_inclusive':b},'1989-10-16','2022-01-01',['2003-12-01']))
 def test_identical_date_boundary_and_weekend_boundary(self):
  self.assertEqual(m.windows('2021-12-30','2022-01-04',['2022-01-01']),[('2021-12-30','2021-12-31'),('2022-01-03','2022-01-03')])
 def test_atomic_checkpoints_replace_complete_json_only(self):
  with tempfile.TemporaryDirectory() as folder:
   p=Path(folder)/'state.json';m.atomic(p,{'n':1});m.atomic(p,{'n':2})
   self.assertEqual(json.loads(p.read_text()),{'n':2});self.assertEqual(len(list(p.parent.iterdir())),1)
 def test_capacity_reserves_cover_data_inodes_and_backup_staging(self):
  good=SimpleNamespace(f_bavail=90*1024**3,f_frsize=1,f_blocks=100*1024**3,f_bfree=93*1024**3,f_favail=5_000_000)
  boot=SimpleNamespace(f_bavail=60*1024**3,f_frsize=1)
  with patch.object(m.os,'statvfs',side_effect=[good,boot]):self.assertEqual(m.capacity(Path('/fixture'))['data_free_inodes'],5_000_000)
  for changes,boot_free in [({'f_bavail':19*1024**3},60),({'f_favail':999_999},60),({},16)]:
   v=SimpleNamespace(**(vars(good)|changes));b=SimpleNamespace(f_bavail=boot_free*1024**3,f_frsize=1)
   with patch.object(m.os,'statvfs',side_effect=[v,b]):
    with self.assertRaisesRegex(RuntimeError,'paused'):m.capacity(Path('/fixture'))
 def test_executor_waits_for_brief_contention_and_honors_stop(self):
  import fcntl,threading
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);path=root/'storage/catalog/operations/research-executor.lock';path.parent.mkdir(parents=True)
   with path.open('a+b') as other:
    fcntl.flock(other,fcntl.LOCK_EX|fcntl.LOCK_NB)
    timer=threading.Timer(.15,lambda:fcntl.flock(other,fcntl.LOCK_UN));timer.start()
    try:
     with m.executor(root):pass
    finally:timer.join()
    fcntl.flock(other,fcntl.LOCK_EX|fcntl.LOCK_NB)
    with patch.object(m,'STOP',True):
     with self.assertRaises(InterruptedError):
      with m.executor(root):self.fail('Contended executor must not be entered')
    with patch.object(m.time,'monotonic',side_effect=[0,31]):
     with self.assertRaisesRegex(RuntimeError,'remained busy'):
      with m.executor(root):self.fail('Contended executor must not be entered')
 def test_apply_and_dry_run_cannot_be_combined_or_use_unbounded_negative_limit(self):
  for args in [('--apply','--dry-run'),('--max-windows','-1')]:
   with tempfile.TemporaryDirectory() as folder:
    command=[sys.executable,str(Path(m.__file__)),'--root',folder,'--bundle',folder,'--expected-bundle-sha256','0'*64,*args]
    result=subprocess.run(command,capture_output=True,text=True)
    self.assertEqual(result.returncode,2);self.assertEqual(list(Path(folder).iterdir()),[])
 def test_wrong_frozen_bundle_fails_before_any_publication(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder)
   for name in ('preparation-manifest.json','instrument-preparation-matrix.json','scope-coverage-matrix.json'):(root/name).write_text('{}')
   before={p.name:p.read_bytes() for p in root.iterdir()}
   result=subprocess.run([sys.executable,str(Path(m.__file__)),'--root',folder,'--bundle',folder,'--expected-bundle-sha256','0'*64,'--apply'],
     env=dict(os.environ,GAMBIT_ISOLATED_TEST='1'),capture_output=True,text=True)
   self.assertNotEqual(result.returncode,0);self.assertIn('Frozen preparation bundle differs',result.stderr)
   self.assertEqual({p.name:p.read_bytes() for p in root.iterdir()},before)
 def test_preflight_requires_exact_pins_complete_horizons_and_log_integrity(self):
  import hashlib
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);profile={'target_selection':{'source_snapshots':{'EURUSD':{'id':'source'}},'materializations':{'EURUSD':{'1':{'id':'target'}}},'knowledge_cutoff':'2026-10-09'}}
   raw=b'{"kind":"target_verified","instrument":"EURUSD","horizon":1}\n{"kind":"done"}\n'
   (root/'cloud-verify-all.jsonl').write_bytes(raw)
   receipt={'verification_log_sha256':hashlib.sha256(raw).hexdigest(),'bundle_sha256':'bundle',
      'source_snapshots':profile['target_selection']['source_snapshots'],'target_materializations':profile['target_selection']['materializations'],
      'knowledge_cutoff':'2026-10-09','success':True}
   (root/'target-preflight-receipt.json').write_text(json.dumps(receipt))
   m.verify_preflight(root,profile,'bundle',{('EURUSD',1)})
   with self.assertRaisesRegex(RuntimeError,'incomplete'):m.verify_preflight(root,profile,'bundle',{('EURUSD',1),('EURUSD',7)})
   with self.assertRaisesRegex(RuntimeError,'differs'):m.verify_preflight(root,profile,'different',{('EURUSD',1)})
   (root/'cloud-verify-all.jsonl').write_bytes(raw+b' ')
   with self.assertRaisesRegex(RuntimeError,'differs'):m.verify_preflight(root,profile,'bundle',{('EURUSD',1)})
if __name__=='__main__':unittest.main()
