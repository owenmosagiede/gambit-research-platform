"""Durable local Submit worker. No computation occurs without a recorded request.

Immutable submissions/events and scientific records are authority. Job JSON files
are replaceable projections; OS locks prevent competing local writers/workers.
"""
from pathlib import Path
from copy import deepcopy
from datetime import datetime,timezone
import hashlib, json, threading, uuid, logging
from research.contracts import (normalize_submission,request_id,canonical,digest,ref,
    profile_blockers,load_profile,ResearchError,ResearchConflict,ResearchBlocked,HORIZONS)
from research.store import ResearchStore,inside,install_bytes,read_json,lock

ACTIVE={'queued','resolving','preparing','p1','p2'}
TERMINAL={'blocked','failed','cancelled','succeeded'}
class Cancelled(Exception):pass

def now():return datetime.now(timezone.utc).isoformat(timespec='microseconds')

def implementation():
    base=Path(__file__).resolve().parents[1]
    files={}
    # Pin input preparation and source contracts as well as numerical kernels.
    # A code-only adapter change must never reuse a result from different code.
    for folder in ('research','runtime','data','contracts'):
        for p in sorted((base/folder).rglob('*.py')):
            files[p.relative_to(base).as_posix()]=hashlib.sha256(p.read_bytes()).hexdigest()
    return {'profile':'research_execution_0.8','files':files,'numeric_environment':{'python':__import__('sys').version},'fingerprint':digest(files)}

