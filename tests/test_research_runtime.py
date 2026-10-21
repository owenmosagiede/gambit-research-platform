"""Synthetic-only Submit orchestration, authority, recovery and reuse tests."""
from copy import deepcopy
from datetime import date,timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json,math,threading,unittest,uuid
from research.contracts import digest,ref,canonical,profile_blockers,ResearchConflict,ResearchError,ResearchBlocked
from research.store import ResearchStore,install_bytes
from runtime.research_jobs import ResearchJobs

def reference(name):return {'id':name,'version':'1.0.0','content_sha256':digest(name)}
def profile():
 return {'id':'RSPEC_SYNTHETIC_RUNTIME','version':'1.0.0','approval_state':'approved',
  'availability_mode':'retrospective_date_label','exposure_classification':'ISOLATED_SYNTHETIC_TEST_ONLY',
  'periods':{'P1':{'start_inclusive':'2017-01-01','end_exclusive':'2022-01-01'},'P2':{'start_inclusive':'2022-01-01','end_exclusive':'2026-09-01'}},
  'target_selection':{'knowledge_cutoff':'2026-10-09','materializations':{}},
  'kernel':{'kernel_policy':'retained_legacy_v1','spacing':1,'horizon_unit':'scheduled_weekdays','clock_compatibility':'approved','missing_evidence':'legacy_failed_v1'},
  'approvals':dict.fromkeys(('clock_compatibility','retrospective_alignment','validation_exposure','missing_evidence'),True)}
def intent(rid=None,mode='CS',direction='POSITIVE'):
 return {'request_id':rid or str(uuid.uuid4()),'feature':{'id':'FEATURE_RECIPE_'+'a'*64,'version':'1.0.0'},
 'scope':{'id':'SCOPE_'+mode,'version':'1.0.0'},'target_family':'price_return','expected_direction':direction}
def weekday_after(day,n):
 while n:
  day+=timedelta(days=1)
  if day.weekday()<5:n-=1
 return day
class Adapter:
 def __init__(self):self.resolve_calls=0;self.loads=[];self.preparations=[];self.fail_horizon=None;self.on_prepare=None
 def resolve_plan(self,root,intent,profile):
  self.resolve_calls+=1;mode=intent['scope']['id'][-2:];members=['AAA'] if mode=='TS' else ['AAA','BBB','CCC','DDD','EEE']
  plan={'intent':intent,'profile':profile,'recipe':reference(intent['feature']['id']),'scope':reference(intent['scope']['id']),
   'mode':mode,'periods':profile['periods'],'structural_common_start':'2017-01-02','members':[
    {'instrument_id':m,'feature':reference('FEATURE_'+digest(m)), 'signal_id':'SIGNAL_'+digest(m),
     'targets':{str(h):{'definition':reference('TARGET_'+digest([m,h])),'materialization':reference('MATERIALIZATION_'+digest([m,h,'target']))} for h in (1,7,21,63,252)}} for m in members]}
  plan['plan_id']='PLAN_'+digest(plan);return plan
 def prepare_phase(self,root,plan,phase,progress=None,cancelled=None,admission=None):
  self.preparations.append(phase)
  if self.on_prepare:self.on_prepare()
  if cancelled and cancelled():
   error=RuntimeError('cancelled');error.cancelled=True;raise error
  if phase=='P2':assert admission and admission['plan_id']==plan['plan_id']
  return {'plan_id':plan['plan_id'],'prepared_id':'PREP_'+digest([plan['plan_id'],phase]),'phase':phase,'period':plan['periods'][phase],
   'members':[{'instrument_id':m['instrument_id'],'materializations':[reference('MATERIALIZATION_'+digest([m['instrument_id'],phase]))],'unavailable':[]} for m in plan['members']]}
 def load_phase(self,root,plan,prepared,phase,horizon,admission=None):
  self.loads.append((phase,horizon))
  if self.fail_horizon==horizon and phase=='P1':self.fail_horizon=None;raise RuntimeError('Injected after a completed horizon')
  if phase=='P2':assert horizon in admission['admitted_horizons']
  rows=[];day=date(2018,1,2) if phase=='P1' else date(2022,1,3)
  for i in range(400):
   for j,m in enumerate(plan['members']):
    x=math.sin(i*.3)+i*.001 if plan['mode']=='TS' else j+math.sin(i*.1+j)*.2
    y=.5*x+.5*math.cos(i*.7) if plan['mode']=='TS' else .6*j+math.sin(i*.19+j*.9)*2.3
    rows.append({'date':day.isoformat(),'instrument':m['instrument_id'],'feature':str(x),'target':str(y),
     'target_end':weekday_after(day,horizon).isoformat(),'valid':True,'status':'valid','lineage':[]})
   day=weekday_after(day,1)
  return {'rows':rows,'members':[m['instrument_id'] for m in plan['members']],'coverage':{'synthetic':True},'lineage':[],'phase':phase,'horizon':horizon,'plan_id':plan['plan_id']}
