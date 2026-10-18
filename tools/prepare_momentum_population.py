"""One approved Momentum input-preparation operation; never executes research.

Inputs are frozen task manifests. Application writers/readers remain authoritative.
Run as gambit on the cloud, with packed writes enabled and an idle research queue.
"""
import argparse
from collections import defaultdict, Counter
from contextlib import contextmanager
from copy import deepcopy
from datetime import date,timedelta,datetime,timezone
import fcntl,hashlib,json,os,signal,sys,time,tempfile
from pathlib import Path

STOP=False

def stopping(*_):
 global STOP
 STOP=True

def atomic(path,value):
 path.parent.mkdir(parents=True,exist_ok=True)
 fd,temp=tempfile.mkstemp(dir=path.parent)
 try:
  with os.fdopen(fd,'w') as f:
   json.dump(value,f,sort_keys=True);f.write('\n');f.flush();os.fsync(f.fileno())
  os.replace(temp,path)
  fd=os.open(path.parent,os.O_RDONLY)
  try:os.fsync(fd)
  finally:os.close(fd)
 finally:
  if os.path.exists(temp):os.unlink(temp)

def days(start,end):
 day=date.fromisoformat(start);stop=date.fromisoformat(end)
 while day<stop:
  if day.weekday()<5:yield day.isoformat()
  day+=timedelta(days=1)

def windows(start,end,boundaries):
 cuts={start,end}
 cuts.update(x for x in boundaries if start<x<end)
 cuts.update(f'{year}-01-01' for year in range(int(start[:4])+1,int(end[:4])+1) if start<f'{year}-01-01'<end)
 cuts=sorted(cuts)
 return [(sample[0],sample[-1]) for a,b in zip(cuts,cuts[1:]) if (sample:=list(days(a,b)))]

def compatible_window(period,start,end,boundaries):
 a,b=period['start_inclusive'],period['end_inclusive']
 return start<=a<=b<end and not any(a<cut<=b for cut in boundaries)

@contextmanager
def executor(root):
 path=root/'storage/catalog/operations/research-executor.lock'
 with path.open('a+b') as lock:
  deadline=time.monotonic()+30
  while True:
   try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);break
   except BlockingIOError:
    if STOP:raise InterruptedError('Preparation stopped while waiting for the research executor')
    if time.monotonic()>=deadline:raise RuntimeError('Research executor remained busy; preparation paused')
    time.sleep(.1)
  try:yield
  finally:fcntl.flock(lock,fcntl.LOCK_UN)

def capacity(root):
 volume=os.statvfs(root);boot=os.statvfs('/var/lib/gambit-backup')
 free=volume.f_bavail*volume.f_frsize
 used=(volume.f_blocks-volume.f_bfree)*volume.f_frsize
 boot_free=boot.f_bavail*boot.f_frsize
 if free<20*1024**3 or volume.f_favail<1_000_000:
  raise RuntimeError('Preparation paused at data-volume reserve (20 GiB / 1 million file slots)')
 if boot_free<used+10*1024**3:
  raise RuntimeError('Preparation paused to retain a full backup-staging copy plus 10 GiB on boot disk')
 return {'data_free_bytes':free,'data_free_inodes':volume.f_favail,'backup_staging_free_bytes':boot_free}

def verify_preflight(bundle,profile,bundle_sha,expected_pairs):
 receipt=json.loads((bundle/'target-preflight-receipt.json').read_text())
 raw=(bundle/'cloud-verify-all.jsonl').read_bytes()
 if (receipt.get('verification_log_sha256')!=hashlib.sha256(raw).hexdigest()
     or receipt.get('bundle_sha256')!=bundle_sha
     or receipt.get('source_snapshots')!=profile['target_selection']['source_snapshots']
     or receipt.get('target_materializations')!=profile['target_selection']['materializations']
     or receipt.get('knowledge_cutoff')!=profile['target_selection']['knowledge_cutoff']
     or receipt.get('success') is not True):
  raise RuntimeError('Numerical preflight receipt differs from exact approved inputs')
 audit=[json.loads(line) for line in raw.splitlines()]
 verified={(v['instrument'],v['horizon']) for v in audit if v.get('kind')=='target_verified'}
 if verified!=expected_pairs or not audit or audit[-1].get('kind')!='done':
  raise RuntimeError('Full exact-source/Target numerical preflight is incomplete')