class ResearchJobs:
    def __init__(self,root,*,adapter=None,kernels=None,start_worker=False):
        self.root=Path(root).resolve();self.store=ResearchStore(root)
        self.adapter=adapter;self.kernels=kernels;self.stop_event=threading.Event();self.wake=threading.Event();self.thread=None
        self.supervisor=None;self.health_lock=threading.RLock()
        self.worker_state='stopped';self.worker_error=None;self.restarts=0
        self.session_id=str(uuid.uuid4());self.diagnostic_sequence=0;self.last_diagnostic=None
        if start_worker:self.start()
    RESTART_DELAYS=(1,2,4)

    def _diagnostic(self,code,**context):
        """Operational evidence only; never a scientific result or disposition."""
        self.diagnostic_sequence+=1
        event={'code':code,'at':now(),'session_id':self.session_id,
               'sequence':self.diagnostic_sequence,**context}
        self.last_diagnostic=event
        path=inside(self.root,'storage/catalog/operations/worker_events/'+self.session_id+
                    '/'+str(self.diagnostic_sequence)+'.json')
        try:install_bytes(path,canonical(event)+b'\n')
        except Exception as exc:
            self.last_diagnostic=dict(event,diagnostic_write_error=type(exc).__name__)
            logging.getLogger(__name__).exception('Could not persist worker diagnostic')

    def _worker_entry(self):
        try:
            self._loop()
            if not self.stop_event.is_set():raise RuntimeError('Worker returned unexpectedly')
        except BaseException as exc:
            with self.health_lock:
                self.worker_error={'type':type(exc).__name__,'message':str(exc)[:600]}
                self.worker_state='recovering'

    def _launch_worker(self):
        with self.health_lock:
            self.worker_state='starting';self.worker_error=None
            self.thread=threading.Thread(target=self._worker_entry,daemon=True,name='research-worker')
            self.thread.start()

    def start(self):
        with self.health_lock:
            if self.thread is not None:return # one bounded restart budget per process instance
            self._launch_worker()
            self.supervisor=threading.Thread(target=self._supervise,daemon=True,name='research-supervisor')
            self.supervisor.start()

    def _supervise(self):
        try:
            while not self.stop_event.is_set():
                self.thread.join(timeout=.1)
                if self.thread.is_alive():continue
                if self.stop_event.is_set():break
                self._diagnostic('WORKER_TERMINATED',error=self.worker_error)
                if self.restarts>=len(self.RESTART_DELAYS):
                    with self.health_lock:self.worker_state='failed'
                    self._diagnostic('WORKER_RETRIES_EXHAUSTED',restarts=self.restarts)
                    return
                delay=self.RESTART_DELAYS[self.restarts];self.restarts+=1
                with self.health_lock:self.worker_state='recovering'
                self._diagnostic('WORKER_RESTART_SCHEDULED',attempt=self.restarts,delay_seconds=delay)
                if self.stop_event.wait(delay):break
                self._launch_worker()
        except BaseException as exc:
            with self.health_lock:
                self.worker_state='failed'
                self.worker_error={'type':type(exc).__name__,'message':str(exc)[:600]}
            self._diagnostic('SUPERVISOR_FAILED',error=self.worker_error)

    def health(self):
        with self.health_lock:
            alive=bool(self.thread and self.thread.is_alive())
            watched=bool(self.supervisor and self.supervisor.is_alive())
            healthy=alive and watched and not self.stop_event.is_set() and self.worker_state in ('idle','running')
            state=self.worker_state
            if not healthy and state in ('idle','running'):state='failed'
            return {'healthy':healthy,'state':state,'worker_alive':alive,'supervisor_alive':watched,
                    'restart_count':self.restarts,'restart_limit':len(self.RESTART_DELAYS),
                    'last_error':deepcopy(self.worker_error),'last_diagnostic':deepcopy(self.last_diagnostic)}

    def operational_status(self):
        directory=inside(self.root,'storage/catalog/operations/submission_incidents')
        incidents=[read_json(p) for p in sorted(directory.glob('*.json'))] if directory.exists() else []
        return {'worker':self.health(),'submission_incidents':incidents}

    def close(self):
        self.stop_event.set();self.wake.set()
        if self.supervisor:self.supervisor.join(timeout=2)
        if self.thread:self.thread.join(timeout=2)
        with self.health_lock:self.worker_state='stopped'

    def _incident_path(self,path):
        relative=path.relative_to(self.root).as_posix()
        return inside(self.root,'storage/catalog/operations/submission_incidents/'+digest(relative)+'.json')

    def _incident(self,path,exc):
        """Quarantine by location, retain original bytes and publish once under writer lock."""
        destination=self._incident_path(path)
        if destination.exists():return read_json(destination)
        relative=path.relative_to(self.root).as_posix();rid=None
        try:rid=request_id(path.stem)
        except ResearchError:pass
        raw=None;read_error=None
        try:raw=path.read_bytes()
        except OSError as error:read_error=type(error).__name__
        envelope_id=None
        if raw is not None:
            try:envelope_id=request_id(json.loads(raw).get('request_id'))
            except (ValueError,TypeError,AttributeError,ResearchError):pass
        sha=hashlib.sha256(raw).hexdigest() if raw is not None else None
        evidence=None
        if raw is not None:
            evidence='storage/catalog/operations/submission_evidence/'+sha+'.bin'
            install_bytes(inside(self.root,evidence),raw)
        record={'id':'OPINCIDENT_'+digest(relative),'kind':'submission_integrity_failure',
                'code':'SUBMISSION_INTEGRITY_FAILURE','request_id':rid,'envelope_request_id':envelope_id,
                'storage_path':relative,'evidence_path':evidence,'evidence_sha256':sha,
                'read_error':read_error,'error_type':type(exc).__name__,'diagnostic':str(exc)[:600],
                'message':'Submission evidence could not be verified. It is quarantined; no further research will run for this request.',
                'created_at':now(),'resumable':False}
        install_bytes(destination,canonical(record)+b'\n')
        return record

    def _incident_job(self,record):
        return {'request_id':record['request_id'],'status':'failed','stage':'operational integrity failure',
                'message':record['message'],'operational_failure':True,'resumable':False,
                'incident':record,'blockers':[{'code':record['code'],'message':record['message']+' Incident '+record['id']}],
                'mode':None,'progress':{'completed':0,'total':0},'horizons':[],'results':[],
                'created_at':record['created_at'],'updated_at':record['created_at']}

    def _submission_path(self,rid):return inside(self.root,'storage/catalog/submissions/'+request_id(rid)+'.json')
    def _job_path(self,rid):return inside(self.root,'storage/catalog/operations/jobs/'+request_id(rid)+'.json')
    def _submission(self,rid):
        record=read_json(self._submission_path(rid))
        if type(record) is not dict or record.get('schema_version')!='0.8.0':raise ResearchError('Invalid submission envelope')
        required={'request_id','intent','intent_fingerprint','research_spec','implementation','created_at','record_sha256'}
        if not required.issubset(record):raise ResearchError('Incomplete submission envelope')
        if type(record['intent']) is not dict or type(record['implementation']) is not dict or not isinstance(record['created_at'],str):raise ResearchError('Invalid submission envelope fields')
        normalize_submission(dict(record['intent'],request_id=rid))
        impl=record['implementation']
        if not {'profile','files','numeric_environment','fingerprint'}.issubset(impl) or type(impl['files']) is not dict or impl['fingerprint']!=digest(impl['files']):raise ResearchError('Invalid frozen implementation')
        try:datetime.fromisoformat(record['created_at'])
        except ValueError:raise ResearchError('Invalid submission creation time')
        if record['research_spec'] is not None and type(record['research_spec']) is not dict:raise ResearchError('Invalid frozen Research Spec')
        if record['request_id']!=rid or record['intent_fingerprint']!=digest(record['intent']):raise ResearchError('Submission integrity conflict')
        if record['record_sha256']!=digest({k:v for k,v in record.items() if k!='record_sha256'}):raise ResearchError('Submission checksum conflict')
        return record
    def _event_snapshot(self):
        """Read history once for a multi-job view; each chain is still verified."""
        groups={}
        directory=inside(self.root,'storage/catalog/attempts')
        for p in directory.glob('*/events/RESEVENT_*.json'):
            try:
                event=read_json(p)
                rid=event.get('request_id')
                request_id(rid)
            except (ValueError, TypeError, AttributeError, OSError) as exc:
                # Preserve fail-closed history verification, but let callers
                # quarantine submissions rather than crashing the worker loop.
                groups.setdefault(None,[]).append(p.name + ': ' + str(exc)[:200])
                continue
            groups.setdefault(rid,[]).append((p.stem,event))
        return groups
    def _events(self,rid,snapshot=None):
        snapshot=self._event_snapshot() if snapshot is None else snapshot
        if snapshot.get(None):raise ResearchError('Unreadable execution event: ' + snapshot[None][0])
        entries=snapshot.get(rid,[])
        events=[]
        for name,event in entries:
            if name!='RESEVENT_'+digest(event):raise ResearchError('Execution event checksum mismatch')
            events.append(event)
        events.sort(key=lambda e:e['sequence'])
        previous=None
        for i,e in enumerate(events):
            if e['sequence']!=i or e['previous']!=previous:raise ResearchError('Execution event chain conflict')
            previous=digest(e)
        return events
    def _read_job(self,rid,snapshot=None):
        self._submission(rid)
        p=self._job_path(rid)
        # Verify the projection's last event cheaply; recover/reconcile from the
        # append-only chain after a missing/partial projection or interrupted update.
        events=self._events(rid,snapshot)
        if not events:return None
        expected=dict(events[-1]['job'],sequence=events[-1]['sequence'],event_sha256=digest(events[-1]))
        return expected
    def get(self,rid, *, _snapshot=None):
        path=self._submission_path(rid)
        with lock(self.root,'research-writer'):
            from runtime.experiment_identity import IdentityIndex
            index=IdentityIndex(self)
            journal=index.journal(rid)
            if journal:
                try:return self._received(journal,index)
                except Exception as exc:
                    canonical_path=self._submission_path(journal['canonical_request_id'])
                    return self._incident_job(self._incident(canonical_path,exc))
            incident=self._incident_path(path)
            if incident.exists():return self._incident_job(read_json(incident))
            try:job=self._read_job(rid,_snapshot)
            except Exception as exc:
                if not path.exists() and not self._job_path(rid).exists():raise
                return self._incident_job(self._incident(path,exc))
        if job is None:raise ResearchError('Submission has no recorded event')
        value=self.public(job);value['runtime']=self.health()
        return value
    @staticmethod
    def queue_key(job):
        # Continue interrupted execution before starting waiting work. Old records
        # have no queued_at; their immutable creation time remains the fallback.
        return (0 if job['status'] in ACTIVE-{'queued'} else 1,
                job.get('queued_at',job['created_at']),job['request_id'])

    def list_jobs(self):
        """Verified metadata only; never resolve prices or prepare research."""
        directory=inside(self.root,'storage/catalog/submissions')
        paths={p.name:p for p in directory.glob('*.json')}
        for p in inside(self.root,'storage/catalog/operations/jobs').glob('*.json'):
            paths.setdefault(p.name,directory/p.name)
        items=[];issues=[]
        for path in sorted(paths.values()):
            try:
                rid=request_id(path.stem);job=self.get(rid)
                intent=None
                if not job.get('operational_failure'):
                    intent=deepcopy(self._submission(rid)['intent'])
                items.append({'job':job,'intent':intent})
            except Exception:
                # Never hide an unreadable record or turn it into a success.
                issues.append({'request_id':path.stem,'message':'Queue record could not be verified.'})
        items.sort(key=lambda item:(0 if item['job']['status'] in ACTIVE else 1,
                   self.queue_key(item['job'])))
        waiting=0
        for item in items:
            if item['job']['status']=='queued':waiting+=1;item['queue_position']=waiting
            else:item['queue_position']=None
        return {'items':items,'issues':issues,'worker':self.health(),
                'execution':'sequential','ordering':'queued_at_then_request_id'}

    def public(self,job):
        value={k:deepcopy(v) for k,v in job.items() if k not in ('event_sha256','cancel_requested')}
        # Compatibility is presentation metadata, never a rewrite of frozen history.
        if job['status'] in ('blocked','failed','cancelled'):
            reason=self._resume_blocker(job['request_id'])
            value['resumable']=reason is None
            if reason:value['resume_blocker']=reason
        return value
    def _resume_blocker(self,rid):
        if self._submission(rid)['implementation'] != implementation():
            return {'code':'IMPLEMENTATION_CHANGED','message':
                'This submission uses an older code version and cannot resume. Recovery needs a compatible execution release. Reconcile the release before retrying; the original record is preserved.'}
        return None
    def _save(self,job):
        rid=job['request_id'];events=self._events(rid);sequence=len(events)
        body={k:v for k,v in job.items() if k not in ('sequence','event_sha256')};body['updated_at']=now()
        event={'schema_version':'0.8.0','request_id':rid,'sequence':sequence,
               'previous':digest(events[-1]) if events else None,'job':body}
        install_bytes(inside(self.root,'storage/catalog/attempts/'+body['attempt_id']+'/events/RESEVENT_'+digest(event)+'.json'),canonical(event)+b'\n')
        projection=dict(body,sequence=sequence,event_sha256=digest(event))
        install_bytes(self._job_path(rid),canonical(projection)+b'\n',mutable=True)
        return projection
    def _update(self,rid,**changes):
        with lock(self.root,'research-writer'):
            job=self._read_job(rid)
            if job is None:raise ResearchError('Unknown execution')
            job.update(changes);return self._save(job)
    def _ensure_recorded(self, original):
        """Complete an interrupted publication without resolving new inputs."""
        rid=original['request_id']
        install_bytes(self._submission_path(rid),canonical(original)+b'\n')
        job=self._read_job(rid)
        if job is not None:return job
        job={'request_id':rid,'attempt_id':str(uuid.uuid4()),'status':'queued','stage':'recorded',
            'message':'Request recorded. Waiting for the research worker.', 'blockers':[],
            'progress':{'completed':0,'total':5},
            'horizons':[{'horizon':h,'p1_status':'pending','p2_status':'pending'} for h in HORIZONS],
            'results':[],'mode':None,'created_at':original['created_at'],
            'queued_at':original['created_at'],'cancel_requested':False}
        return self._save(job)

    def _received(self, journal, index):
        rid=journal['canonical_request_id']
        if not self._submission_path(rid).exists():
            authority=index.journal(rid)
            if not authority or not authority.get('submission'):
                raise ResearchConflict('Canonical experiment is missing; reconciliation required')
            original=authority['submission']
        else:original=self._submission(rid)
        if original['intent']!=journal['intent']:
            raise ResearchConflict('Receipt and experiment differ; reconciliation required')
        if index.entry(original)['scientific_identity']!=journal['scientific_identity']:
            raise ResearchConflict('Receipt scientific identity differs; reconciliation required')
        incident=self._incident_path(self._submission_path(rid))
        if incident.exists():return self._incident_job(read_json(incident))
        job=self._ensure_recorded(original)
        value=self.public(job)
        value['submission_receipt']=index.receipt(journal)
        value['intake_action']=('view_results' if job['status']=='succeeded' else
            'view_existing' if job['status'] in ACTIVE else 'recover_existing')
        self.wake.set()
        return value

    def submit(self,value, *, _batch_packet=None, _batch_duplicate_policy=None, _batch_reuse_id=None):
        from runtime.experiment_identity import IdentityIndex, freeze, scientific_key, save, release_reviews
        request=normalize_submission(value);rid=request.pop('request_id');intent=request
        with lock(self.root,'research-writer'):
            index=IdentityIndex(self)
            journal=index.journal(rid)
            if journal:
                if journal['intent']!=intent:raise ResearchConflict('This request ID already has different inputs')
                if _batch_packet is not None and scientific_key(_batch_packet)!=journal['scientific_identity']:
                    raise ResearchConflict('Batch request belongs to different frozen inputs')
                return self._received(journal,index),False
            path=self._submission_path(rid)
            incident=self._incident_path(path)
            if incident.exists():return self._incident_job(read_json(incident)),False
            if path.exists():
                try:original=self._submission(rid)
                except Exception as exc:return self._incident_job(self._incident(path,exc)),False
                if original['intent']!=intent:raise ResearchConflict('This request ID already has different inputs')
                if index.entry(original)['scientific_identity'] is None:
                    raise ResearchConflict('Historical inputs were not frozen; reconciliation required')
                if _batch_packet is not None and index.entry(original)['scientific_identity']!=scientific_key(_batch_packet):
                    raise ResearchConflict('Batch UUID belongs to different historical inputs')
                # Existing UUID retries retain their frozen legacy authority.
                return self.public(self._ensure_recorded(original)),False
            try:
                packet=freeze(self,intent,implementation())
            except ResearchBlocked:raise
            except (ValueError,KeyError,TypeError,OSError) as exc:
                raise ResearchBlocked(getattr(exc,'blockers',[{'code':'INPUT_METADATA_BLOCKED','message':str(exc)}])) from exc
            if _batch_packet is not None:
                if (_batch_packet['implementation']!=packet['implementation'] or
                        scientific_key(_batch_packet)!=scientific_key(packet)):
                    raise ResearchConflict('Exact inputs or implementation changed after preview; create a new preview')
                packet=deepcopy(_batch_packet)
            state=index.load()
            matches,ambiguous=index.matches(packet,state)
            if ambiguous:raise ResearchConflict('History or release compatibility requires reconciliation: '+', '.join(ambiguous))
            if _batch_reuse_id is not None and not any(r==_batch_reuse_id for r,_ in matches):
                raise ResearchConflict('Previewed duplicate is no longer reusable; no replacement was submitted')
            if _batch_reuse_id is not None and any(j and j['status'] not in ACTIVE|{'succeeded'} for _,j in matches):
                raise ResearchConflict('Previewed trial now needs recovery; review before dispatch')
            if matches and _batch_duplicate_policy=='reject':
                raise ResearchConflict('Exact matching experiment exists; review the existing trial')
            canonical_id=matches[0][0] if matches else rid
            original=None
            if not matches:
                original=dict(packet,schema_version='0.8.0',request_id=rid,
                    intent_fingerprint=digest(intent),created_at=now())
                original['record_sha256']=digest(original)
            journal={'schema':'experiment_intake_v1','request_id':rid,'canonical_request_id':canonical_id,
                'intent':intent,'scientific_identity':scientific_key(packet),'submission':original,
                'requested_implementation':packet['implementation'],'release_reviews':release_reviews(),'created_at':now()}
            # Durable reservation first. A crash at any following boundary can be
            # completed using this journal, with no re-resolution or replacement.
            index.invalidate()
            journal=save(index.journal_path(rid),journal)
            value=self._received(journal,index)
            if original:state['entries'][rid]=index.entry(original)
            index.publish(state)
            if original:value['intake_action']='created'
        return value,original is not None
    def cancel(self,rid):
        with lock(self.root,'research-writer'):
            request_id(rid)
            incident=self._incident_path(self._submission_path(rid))
            if incident.exists():raise ResearchConflict('Quarantined submissions cannot be resumed or changed')
            job=self._read_job(rid)
            if job['status'] in ACTIVE:
                job['cancel_requested']=True;job['message']='Cancellation requested; committed scientific evidence will be retained.'
                if job['status']=='queued':job.update(status='cancelled',stage='cancelled')
                job=self._save(job)
        return self.public(job)
    def resume(self,rid):
        with lock(self.root,'research-writer'):
            request_id(rid)
            incident=self._incident_path(self._submission_path(rid))
            if incident.exists():raise ResearchConflict('Quarantined submissions cannot be resumed or changed')
            job=self._read_job(rid)
            if job['status'] not in ('blocked','failed','cancelled'):raise ResearchConflict('Only blocked, failed or cancelled work can resume')
            reason=self._resume_blocker(rid)
            if reason:raise ResearchConflict(reason['message'])
            job.update(attempt_id=str(uuid.uuid4()),status='queued',stage='recorded',queued_at=now(),cancel_requested=False,blockers=[],message='Resume recorded with the original frozen inputs and Research Spec.')
            job=self._save(job)
        self.wake.set();return self.public(job)
    def _cancelled(self,rid):
        with lock(self.root,'research-writer'):job=self._read_job(rid)
        return self.stop_event.is_set() or job['cancel_requested']
    def _check(self,rid):
        if self._cancelled(rid):raise Cancelled()
    def _pending(self):
        from runtime.experiment_identity import IdentityIndex
        with lock(self.root,'research-writer'):
            index=IdentityIndex(self);state=index.load()
            if not state['issues']:
                for rid in state.get('pending',[]):
                    self._received(index.journal(rid),index)
                if state.get('pending'):
                    state['pending']=[];index.publish(state)
        directory=inside(self.root,'storage/catalog/submissions')
        paths={p.name:p for p in directory.glob('*.json')}
        # Missing accepted envelopes remain discoverable through their job projections.
        for p in inside(self.root,'storage/catalog/operations/jobs').glob('*.json'):
            paths.setdefault(p.name,directory/p.name)
        found=[]
        with lock(self.root,'research-writer'):
            snapshot=self._event_snapshot()
            for p in sorted(paths.values()):
                if self._incident_path(p).exists():continue
                try:
                    request_id(p.stem)
                    job=self._read_job(p.stem,snapshot)
                    original=self._submission(p.stem) if job is None else None
                except Exception as exc:
                    self._incident(p,exc);continue
                if job is None and not original.get('frozen_plan'):
                    self._incident(p,ResearchConflict('Historical inputs were not frozen; reconciliation required'))
                    continue
                if job is None:
                    # Recover after releasing the writer lock, through normal Submit.
                    found.append({'request_id':p.stem,'original':original})
                elif job['status'] in ACTIVE:found.append(job)
        for i,job in enumerate(found):
            if 'original' in job:
                self.submit(dict(job['original']['intent'],request_id=job['request_id']))
                found[i]=self._read_job(job['request_id'])
        if not found and not self.stop_event.is_set():
            from runtime.research_batches import ResearchBatches
            ResearchBatches(self).advance()
        return [job['request_id'] for job in sorted(found,key=self.queue_key)]

    def _worker_ready(self,state):
        with self.health_lock:
            recovering=self.worker_state=='starting' and self.restarts>0
            self.worker_state=state
        if recovering:self._diagnostic('WORKER_RECOVERED',attempt=self.restarts)

    def _loop(self):
        while not self.stop_event.is_set():
            # Idle is healthy; lock contention is explicit and never spawns a second executor.
            if (inside(self.root,'storage/catalog/submissions').exists() or inside(self.root,'storage/catalog/operations/jobs').exists()
                    or inside(self.root,'storage/catalog/operations/research_batches').exists()):
                with lock(self.root,'research-executor',nonblocking=True) as claimed:
                    if claimed:
                        pending=self._pending()
                        self._worker_ready('running' if pending else 'idle')
                        for rid in pending:
                            if self.stop_event.is_set():break
                            self._run(rid)
                        self._worker_ready('idle')
                    else:
                        with self.health_lock:self.worker_state='waiting_for_executor'
            else:self._worker_ready('idle')
            self.wake.wait(1);self.wake.clear()
    def run_pending_once(self):
        """Synchronous harness/worker entry; operates only on explicit submissions."""
        with lock(self.root,'research-executor',nonblocking=True) as claimed:
            if not claimed:return
            for rid in self._pending():self._run(rid)
    def _kernel(self,stage,rows,**kw):
        if self.kernels:return getattr(self.kernels,'run_'+stage.lower())(rows,**kw)
        if stage=='P1':
            from research.p1_discovery import run_p1
            return run_p1(rows,**kw)
        from research.p2_validation import run_p2
        return run_p2(rows,**kw)
    def _horizon(self,rid,h,**changes):
        with lock(self.root,'research-writer'):
            job=self._read_job(rid)
            for row in job['horizons']:
                if row['horizon']==h:row.update(changes)
            job['progress']={'completed':sum(r['p1_status'] not in ('pending','running') and r['p2_status'] not in ('pending','running') for r in job['horizons']),'total':5}
            self._save(job)
    def _trial(self,plan,prepared,phase,horizon,relationship,inputs,profile,impl,*,discovery_effect=None,discovery_trial=None):
        key={'relationship':ref(relationship),'stage':phase,'horizon':horizon,'research_spec':{'id':profile['id'],'version':profile['version'],'content_sha256':digest(profile)},
            'period':plan['periods'][phase],'prepared':{k:prepared[k] for k in ('phase','period','members')},
            'targets':[{ 'instrument':m['instrument_id'],'binding':m['targets'][str(horizon)]} for m in plan['members']],
            'implementation':ref(impl),'input_digest':digest({'rows':inputs['rows'],'lineage':inputs.get('lineage',[])}),
            'discovery_trial':discovery_trial,'discovery_effect':discovery_effect}
        existing=self.store.find('trial',key)
        if existing:
            for artifact in existing['body']['artifact_manifests']:self.store.verify_artifact(artifact)
            return existing
        exp=self.store.put('exposure',{'trial_key':digest(key)}, {'stage':phase,'period':plan['periods'][phase],
            'classification':profile['exposure_classification'],'sample_digest':digest(inputs),'relationship':ref(relationship)})
        kp=dict(profile['kernel'],structural_common_start=plan.get('structural_common_start'),
            window_start=plan['periods'][phase]['start_inclusive'],window_end_exclusive=plan['periods'][phase]['end_exclusive'])
        kwargs={'mode':plan['mode'],'horizon':horizon,'members':[m['instrument_id'] for m in plan['members']],
            'expected_direction':plan['intent']['expected_direction'],'profile':kp}
        if phase=='P2':kwargs['discovery_effect']=discovery_effect
        calculation=self._kernel(phase,inputs['rows'],**kwargs)
        artifacts=self.store.artifact(key,dict(calculation.get('artifacts',{}),coverage=inputs.get('coverage',{}),lineage=inputs.get('lineage',[])))
        if plan.get('application_class')=='external_stored_feature_to_individual_ts':
            coverage=inputs['coverage'][0]
            calculation['sample']=dict(calculation.get('sample',{}),external_alignment={
                k:coverage[k] for k in ('aligned_weekday_rows','distinct_source_update_count','valid_distinct_source_update_count')})
        body={k:v for k,v in calculation.items() if k!='artifacts'}
        body.update(stage=phase,artifact_manifests=[ref(artifacts)],exposure=ref(exp),metrics=calculation.get('metrics',{}),sample=calculation.get('sample',{}))
        return self.store.put('trial',key,body)
    def _link(self,relationship,p1,admission,p2=None,validation=None):
        body={'relationship':ref(relationship),'trial_results':[ref(p1)]+([ref(p2)] if p2 else []),
            'admission_results':[ref(admission)],'validation_results':[ref(validation)] if validation else []}
        return self.store.put('link',body,body)
    def _record_access(self,rid,plan,phase,horizon):
        with lock(self.root,'research-writer'):job=self._read_job(rid)
        self.store.put('exposure',{'request_id':rid,'attempt_id':job['attempt_id'],'phase':phase,'horizon':horizon},
            {'event':'sample_access_started','plan_id':plan['plan_id'],'period':plan['periods'][phase],
             'classification':plan['profile']['exposure_classification'],
             'description':'Access intent recorded before loading; interruption means exposure is possible, not certified untouched.'})
    def _run(self,rid):
        from data.verified_inputs import execution_inputs
        # Lifetime is one frozen submission attempt, never the web session.
        with execution_inputs(self.root, implementation()):
            return self._execute(rid)

    def _execute(self,rid):
        try:
            self._check(rid);submission=self._submission(rid);profile=submission['research_spec']
            self._update(rid,status='resolving',stage='preflight',message='Verifying the frozen Research Spec and exact input bindings.')
            blockers=profile_blockers(profile)
            if blockers:raise ResearchBlocked(blockers)
            if submission['implementation']!=implementation():raise ResearchBlocked([{'code':'IMPLEMENTATION_CHANGED','message':'The installed implementation changed. Reconcile execution compatibility; the original request retains its code fingerprint.'}])
            adapter=self.adapter
            if adapter is None:
                from research import inputs as adapter
            with lock(self.root,'research-writer'):previous=self._read_job(rid)
            if previous.get('plan'):
                planrecord=self.store.resolve('plan',previous['plan']);plan=planrecord['body']
            else:
                plan=submission.get('frozen_plan') or adapter.resolve_plan(self.root,submission['intent'],profile)
                planrecord=self.store.put('plan',plan,plan)
            if 'feature_application' in submission and plan.get('feature_application')!=submission['feature_application']:
                raise ResearchBlocked([{'code':'APPLICATION_CHANGED','message':'Resolved application differs from the frozen submission contract.'}])
            impl=self.store.put('implementation',submission['implementation'],submission['implementation'])
            self._update(rid,mode=plan['mode'],plan=ref(planrecord),status='preparing',stage='P1 preparation',message='Preparing only required discovery Feature coverage.')
            def progress(*args,**kwargs):self._check(rid)
            prepared=adapter.prepare_phase(self.root,plan,'P1',progress=progress,cancelled=lambda:self._cancelled(rid))
            self._check(rid);pending=[];links=[]
            for horizon in HORIZONS:
                self._check(rid);self._update(rid,status='p1',stage='P1',message=f'P1 {plan["mode"]}: {horizon} scheduled weekdays.')
                self._horizon(rid,horizon,p1_status='running')
                relation={'recipe':plan['recipe'],'scope':plan['scope'],'mode':plan['mode'],'target_family':'price_return','horizon':horizon,
                    'horizon_unit':'scheduled_weekdays','members':[m['instrument_id'] for m in plan['members']],
                    'targets':[m['targets'][str(horizon)]['definition'] for m in plan['members']],
                    'expected_direction':plan['intent']['expected_direction']}
                if 'feature_application' in plan:
                    relation['feature_application']=plan['feature_application']
                relationship=self.store.put('relationship',relation,relation)
                self._record_access(rid,plan,'P1',horizon)
                data=adapter.load_phase(self.root,plan,prepared,'P1',horizon)
                self._check(rid)
                p1=self._trial(plan,prepared,'P1',horizon,relationship,data,profile,impl)
                decision=p1['body']['admission']
                admission=self.store.put('admission',{'trial':ref(p1)}, {'trial':ref(p1),'relationship':ref(relationship),'decision':decision,
                    'evidence':p1['body'].get('evidence',{}),'reason_codes':p1['body'].get('reason_codes',[])})
                link=self._link(relationship,p1,admission);links.append(ref(link))
                self._horizon(rid,horizon,p1_status=decision,p2_status='pending' if decision=='admitted' else 'not_admitted')
                effect=p1['body']['metrics'].get('primary_effect')
                if decision=='admitted':
                    direction=1 if plan['intent']['expected_direction']=='POSITIVE' else -1
                    if effect is not None and float(effect)*direction<=0:
                        validation=self.store.put('validation',{'discovery':ref(p1),'precheck':'direction','profile':digest(profile)},
                            {'relationship':ref(relationship),'decision':'FAILED','reason_codes':['DISCOVERY_EFFECT_CONTRADICTS_EXPECTED_DIRECTION'],
                             'discovery_trial':ref(p1),'evaluation_trial':None,'period':plan['periods']['P2'],'research_spec':ref(profile)})
                        links[-1]=ref(self._link(relationship,p1,admission,validation=validation));self._horizon(rid,horizon,p2_status='FAILED')
                    elif effect is None:
                        validation=self.store.put('validation',{'discovery':ref(p1),'precheck':'missing_effect','profile':digest(profile)},
                            {'relationship':ref(relationship),'decision':'UNRESOLVED','reason_codes':['DISCOVERY_EFFECT_UNAVAILABLE'],
                             'discovery_trial':ref(p1),'evaluation_trial':None,'period':plan['periods']['P2'],'research_spec':ref(profile)})
                        links[-1]=ref(self._link(relationship,p1,admission,validation=validation))
                        self._horizon(rid,horizon,p2_status='UNRESOLVED')
                    else:pending.append((horizon,relationship,p1,admission,effect))
                self._update(rid,results=links)
            if pending:
                self._check(rid)
                token={'plan_id':plan['plan_id'],'direction':plan['intent']['expected_direction'],'admitted_horizons':[p[0] for p in pending]}
                self._update(rid,status='preparing',stage='P2 preparation',message='Preparing the frozen validation interval for admitted candidates only.')
                prepared2=adapter.prepare_phase(self.root,plan,'P2',progress=progress,cancelled=lambda:self._cancelled(rid),admission=token)
                for horizon,relationship,p1,admission,effect in pending:
                    self._check(rid);self._update(rid,status='p2',stage='P2',message=f'P2 {plan["mode"]}: {horizon} scheduled weekdays.')
                    self._horizon(rid,horizon,p2_status='running')
                    self._record_access(rid,plan,'P2',horizon)
                    data=adapter.load_phase(self.root,plan,prepared2,'P2',horizon,admission=token)
                    self._check(rid)
                    p2=self._trial(plan,prepared2,'P2',horizon,relationship,data,profile,impl,discovery_effect=effect,discovery_trial=ref(p1))
                    validation=self.store.put('validation',{'discovery':ref(p1),'evaluation':ref(p2)},
                        {'relationship':ref(relationship),'decision':p2['body']['decision'],'discovery_trial':ref(p1),'evaluation_trial':ref(p2),
                         'reason_codes':p2['body'].get('reason_codes',[]),'evidence':p2['body'].get('evidence',{})})
                    link=self._link(relationship,p1,admission,p2,validation)
                    links=[r for r in links if self.store.resolve('link',r)['body']['relationship']!=ref(relationship)]+[ref(link)]
                    self._horizon(rid,horizon,p2_status=p2['body']['decision']);self._update(rid,results=links)
            self._check(rid);self._update(rid,status='succeeded',stage='complete',message='Research execution completed. Each horizon retains its own scientific outcome.',results=links)
        except Cancelled:
            self._update(rid,status='cancelled',stage='cancelled',message='Execution stopped at a safe checkpoint. Committed results are retained.')
        except Exception as exc:
            if getattr(exc,'cancelled',False) or type(exc).__name__=='InputsCancelled':
                self._update(rid,status='cancelled',stage='cancelled',message='Execution stopped at a safe checkpoint. Committed results are retained.')
            elif isinstance(exc,ResearchBlocked) or hasattr(exc,'blockers'):
                blockers=exc.blockers
                self._update(rid,status='blocked',stage='blocked',blockers=blockers,message='Execution is blocked by the listed requirements. No policy is guessed.')
            else:
                self._update(rid,status='failed',stage='failed',message='Execution failed; committed evidence is retained and can be reconciled on resume.',
                    blockers=[{'code':'EXECUTION_ERROR','message':str(exc)[:600]}])
