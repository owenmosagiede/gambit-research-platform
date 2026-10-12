"""Immutable full-history CES0500000003 onboarding and date-level PIT store.

Definitions/policies use version 2.0.0. Published packages can be replayed without the retired pilot.
Raw requests are archived exactly; no release-time timestamps are inferred.
"""
from contextlib import closing
import copy
import fcntl
import os
from pathlib import Path
import platform
import sqlite3
import tempfile
from jsonschema import Draft202012Validator, FormatChecker
from data.alfred_onboarding import Store, SERIES, canonical, sha, strict_json, stable_read, ref, identified
from data.alfred_pit import load_onboarding, inside, date_only, select_rows, member_bytes, snapshot_path, index_tuples
from data.alfred_full_acquisition import load_bundle, validate_bundle

VIEW = 'SVIEW_ALFRED_CES0500000003_VINTAGE_DATE'
VERSION = '2.0.0'
INDEX = 'storage/catalog/pit_store/full_history/index.sqlite'
STATUS = 'VERIFIED_FULL_HISTORY_PACKAGE'


def rowset(changes, raw, view):
    rows=[]
    for i,item in enumerate(changes):
        row={k:item[k] for k in ['series_id','observation_date','vintage_date','value','status','source_raw_blob_sha256']}
        row.update(entity_id='US', timing_precision='date', raw_snapshot=raw, source_view=view,
                   source_field=SERIES+'_'+item['vintage_date'].replace('-',''),
                   next_vintage_date=changes[i+1]['vintage_date'] if i+1<len(changes) and changes[i+1]['observation_date']==item['observation_date'] else None)
        rows.append(row)
    return rows


def validate_rows(rows, schema):
    Draft202012Validator.check_schema(schema)
    validator=Draft202012Validator(schema,format_checker=FormatChecker())
    previous=None
    for i,row in enumerate(rows):
        validator.validate(row)
        key=(row['observation_date'],row['vintage_date'])
        if previous is not None and key<=previous: raise ValueError('Unsorted or duplicate PIT key')
        previous=key
        successor=rows[i+1]['vintage_date'] if i+1<len(rows) and rows[i+1]['observation_date']==row['observation_date'] else None
        if row['next_vintage_date']!=successor: raise ValueError('Invalid successor interval')
        if row['source_field']!=SERIES+'_'+row['vintage_date'].replace('-',''): raise ValueError('Source field mismatch')
    if not rows: raise ValueError('Empty full-history PIT output')


def evidence(store, kind, value, description, data=None):
    member=store.blob(canonical(value)+b'\n' if data is None else data,'json',kind,None)
    record=identified('onboarding_evidence',{'kind':kind,'payload':{'sha256':member['blob_sha256'],'byte_count':member['byte_count'],'row_count':None},'media_type':'application/json','description':description},'EVIDENCE_')
    return store.record(record,f"storage/catalog/onboarding/evidence/{record['id']}.json")


def publish_snapshot(store, body):
    body=dict(body,schema_version='0.2.0',record_type='snapshot_manifest',version='1.0.0')
    record=dict(body,id='SNAPSHOT_'+sha(canonical({k:v for k,v in body.items() if k!='members'})))
    return store.record(record,snapshot_path(record['id']))


def publish_lineage(store, inputs, operation, implementation, bindings):
    body={'schema_version':'0.2.0','record_type':'lineage_manifest','version':'1.0.0','inputs':inputs,'operation':operation,'implementation':implementation,'policy_bindings':bindings}
    record=dict(body,id='LINEAGE_'+sha(canonical(body)))
    return store.record(record,f"storage/catalog/lineage/{record['id']}/manifest.json")


def payload_record_bytes(root, record):
    payload=record['body']['payload']
    return member_bytes(root,{'blob_sha256':payload['sha256'],'format':'json','byte_count':payload['byte_count']})