def inventory_candidates(root,selected,batch,cutoff,starts,end,boundaries):
 from data.fx_feature_contracts import validate_record
 existing=defaultdict(list)
 for path in sorted((root/'storage/catalog/feature_store').glob('*/manifest.json')):
  value=json.loads(path.read_text())
  if value.get('schema_version')!='0.6.0':continue
  validate_record(value)
  if path.parent.name!=value['id']:raise RuntimeError('Materialization path differs')
  entry=selected.get(value['definition']['id'])
  if entry is None:continue
  key=value['input_key'];symbol=entry['instrument_id']
  if (value['definition']!=entry['historical_feature'] or key['source_snapshots']!=[entry['source_snapshot']]
      or key['batch_policy']!=batch or key['knowledge_cutoff']!=cutoff
      or not compatible_window(key['period'],starts[symbol],end,boundaries[symbol])):continue
  # Independent replay reloads the exact manifest. Retain locators only.
  existing[value['definition']['id']].append(value['id'])
 return existing


def main():
 parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True)
 parser.add_argument('--bundle',type=Path,required=True);parser.add_argument('--expected-bundle-sha256',required=True)
 mode=parser.add_mutually_exclusive_group()
 mode.add_argument('--dry-run',action='store_true',help='Verify frozen metadata only; never publish observations')
 mode.add_argument('--apply',action='store_true',help='Publish approved discovery observations after all guards pass')
 parser.add_argument('--max-windows',type=int)
 args=parser.parse_args();root=args.root.resolve();bundle=args.bundle.resolve()
 if args.max_windows is not None and args.max_windows<1:parser.error('--max-windows must be positive')
 if root!=Path('/srv/gambit/research_platform') and os.environ.get('GAMBIT_ISOLATED_TEST')!='1':
  raise RuntimeError('Cloud authority required')
 sys.path.insert(0,str(root/'src'))
 from data.transformations.identity import reference,digest
 from data.feature_store import FeatureStore,PublicationError
 from data.targets.store import TargetStore
 from data.targets.fx import _approved_policy,_price_snapshot
 from data.fx_feature_store import prepare_fx_feature,read_fx_materialization
 from data.reusable_features import reusable_recipe_mapping_context
 from data.scopes import resolve_scope
 from data.verified_inputs import execution_inputs,phase_inputs
 from research.contracts import load_profile,ref
 from research.inputs import _profile,_structural_start,_chunks
 from runtime.research_jobs import ResearchJobs,ACTIVE,implementation
 names=('preparation-manifest.json','instrument-preparation-matrix.json','scope-coverage-matrix.json')
 payloads={name:(bundle/name).read_bytes() for name in names}
 hashes={n:hashlib.sha256(b).hexdigest() for n,b in payloads.items()}
 if hashlib.sha256(json.dumps(hashes,sort_keys=True,separators=(',',':')).encode()).hexdigest()!=args.expected_bundle_sha256:
  raise RuntimeError('Frozen preparation bundle differs')
 manifest,matrix,scopes=[json.loads(payloads[n]) for n in names]
 profile=_profile(load_profile(root));store=TargetStore(root)
 if ref(profile)!=manifest['research_spec'] or profile['periods']!=manifest['periods']:
  raise RuntimeError('Research policy differs from the approved preparation manifest')
 if profile['target_selection']['knowledge_cutoff']!=manifest['knowledge_cutoff']:
  raise RuntimeError('Frozen knowledge cutoff differs')
 if len(matrix)!=2279 or len(manifest['recipes'])!=53 or len(scopes)!=61:
  raise RuntimeError('Approved population size differs')
 config=json.loads((root/'config/fx_retrospective_completion.json').read_text())
 if config.get('knowledge_cutoff')!=manifest['knowledge_cutoff']:raise RuntimeError('Completion configuration cutoff differs')
 batch=_approved_policy(store,config['return_policy'])
 if batch['horizons']!=manifest['horizons']:raise RuntimeError('Target horizon policy differs')
 mappings,project=reusable_recipe_mapping_context(root)
 by_instrument=defaultdict(list);recipe_refs={r['reference']['id']:r['reference'] for r in manifest['recipes']}
 starts={};boundaries=defaultdict(set)
 scope_refs={s['reference']['id']:s['reference'] for s in manifest['scopes']}
 for entry in scopes:
  actual=resolve_scope(root,entry['scope_id'],scope_refs[entry['scope_id']]['version'])
  if (actual['reference']!=scope_refs[entry['scope_id']] or actual['membership_snapshot']!=entry['membership_snapshot']
      or actual['members']!=entry['members'] or actual['kind']!=entry['kind']):
   raise RuntimeError('Scope membership changed: '+entry['scope_id'])
  if entry['kind']=='instrument':starts[entry['scope_id']]=entry['structural_p1_start']
  else:
   for symbol in entry['members']:boundaries[symbol].add(entry['structural_p1_start'])
 seen=set()
 for entry in matrix:
  symbol=entry['instrument_id'];feature_ref=entry['historical_feature'];recipe_ref=entry['recipe']
  key=(symbol,recipe_ref['id'])
  if key in seen or recipe_refs.get(recipe_ref['id'])!=recipe_ref:raise RuntimeError('Duplicate or unexpected binding')
  seen.add(key);feature=store.resolve(feature_ref);mapping=mappings[feature_ref['id']]
  if mapping['instrument_id']!=symbol or reference(project(feature))!=recipe_ref:raise RuntimeError('Recipe mapping changed')
  if (entry['source_snapshot']!=profile['target_selection']['source_snapshots'][symbol]
      or entry['target_materializations']!=profile['target_selection']['materializations'][symbol]):
   raise RuntimeError('Source/Target pins changed')
  by_instrument[symbol].append(entry)
 for symbol,entries in by_instrument.items():
  if len(entries)!=53:raise RuntimeError('Missing recipe configuration')
  snapshot,_=_price_snapshot(store,entries[0]['source_snapshot'],batch,verify_rows=False)
  if snapshot['body']['instrument_id']!=symbol or _structural_start(store,snapshot)!=starts[symbol]:
   raise RuntimeError('Structural source coverage changed')
  if any(mappings[e['historical_feature']['id']]['source_view']!=snapshot['body']['definition'] for e in entries):
   raise RuntimeError('Recipe source view differs from current research snapshot')
 for entry in scopes:
  if entry['structural_p1_start']!=max(starts[s] for s in entry['members']):raise RuntimeError('Universe start differs')
 # Stable operation namespace binds all exact recipes, inputs, policies and phase.
 # Each numeric cache key still includes its individual Feature and snapshot;
 # publisher and independent verifier retain separate cache entries.
 end=profile['periods']['P1']['end_exclusive']
 program={'kind':'momentum_discovery_preparation_v1','inputs':hashes,'profile':ref(profile),
          'phase':'P1','script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
          'application_implementation':implementation(),'research_executed':False}
 program_id=digest(program);out=bundle/'progress'/program_id
 source_paths=[p for p in (root/'src').rglob('*.py')]
 source_state={str(p):(p.stat().st_ino,p.stat().st_mtime_ns,p.stat().st_ctime_ns,p.stat().st_size) for p in source_paths}
 def stable_code():
  for name,before in source_state.items():
   st=Path(name).stat()
   if (st.st_ino,st.st_mtime_ns,st.st_ctime_ns,st.st_size)!=before:raise RuntimeError('Application changed; restart preparation under reviewed release')
  if ref(load_profile(root))!=manifest['research_spec']:raise RuntimeError('Research profile changed')
 summary={'program_id':program_id,'program':program,'status':'planned','bindings':2279,'registered_recipes':53,
          'scope_count':61,'P2':'deferred pending real P1 admission','research_executed':False}
 if not args.apply:print(json.dumps(summary));return
 if os.environ.get('GAMBIT_FX_LINEAGE_STORAGE')!='packed_v1':raise RuntimeError('Packed writer must be explicitly enabled')
 verify_preflight(bundle,profile,args.expected_bundle_sha256,{(s,h) for s in starts for h in manifest['horizons']})
 signal.signal(signal.SIGTERM,stopping);signal.signal(signal.SIGINT,stopping)
 completed=0;published=0;receipts=[]
 selected_entries={e['historical_feature']['id']:e for entries in by_instrument.values() for e in entries}
 def state(status,**details):
  value=dict(summary,status=status,updated_at=datetime.now(timezone.utc).isoformat(),completed_bindings=completed,
             new_windows_this_execution=published,**details)
  atomic(out/'status.json',value);print(json.dumps(value),flush=True)
 jobs=ResearchJobs(root)
 def idle():
  for path in (root/'storage/catalog/operations/jobs').glob('*.json'):
   job=jobs._read_job(path.stem)
   if job and job['status'] in ACTIVE:raise RuntimeError('Research queued/running; preparation paused without interrupting it')
 try:
  with executor(root):
   idle();stable_code();capacity(root)
   # Inventory once. Each candidate is independently replayed before reuse.
   existing=inventory_candidates(root,selected_entries,batch,manifest['knowledge_cutoff'],starts,end,boundaries)
   atomic(out/'program.json',program);state('preparing')
  for symbol in sorted(by_instrument):
   # Check exact Target bytes again; numerical replay is certified by the
   # pinned preflight receipt. A receipt never substitutes for current integrity.
   with executor(root):
    idle();stable_code();target_store=TargetStore(root)
    for binding in profile['target_selection']['materializations'][symbol].values():
     target_store.verify_closure([target_store.resolve(binding)])
    del target_store
   period={'start_inclusive':starts[symbol],'end_exclusive':end}
   context_plan={'plan_id':program_id+'_'+symbol,'periods':{'P1':period}}
   # The longest verified source working set exceeds the research default of
   # 128 MiB. A bounded 512 MiB cache prevents repeatedly re-verifying that same
   # snapshot between annual windows. Production execution also has a 2 GiB
   # process limit; this does not change normal research worker cache budgets.
   with execution_inputs(root,program['application_implementation'],max_bytes=512*1024*1024) as context:
    with phase_inputs(root,context_plan,'P1'):
     for entry in sorted(by_instrument[symbol],key=lambda r:r['recipe']['id']):
      covered=set();results=[];unavailable=[];counts=Counter()
      def accept(item,reused):
       value=item['manifest'];key=value['input_key']
       if (value['definition']!=entry['historical_feature'] or key['source_snapshots']!=[entry['source_snapshot']]
           or key['batch_policy']!=batch or key['knowledge_cutoff']!=manifest['knowledge_cutoff']
           or not compatible_window(key['period'],starts[symbol],end,boundaries[symbol])):
        raise RuntimeError('Prepared materialization violates exact input/phase/scope boundaries')
       sample=item['observations'];dates={r['reference_time'] for r in sample}
       if covered & dates:return  # prefer the first verified complete covering window
       covered.update(dates);counts.update(r['status'] for r in sample)
       results.append({'reference':reference(value),'period':key['period'],'row_count':len(sample),
                       'status_counts':dict(Counter(r['status'] for r in sample)),'reused':reused})
      for identifier in existing.get(entry['historical_feature']['id'],[]):
       with executor(root):
        idle();stable_code();accept(read_fx_materialization(root,identifier,research=True),True)
      for a,b in windows(starts[symbol],end,boundaries[symbol]):
       missing=sorted(set(days(a,(date.fromisoformat(b)+timedelta(days=1)).isoformat()))-covered)
       for lo,hi in _chunks(missing):
        if STOP or (args.max_windows is not None and published>=args.max_windows):
         state('paused',reason='bounded run or requested stop');return
        with executor(root):
         idle();stable_code();space=capacity(root)
         state('preparing',instrument=symbol,recipe=entry['recipe'],window=[lo,hi],capacity=space)
         try:
          saved=prepare_fx_feature(root,entry['historical_feature'],price_snapshot=entry['source_snapshot'],
            batch_policy=batch,knowledge_cutoff=manifest['knowledge_cutoff'],start=lo,end=hi)
         except PublicationError as exc:
          if str(exc) not in ('No valid FX Feature observations; recipe remains registered only','Output interval has no scheduled weekdays'):raise
          unavailable.append({'start':lo,'end':hi,'reason':'NO_VALID_FEATURE_OBSERVATIONS'});continue
         item=read_fx_materialization(root,saved['materialization']['id'],research=True);accept(item,saved['reused'])
         published+=not saved['reused']
         atomic(out/'partial.json',{'binding':entry,'materializations':results,'unavailable':unavailable})
      receipt={'binding':entry,'phase':'P1','period':period,'materializations':results,'unavailable':unavailable,
               'status_counts':dict(counts),'prepared_rows':len(covered),'registered':True,'research_validation':'not evaluated',
               'P2':'deferred pending real P1 admission'}
      with executor(root):
       atomic(out/'bindings'/symbol/(entry['recipe']['id']+'.json'),receipt)
       completed+=1;receipts.append(receipt);state('preparing',instrument=symbol,cache_counts=dict(context.counts),
         cache_seconds=dict(context.seconds),cache_retained_bytes=context.bytes,cache_limit_bytes=context.max_bytes)
  with executor(root):
   scope_report=[]
   for scope in scopes:
    members=[]
    for symbol in scope['members']:
     entries=[r for r in receipts if r['binding']['instrument_id']==symbol]
     members.append({'instrument':symbol,'recipe_count':len(entries),'rows_by_recipe':[
      {'recipe':r['binding']['recipe'],'prepared_rows':sum(m['row_count'] for m in r['materializations']
         if m['period']['start_inclusive']>=scope['structural_p1_start']),
       'valid_rows':sum(m['status_counts'].get('valid',0) for m in r['materializations'] if m['period']['start_inclusive']>=scope['structural_p1_start']),
       'unavailable_windows':[w for w in r['unavailable'] if w['end']>=scope['structural_p1_start']]} for r in entries]})
    scope_report.append(dict(scope,members_prepared=members,feature_preparation='completed with explicit unavailable windows',
      paired_sample_and_research_gates='not evaluated; evaluated by normal Submit preparation/research',research_validation='not evaluated'))
   atomic(out/'scope-coverage.json',scope_report);state('completed')
 except BaseException as exc:
  state('paused',reason=type(exc).__name__+': '+str(exc));raise

if __name__=='__main__':main()