class KernelSpy:
 def __init__(self,missing=False):self.calls=[];self.missing=missing
 def run_p1(self,rows,**kw):
  self.calls.append(('P1',kw['horizon']));return {'stage':'P1','metrics':{'primary_effect':None if self.missing else 1.0},'sample':{'n':len(rows)},'admission':'admitted','reason_codes':['TEST'],'artifacts':{'rows':rows},'evidence':{}}
 def run_p2(self,rows,**kw):
  self.calls.append(('P2',kw['horizon']));return {'stage':'P2','metrics':{'primary_effect':1.0},'sample':{'n':len(rows)},'decision':'VALIDATED','reason_codes':['TEST'],'artifacts':{},'evidence':{}}
class RuntimeTests(unittest.TestCase):
 def setUp(self):
  self.temp=TemporaryDirectory();self.root=Path(self.temp.name);(self.root/'config').mkdir();self.set_profile(profile());self.adapter=Adapter()
 def tearDown(self):self.temp.cleanup()
 def set_profile(self,value):(self.root/'config/research_execution.json').write_text(json.dumps(value))
 def execute(self,request=None,kernels=None):
  jobs=ResearchJobs(self.root,adapter=self.adapter,kernels=kernels);request=request or intent();jobs.submit(request);jobs.run_pending_once();return jobs,jobs.get(request['request_id'])
 def test_real_cs_kernels_five_evaluations(self):
  jobs,job=self.execute()
  self.assertEqual(job['status'],'succeeded',job);self.assertEqual(job['mode'],'CS');self.assertEqual(len(job['horizons']),5)
  self.assertEqual(len([x for x in self.adapter.loads if x[0]=='P1']),5)
  relationships=jobs.store.results_for_recipe(intent()['feature']['id']);self.assertEqual(len(relationships),5)
  for r in relationships:
   self.assertEqual(r['mode'],'CS');self.assertEqual(r['results'][0]['sample']['inference_observation_count'],400)
   self.assertEqual(r['results'][0]['sample']['inference_observation_unit'],'dates')
   self.assertIsNotNone(r['results'][0]['metrics']['primary_effect'])
 def test_real_ts_kernels_individual(self):
  jobs,job=self.execute(intent(mode='TS'));self.assertEqual(job['status'],'succeeded',job);self.assertEqual(job['mode'],'TS');self.assertEqual(len(job['horizons']),5)
  for r in jobs.store.results_for_recipe(intent()['feature']['id']):
   self.assertEqual(r['results'][0]['sample']['inference_observation_count'],400)
   self.assertAlmostEqual(float(r['results'][0]['metrics']['primary_effect']),.5,delta=.03)
 def test_pending_policy_never_resolves_or_prepares(self):
  p=profile();p['approval_state']='pending';self.set_profile(p)
  with self.assertRaises(ResearchBlocked):self.execute()
  self.assertEqual(self.adapter.resolve_calls,0);self.assertFalse(self.adapter.preparations)
 def test_malformed_policy_is_blocked_before_preparation(self):
  for key,value,code in [('spacing',True,'KERNEL_COMPATIBILITY_UNRESOLVED'),('date','20170101','RESEARCH_PERIODS_UNRESOLVED')]:
   with self.subTest(key=key):
    p=profile()
    if key=='spacing':p['kernel']['spacing']=value
    else:p['periods']['P1']['start_inclusive']=value
    self.set_profile(p)
    with self.assertRaises(ResearchBlocked) as raised:self.execute()
    self.assertIn(code,[b['code'] for b in raised.exception.blockers]);self.assertEqual(self.adapter.resolve_calls,0)
 def test_fingerprint_covers_preparation_and_data_contracts(self):
  from runtime.research_jobs import implementation
  files=implementation()['files']
  self.assertIn('data/fx_feature_store.py',files)
  self.assertIn('data/targets/fx.py',files)
 def test_duplicate_submit_and_conflict(self):
  jobs=ResearchJobs(self.root,adapter=self.adapter);r=intent();a,created=jobs.submit(r);b,created2=jobs.submit(r)
  self.assertTrue(created);self.assertFalse(created2);self.assertEqual(a['request_id'],b['request_id'])
  changed=dict(r,expected_direction='NEGATIVE')
  with self.assertRaises(ResearchConflict):jobs.submit(changed)
 def test_concurrent_same_request_records_one_intent(self):
  jobs=ResearchJobs(self.root,adapter=self.adapter);r=intent();results=[]
  threads=[threading.Thread(target=lambda:results.append(jobs.submit(r)[1])) for _ in range(4)]
  for t in threads:t.start()
  for t in threads:t.join()
  self.assertEqual(sum(results),1)
 def test_resume_uses_frozen_plan_and_completed_trials(self):
  spy=KernelSpy();self.adapter.fail_horizon=7;jobs,job=self.execute(kernels=spy)
  self.assertEqual(job['status'],'failed');rid=job['request_id'];self.assertEqual(spy.calls,[('P1',1)])
  jobs.resume(rid);jobs.run_pending_once();self.assertEqual(jobs.get(rid)['status'],'succeeded')
  self.assertEqual(self.adapter.resolve_calls,1);self.assertEqual(spy.calls.count(('P1',1)),1)
 def test_obsolete_resume_rejected_without_requeue_or_history_changes(self):
  jobs=ResearchJobs(self.root,adapter=self.adapter);r=intent();jobs.submit(r);jobs.cancel(r['request_id'])
  before={p:p.read_bytes() for p in (self.root/'storage').rglob('*.json')}
  with patch('runtime.research_jobs.implementation',return_value={'changed':True}):
   public=jobs.get(r['request_id'])
   self.assertFalse(public['resumable']);self.assertEqual(public['resume_blocker']['code'],'IMPLEMENTATION_CHANGED')
   self.assertFalse(jobs.list_jobs()['items'][0]['job']['resumable'])
   with self.assertRaisesRegex(ResearchConflict,'cannot resume'):jobs.resume(r['request_id'])
  self.assertEqual(before,{p:p.read_bytes() for p in (self.root/'storage').rglob('*.json')})
  self.assertTrue(jobs.get(r['request_id'])['resumable'])
  self.assertFalse(self.adapter.preparations)
 def test_same_science_new_request_reuses_results(self):
  spy=KernelSpy();jobs,_=self.execute(kernels=spy);before=list(spy.calls)
  jobs.submit(intent());jobs.run_pending_once();self.assertEqual(spy.calls,before)
 def test_direction_conflict_never_loads_validation(self):
  jobs,job=self.execute(intent(direction='NEGATIVE'),KernelSpy());self.assertEqual(job['status'],'succeeded')
  self.assertEqual(self.adapter.preparations,['P1']);self.assertTrue(all(r['p2_status']=='FAILED' for r in job['horizons']))
  results=jobs.store.results_for_recipe(intent()['feature']['id']);self.assertTrue(all(r['p2_status']=='FAILED' for r in results))
 def test_missing_discovery_effect_has_authoritative_unresolved(self):
  jobs,job=self.execute(kernels=KernelSpy(missing=True));self.assertEqual(job['status'],'succeeded');self.assertEqual(self.adapter.preparations,['P1'])
  results=jobs.store.results_for_recipe(intent()['feature']['id']);self.assertEqual(len(results),5);self.assertTrue(all(r['p2_status']=='UNRESOLVED' for r in results))
 def test_projection_loss_rebuilt_from_events(self):
  jobs=ResearchJobs(self.root,adapter=self.adapter);r=intent();jobs.submit(r);jobs._job_path(r['request_id']).unlink()
  self.assertEqual(jobs.get(r['request_id'])['status'],'queued')
 def test_cancel_during_preparation_no_trial(self):
  jobs=ResearchJobs(self.root,adapter=self.adapter);r=intent();jobs.submit(r);self.adapter.on_prepare=lambda:jobs.cancel(r['request_id']);jobs.run_pending_once()
  self.assertEqual(jobs.get(r['request_id'])['status'],'cancelled');self.assertFalse((self.root/'storage/catalog/trial_ledger').exists())
 def test_changed_profile_does_not_change_frozen_request(self):
  jobs=ResearchJobs(self.root,adapter=self.adapter,kernels=KernelSpy());request=intent();jobs.submit(request)
  p=profile();p['version']='2.0.0';self.set_profile(p);jobs.run_pending_once()
  self.assertEqual(jobs.get(request['request_id'])['status'],'succeeded')
  self.assertEqual(jobs._submission(request['request_id'])['research_spec']['version'],'1.0.0');self.assertEqual(self.adapter.resolve_calls,1)
 def test_altered_trial_metric_detected(self):
  store=ResearchStore(self.root);r=store.put('trial',{'a':1},{'metrics':{'beta':1.0}});p=store.path('trial',r['id']);r['body']['metrics']['beta']='2';p.write_bytes(canonical(r)+b'\n')
  with self.assertRaisesRegex(ResearchError,'checksum'):store.find('trial',{'a':1})
 def test_conflicting_result_never_overwrites(self):
  store=ResearchStore(self.root);store.put('trial',{'key':1},{'value':1})
  with self.assertRaises(ResearchConflict):store.put('trial',{'key':1},{'value':2})
 def test_no_worker_start_without_request(self):
  jobs=ResearchJobs(self.root,adapter=self.adapter,start_worker=True);jobs.close();self.assertFalse((self.root/'storage').exists())
if __name__=='__main__':unittest.main()