def resolve(store, binding):
    value=store.records[(binding['id'],binding['version'])]
    if ref(value)!=binding: raise ValueError('Immutable reference mismatch')
    return value


def load_package(root, snapshot_id):
    snapshot_path(snapshot_id)
    found=[]
    for path in inside(root,'storage/catalog/onboarding/runs').glob('ONBOARDING_*.json'):
        candidate=strict_json(stable_read(path))
        if candidate.get('status')==STATUS and candidate.get('pit_snapshot',{}).get('id')==snapshot_id:
            if path.stem!='ONBOARDING_'+sha(canonical(candidate)): raise ValueError('Full-history package ID mismatch')
            found.append(candidate)
    if len(found)!=1: raise ValueError('Expected one full-history package for this snapshot')
    run=found[0];store=Store(root)
    schemas={v:Draft202012Validator(strict_json(inside(root,'specs/schemas/'+name).read_bytes()),format_checker=FormatChecker()) for v,name in [('0.1.0','onboarding.schema.json'),('0.2.0','platform.schema.json')]}
    for path in run['record_paths']:
        record=strict_json(stable_read(inside(root,path)));schemas[record['schema_version']].validate(record)
        key=(record['id'],record['version'])
        if key in store.records: raise ValueError('Duplicate package record')
        store.records[key]=record;store.paths[key]=path
    for path in run['payload_paths']:
        data=stable_read(inside(root,path),Path(path).stem);store.blobs[path]=(sha(data),len(data))
    store.verify_closure()
    return store,run


def read_pit(root, snapshot_id):
    store,run=load_package(root,snapshot_id)
    raw=resolve(store,run['raw_snapshot']);pit=resolve(store,run['pit_snapshot']);view=resolve(store,run['source_view'])
    if view['id']!=VIEW or view['version']!=VERSION or view['body']['dataset']!=run['dataset']:
        raise ValueError('Wrong full-history source-view binding')
    if raw['layer']!='raw' or raw['definition']!=run['dataset'] or pit['layer']!='pit' or pit['definition']!=ref(view) or pit['upstream_snapshots']!=[ref(raw)]:
        raise ValueError('Wrong full-history snapshot dependencies')
    if pit['period']!=raw['period'] or pit['period']!=run['period'] or pit['information_cutoff']!=raw['information_cutoff'] or pit['information_cutoff']!=run['capture_finished_at']:
        raise ValueError('Full-history temporal binding mismatch')
    for snapshot in [raw,pit]:
        if snapshot['id']!='SNAPSHOT_'+sha(canonical({k:v for k,v in snapshot.items() if k not in ('id','members')})): raise ValueError('Snapshot ID mismatch')
    bundle_evidence=resolve(store,run['acquisition_evidence'])
    index=strict_json(payload_record_bytes(root,bundle_evidence))
    requests={}
    for name,binding in run['ingestion_receipts'].items():
        receipt=resolve(store,binding)['body'];data=payload_record_bytes(root,{'body':receipt})
        # Preserve the exact acquisition receipt rather than synthesizing transport facts.
        saved=index['saved_receipts'][name]
        if saved['sha256']!=receipt['payload']['sha256'] or saved['byte_count']!=receipt['payload']['byte_count'] or saved['endpoint']!=receipt['request']['endpoint'] or sorted(saved['parameters'].items())!=[(v['name'],v['value']) for v in receipt['request']['parameters']]:
            raise ValueError('Acquisition/ingestion receipt mismatch')
        requests[name]={'receipt':saved,'payloadbytes':data,'parsed':strict_json(data)}
    bundle=validate_bundle(index['bundle_index'],requests)
    if bundle['period']!=run['period'] or bundle['capture_finished_at']!=run['capture_finished_at'] or bundle['coverage']!=run['coverage'] or bundle['index']['realtime_cutoff']!=run['as_of_date']:
        raise ValueError('Coverage differs from acquisition evidence')
    expected_bindings=[{'role':name,'artifact':run['policies'][name]} for name in ['availability','revision','quality']]
    if pit['policy_bindings']!=expected_bindings or pit['implementation']!=run['implementation']:
        raise ValueError('PIT policy/implementation mismatch')
    lineage=resolve(store,pit['lineage'][0]) if len(pit['lineage'])==1 else None
    expected_inputs=[{'role':name,'artifact':run[field]} for name,field in [('raw_snapshot','raw_snapshot'),('source_view','source_view'),('row_schema','row_schema'),('coverage_audit','audit')]]
    if lineage is None or lineage['inputs']!=expected_inputs or lineage['operation']!=run['policies']['selection'] or lineage['implementation']!=run['implementation'] or lineage['policy_bindings']!=expected_bindings:
        raise ValueError('PIT lineage mismatch')
    impl=resolve(store,run['implementation'])
    if impl['entrypoint_id']!='onboard_alfred_full_history' or impl['determinism_policy']!=run['policies']['randomness']: raise ValueError('Implementation policy mismatch')
    schema=strict_json(payload_record_bytes(root,resolve(store,run['row_schema'])))
    if len(pit['members'])!=1 or pit['members'][0]['format']!='jsonl' or pit['members'][0]['role']!='alfred_full_history_pit_changes': raise ValueError('Unexpected PIT member')
    data=member_bytes(root,pit['members'][0]);rows=[strict_json(line) for line in data.splitlines()]
    validate_rows(rows,schema)
    if data!=b''.join(canonical(row)+b'\n' for row in rows) or sha(canonical(rows))!=pit['semantic_content_sha256'] or len(rows)!=pit['record_count'] or len(rows)!=pit['members'][0]['row_count']:
        raise ValueError('PIT bytes/digest/count mismatch')
    if rows!=rowset(bundle['rows'],ref(raw),ref(view)): raise ValueError('PIT differs from normalized raw archive')
    observation_names=index['bundle_index']['request_groups']['initial_vintage']+index['bundle_index']['request_groups']['observations']
    expected_members=[{'role':name,'blob_sha256':requests[name]['receipt']['sha256'],'format':'json','byte_count':requests[name]['receipt']['byte_count'],'row_count':len(requests[name]['parsed']['observations'])} for name in observation_names]
    if raw['members']!=expected_members or raw['semantic_content_sha256']!=sha(canonical([requests[n]['parsed'] for n in observation_names])) or raw['record_count']!=sum(m['row_count'] for m in expected_members):
        raise ValueError('Raw snapshot coverage mismatch')
    readiness=resolve(store,run['historical_assessment'])['body']
    if readiness['decision']!='ready' or readiness['snapshot']!=ref(pit) or readiness['interval']!=run['period'] or readiness['policy']!=run['policies']['readiness']:
        raise ValueError('Historical readiness mismatch')
    return pit,rows,run


def rebuild_index(root):
    index=inside(root,INDEX);index.parent.mkdir(parents=True,exist_ok=True)
    lock_path=inside(root,'storage/temporary/alfred-full-history-index.lock');lock_path.parent.mkdir(parents=True,exist_ok=True)
    with lock_path.open('a+b') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        ids=[]
        for path in inside(root,'storage/catalog/onboarding/runs').glob('ONBOARDING_*.json'):
            value=strict_json(stable_read(path))
            if value.get('status')==STATUS:ids.append(value['pit_snapshot']['id'])
        snapshots=[read_pit(root,sid) for sid in sorted(set(ids))]
        if not snapshots:raise ValueError('No verified full-history package')
        fd,temp=tempfile.mkstemp(prefix='.full-pit-',suffix='.sqlite',dir=index.parent);os.close(fd)
        try:
            with closing(sqlite3.connect(temp)) as conn:
                conn.executescript('''PRAGMA journal_mode=DELETE; PRAGMA synchronous=FULL;
                CREATE TABLE snapshots(snapshot_id TEXT PRIMARY KEY,content_sha256 TEXT NOT NULL,rows_sha256 TEXT NOT NULL,row_count INTEGER NOT NULL,information_cutoff TEXT NOT NULL);
                CREATE TABLE observations(snapshot_id TEXT NOT NULL,series_id TEXT NOT NULL,observation_date TEXT NOT NULL,vintage_date TEXT NOT NULL,next_vintage_date TEXT,row_json TEXT NOT NULL,PRIMARY KEY(snapshot_id,series_id,observation_date,vintage_date));
                CREATE INDEX as_of_lookup ON observations(snapshot_id,observation_date,vintage_date,next_vintage_date);''')
                for snapshot,rows,run in snapshots:
                    conn.execute('INSERT INTO snapshots VALUES(?,?,?,?,?)',(snapshot['id'],ref(snapshot)['content_sha256'],snapshot['semantic_content_sha256'],len(rows),snapshot['information_cutoff']))
                    conn.executemany('INSERT INTO observations VALUES(?,?,?,?,?,?)',index_tuples(snapshot,rows))
                conn.commit()
                if conn.execute('PRAGMA integrity_check').fetchall()!=[('ok',)]:raise ValueError('SQLite integrity failure')
            with open(temp,'rb') as f:os.fsync(f.fileno())
            os.replace(temp,index);dfd=os.open(index.parent,os.O_RDONLY)
            try:os.fsync(dfd)
            finally:os.close(dfd)
        finally:
            if os.path.exists(temp):os.unlink(temp)
    return {'index_path':INDEX,'snapshots':len(snapshots),'vintage_rows':sum(len(rows) for _,rows,_ in snapshots)}


def query(root,snapshot_id,as_of_date,observation_date=None):
    date_only(as_of_date)
    snapshot,rows,run=read_pit(root,snapshot_id)
    if as_of_date>run['as_of_date']:raise ValueError('As-of date exceeds frozen acquisition vintage cutoff')
    if observation_date is not None:
        date_only(observation_date)
        if observation_date not in {row['observation_date'] for row in rows}:raise ValueError('Observation date outside snapshot coverage')
    path=inside(root,INDEX)
    if not path.exists():raise ValueError('Full-history index missing; run rebuild-index')
    with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as conn:
        conn.execute('PRAGMA query_only=ON')
        expected=(snapshot_id,ref(snapshot)['content_sha256'],snapshot['semantic_content_sha256'],len(rows),snapshot['information_cutoff'])
        if conn.execute('SELECT * FROM snapshots WHERE snapshot_id=?',(snapshot_id,)).fetchone()!=expected:raise ValueError('Stale full-history index; run rebuild-index')
        if conn.execute('SELECT * FROM observations WHERE snapshot_id=? ORDER BY series_id,observation_date,vintage_date',(snapshot_id,)).fetchall()!=index_tuples(snapshot,rows):raise ValueError('Altered full-history index; run rebuild-index')
        sql='SELECT row_json FROM observations WHERE snapshot_id=? AND vintage_date<=? AND (next_vintage_date IS NULL OR ?<next_vintage_date)';params=[snapshot_id,as_of_date,as_of_date]
        if observation_date is not None:sql+=' AND observation_date=?';params.append(observation_date)
        selected=[{k:v for k,v in strict_json(t).items() if k!='next_vintage_date'} for (t,) in conn.execute(sql+' ORDER BY observation_date',params)]
    if selected!=select_rows(rows,as_of_date,observation_date):raise ValueError('PIT selection disagreement')
    first=min(r['vintage_date'] for r in rows)
    return {'snapshot':ref(snapshot),'as_of_vintage_date':as_of_date,'archive_captured_at':snapshot['information_cutoff'],'timing_precision':'date',
        'reference_period':snapshot['period'],'earliest_archived_vintage':first,'archive_coverage_status':'before_archive_coverage' if as_of_date<first else 'within_captured_archive',
        'selected_count':len(selected),'observations':selected,'limitations':['Archived vintage-date state; no exact intraday availability or historical local receipt inferred.','Before the earliest archived vintage, an empty result means archive coverage is unavailable, not that the economic data did not exist.','Frozen acquisition; capture day is not guaranteed to be a complete source-calendar day.']}


def reuse_completed_bundle(root, bundle):
    """Replay an identical verified acquisition without its old bootstrap sample."""
    matches=[]
    supplied={'bundle_index':bundle['index'],
              'saved_receipts':{name:request['receipt'] for name,request in bundle['requests'].items()}}
    for path in sorted(inside(root,'storage/catalog/pit_store/full_history/completions').glob('SNAPSHOT_*.json')):
        completion=strict_json(stable_read(path))
        if completion.get('status')!='COMPLETE_FULL_HISTORY_RAW_AND_PIT':
            raise ValueError('Unsupported full-history completion')
        snapshot,rows,run=read_pit(root,completion['pit_snapshot']['id'])
        run_path=inside(root,completion['run_path'])
        if (path.stem!=snapshot['id'] or completion['pit_snapshot']!=ref(snapshot)
                or completion['raw_snapshot']!=run['raw_snapshot']
                or completion['counts']!=run['counts'] or completion['coverage']!=run['coverage']
                or completion['run_sha256']!=sha(canonical(run))
                or run_path.stem!='ONBOARDING_'+completion['run_sha256']
                or strict_json(stable_read(run_path))!=run):
            raise ValueError('Full-history completion does not match its verified package')
        store,_=load_package(root,snapshot['id'])
        saved=strict_json(payload_record_bytes(root,resolve(store,run['acquisition_evidence'])))
        if saved==supplied:
            matches.append((completion,str(path.relative_to(Path(root).resolve()))))
    if len(matches)>1:raise ValueError('Ambiguous repeated acquisition')
    if not matches:return None
    completion,path=matches[0]
    return dict(completion,completion_path=path,index=rebuild_index(root))


def materialize(root,acquisition):
    bundle=load_bundle(acquisition)
    existing=reuse_completed_bundle(root,bundle)
    if existing is not None:return existing
    from data.alfred_pit import RUN
    if not inside(root,RUN).exists():
        raise ValueError('This acquisition is not the published bundle; a new versioned refresh must be implemented before publishing it without the retired pilot')
    store,parent_run,old_raw,old_view=load_onboarding(root)
    original={path:sha(stable_read(inside(root,path))) for path in parent_run['record_paths']+parent_run['payload_paths']}
    source_map={(r['observation_date'],r['vintage_date']):(r['value'],r['status']) for r in bundle['rows']}
    from data.alfred_onboarding import parse_vintages
    previous=parse_vintages(strict_json(member_bytes(root,old_raw['members'][0])))
    if any(source_map.get((r['observation_date'],r['vintage_date']))!=(r['value'],r['status']) for r in previous):raise ValueError('Full archive conflicts with preserved 2018 pilot; investigate before publication')
    index=strict_json(stable_read(Path(acquisition)/'bundle.json'))
    acquisition_ref=evidence(store,'alfred_full_acquisition',{'bundle_index':index,'saved_receipts':{name:request['receipt'] for name,request in bundle['requests'].items()}},'Complete sanitized request bundle, pagination and capture boundaries; response bytes retained separately.')
    audit=evidence(store,'alfred_full_history_audit',{'coverage':bundle['coverage'],'asof_checks':bundle['asof_checks'],'preserved_2018_vintage_events':len(previous),'pilot_overlap_equal':True,'date_precision_only':True},'Full available archive coverage and independent historical-state comparisons, without first-release or intraday claims.')
    policy_spec=evidence(store,'alfred_full_history_policy',{
        'scope':'All observation periods, the earliest archived state and all subsequent native ALFRED change events available for CES0500000003 at the frozen acquisition cutoff.',
        'selection':'Latest native vintage date <= requested date for each observation; missing replaces valid; no future successor dates returned.',
        'availability':'Source calendar vintage dates only. Earliest archived vintage is not necessarily first economic release. Before archive coverage returns unavailable status. No fabricated UTC timestamps.',
        'quality':'Verify complete pages, unique monthly reference coverage, all vintage-date membership, stable endpoint metadata and vintage lists, full first/middle/last historical-state comparisons, hashes and prior pilot overlap.',
        'revision':'Keep the actual earliest archived type-2 state and every subsequent type-3 change event including equal-value events and explicit missingness; raw responses and prior versions remain immutable.',
        'alignment':'Native observation month and source vintage-date labels, no resampling or trading-clock mapping.',
        'readiness':'Only frozen archive-date historical replay; neither research exposure permission nor live-generation readiness.',
        'determinism':'Canonical exact-decimal normalization, pinned code/schema/environment; no randomness; offline replay performs no requests.',
        'capture':'Multi-request acquisition with fixed vintage cutoff and stability checks, not an atomic provider transaction. Capture-day completeness is not implied.',
        'official_documentation':['https://fred.stlouisfed.org/docs/api/fred/series_observations.html','https://fred.stlouisfed.org/docs/api/fred/series_vintagedates.html','https://alfred.stlouisfed.org/help']},'Version 2 full-history engineering policy; scientific availability/decision-clock choices remain unresolved.')
    def definition(kind,id,label,body,folder):
        record={'schema_version':'0.2.0','record_type':kind,'id':id,'version':VERSION,'display_name':label,'body':body}
        return store.record(record,f'definitions/{folder}/{id}/{VERSION}.json')
    policies={}
    for name in ['availability','revision','quality','selection','alignment','readiness','randomness']:
        policies[name]=definition('policy_definition','POL_ALFRED_DATE_'+name.upper(),'ALFRED full-history date-level '+name,{'kind':name,'specification':policy_spec,'parameters':[],'approval_state':'approved','compatibility_evidence':[audit]},'policies')
    limits=[{'code':'DATE_PRECISION_ONLY','detail':'Native vintage dates describe archive state; exact intraday availability and historical local receipt are not established.'},
            {'code':'ARCHIVE_COVERAGE','detail':'All available reference history is preserved; earliest archived vintage may postdate economic observations and their original releases.'},
            {'code':'FROZEN_CAPTURE','detail':'Coverage ends at the fixed acquisition vintage cutoff; multi-request capture and source-calendar day completeness are not atomic guarantees.'},
            {'code':'NO_LIVE_GENERATION','detail':'No decision clock, scheduler, research-exposure authorization or live-generation certification is supplied.'}]
    provider_body=copy.deepcopy(resolve(store,parent_run['provider_contract'])['body']);provider_body.update(availability_policy=policies['availability'],vintage_limitations=limits)
    provider_record=identified('provider_contract',provider_body,'PROVIDER_');provider=store.record(provider_record,f"definitions/providers/{provider_record['id']}/1.0.0.json")
    dataset_body=copy.deepcopy(resolve(store,parent_run['dataset'])['body'])
    for name in ['availability','revision','quality']:dataset_body[name+'_policy']=policies[name]
    dataset_body['source_contract']=provider
    dataset=definition('dataset_definition',parent_run['dataset']['id'],bundle['metadata']['title'],dataset_body,'datasets')
    view_body=copy.deepcopy(old_view['body']);view_body.update(dataset=dataset,alignment_policy=policies['alignment'],selection_policy=policies['selection'])
    view=definition('source_view_definition',VIEW,'Full-history native ALFRED vintage-date view',view_body,'source_views')
    schema_bytes=stable_read(inside(root,'specs/schemas/alfred_pit_rows.schema.json'));schema_ref=evidence(store,'alfred_pit_row_schema',None,'Source-specific date-only PIT row schema, pinned exact bytes.',data=schema_bytes)
    code_paths=['src/data/pit_selection.py','src/data/alfred_full_history.py','src/data/alfred_full_acquisition.py','src/data/alfred_onboarding.py','src/data/alfred_pit.py','tools/onboard_alfred_full_history.py']
    codes=[store.blob(stable_read(inside(root,path)),'bin',path.replace('/','.'),None) for path in code_paths]
    env=store.blob(canonical({'python':platform.python_version(),'sqlite':sqlite3.sqlite_version,'jsonschema':__import__('importlib.metadata',fromlist=['version']).version('jsonschema')})+b'\n','json','environment',None)
    impl={'schema_version':'0.2.0','record_type':'implementation_manifest','version':'1.0.0','code_artifacts':codes,'environment_artifacts':[env],'entrypoint_id':'onboard_alfred_full_history','determinism_policy':policies['randomness']}
    impl['id']='IMPLEMENTATION_'+sha(canonical(impl));implementation=store.record(impl,f"storage/catalog/implementations/{impl['id']}/manifest.json")
    receipts={};members={}
    for name,request in bundle['requests'].items():
        receipt=request['receipt'];parsed=request['parsed'];count=len(parsed.get('observations',parsed.get('vintage_dates',parsed.get('seriess',[]))))
        member=store.blob(request['payloadbytes'],'json',name,count);members[name]=member
        body={'mode':'api_download','dataset':dataset,'provider_contract':provider,'request':{'endpoint':receipt['endpoint'],'parameters':[{'name':k,'value':str(v)} for k,v in sorted(receipt['parameters'].items())]},
            'retrieval':{'original_started_at':receipt['started_at'],'original_finished_at':receipt['finished_at'],'captured_at':bundle['capture_finished_at']},
            'response':{'http_status':receipt['http_status'],'headers':[{'name':k,'value':v} for k,v in sorted(receipt['headers'].items())],'content_type':receipt['headers'].get('content-type'),'content_encoding':receipt['headers'].get('content-encoding')},
            'payload':{'sha256':member['blob_sha256'],'byte_count':member['byte_count'],'row_count':count},'source_evidence':{'legacy_store_id':None,'legacy_relative_path':None,'source_sha256':None},
            'completeness':{'outcome':'complete' if parsed.get('offset',0)==0 and parsed.get('count',count)==count else 'partial','reason_codes':[] if parsed.get('offset',0)==0 and parsed.get('count',count)==count else ['PAGE_OF_COMPLETE_BUNDLE'],'errors':[]}}
        record=identified('ingestion_receipt',body,'INGESTION_');receipts[name]=store.record(record,f"storage/catalog/ingestions/records/{record['id']}.json")
    raw_lineage=publish_lineage(store,[{'role':name,'artifact':binding} for name,binding in receipts.items()]+[{'role':'acquisition_manifest','artifact':acquisition_ref}],policies['selection'],implementation,[{'role':'quality','artifact':policies['quality']}])
    observation_names=index['request_groups']['initial_vintage']+index['request_groups']['observations']
    if not observation_names:raise ValueError('No observation pages in acquired bundle')
    raw=publish_snapshot(store,{'layer':'raw','definition':dataset,'period':bundle['period'],'information_cutoff':bundle['capture_finished_at'],'members':[members[n] for n in observation_names],
        'semantic_content_sha256':sha(canonical([bundle['requests'][n]['parsed'] for n in observation_names])),'record_count':sum(members[n]['row_count'] for n in observation_names),'upstream_snapshots':[],
        'policy_bindings':[{'role':'quality','artifact':policies['quality']}],'implementation':implementation,'lineage':[raw_lineage]})
    rows=rowset(bundle['rows'],raw,view);validate_rows(rows,strict_json(schema_bytes))
    bindings=[{'role':name,'artifact':policies[name]} for name in ['availability','revision','quality']]
    pit_lineage=publish_lineage(store,[{'role':'raw_snapshot','artifact':raw},{'role':'source_view','artifact':view},{'role':'row_schema','artifact':schema_ref},{'role':'coverage_audit','artifact':audit}],policies['selection'],implementation,bindings)
    pit_member=store.blob(b''.join(canonical(row)+b'\n' for row in rows),'jsonl','alfred_full_history_pit_changes',len(rows))
    pit=publish_snapshot(store,{'layer':'pit','definition':view,'period':bundle['period'],'information_cutoff':bundle['capture_finished_at'],'members':[pit_member],
        'semantic_content_sha256':sha(canonical(rows)),'record_count':len(rows),'upstream_snapshots':[raw],'policy_bindings':bindings,'implementation':implementation,'lineage':[pit_lineage]})
    assessment=identified('capability_assessment',{'capability':'historical_replay','decision':'ready','dataset':dataset,'provider_contract':provider,'snapshot':pit,'policy':policies['readiness'],'implementation':implementation,
        'evidence':[audit,acquisition_ref,policy_spec]+list(receipts.values()),'interval':bundle['period'],'limitations':limits,'checks':[{'code':'FULL_AVAILABLE_ARCHIVE','outcome':'pass','evidence':[audit,acquisition_ref],'detail':'Complete stable pagination, metadata/reference-month coverage, vintage catalog coverage, independent historical states and pilot overlap verified.'}],
        'issued_at':bundle['capture_finished_at']},'READINESS_')
    readiness=store.record(assessment,f"storage/catalog/readiness/records/{assessment['id']}.json")
    store.verify_closure()
    for path,digest in original.items():stable_read(inside(root,path),digest)
    for path,(digest,size) in store.blobs.items():
        relative=f'storage/catalog/locators/{digest}/PLATFORM_LOCAL/{sha(path.encode())}.json'
        if inside(root,relative).exists():continue
        locator={'schema_version':'0.2.0','record_type':'payload_locator_record','blob_sha256':digest,'store_id':'PLATFORM_LOCAL','relative_path':path,'access':'managed','verified_byte_count':size,'verified_at':bundle['capture_finished_at']}
        store.install(relative,canonical(locator)+b'\n')
    run={'schema_version':'0.1.0','status':STATUS,'series_id':SERIES,'dataset':dataset,'source_view':view,'provider_contract':provider,'policies':policies,'raw_snapshot':raw,'pit_snapshot':pit,'implementation':implementation,
        'row_schema':schema_ref,'audit':audit,'acquisition_evidence':acquisition_ref,'ingestion_receipts':receipts,'historical_assessment':readiness,'period':bundle['period'],'coverage':bundle['coverage'],
        'capture_started_at':bundle['capture_started_at'],'capture_finished_at':bundle['capture_finished_at'],'as_of_date':index['realtime_cutoff'],
        'record_paths':sorted(store.paths.values()),'payload_paths':sorted(store.blobs),'counts':{'vintage_events':len(rows),'reference_months':len({r['observation_date'] for r in rows}),'requests':len(receipts)},'live_generation_certified':False}
    run_id='ONBOARDING_'+sha(canonical(run));run_path=f'storage/catalog/onboarding/runs/{run_id}.json';store.install(run_path,canonical(run)+b'\n')
    indexed=rebuild_index(root)
    first=min(r['vintage_date'] for r in rows)
    verified=query(root,pit['id'],first)
    if verified['selected_count']!=len(select_rows(rows,first)):raise ValueError('Published query failed')
    completion={'schema_version':'0.1.0','status':'COMPLETE_FULL_HISTORY_RAW_AND_PIT','run_path':run_path,'run_sha256':sha(canonical(run)),'raw_snapshot':raw,'pit_snapshot':pit,'counts':run['counts'],'coverage':run['coverage'],'index_path':INDEX,'timing_precision':'date','live_generation_certified':False}
    completion_path=f"storage/catalog/pit_store/full_history/completions/{pit['id']}.json";store.install(completion_path,canonical(completion)+b'\n')
    return dict(completion,completion_path=completion_path,index=indexed)
