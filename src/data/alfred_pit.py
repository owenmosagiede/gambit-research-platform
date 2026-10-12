"""Materialized ALFRED vintage-date PIT snapshots and a rebuildable SQLite index.

No credentials, network access, legacy reads, UTC release-time inference or
scientific transformations are involved. The source is the frozen onboarding run.
"""
from __future__ import annotations
from contextlib import closing
import datetime as dt
import fcntl
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile
from jsonschema import Draft202012Validator, FormatChecker
from data.alfred_onboarding import (SERIES, Store, canonical, sha, strict_json,
    stable_read, semantic, ref, identified, parse_vintages, now)

RUN = 'storage/catalog/onboarding/runs/ONBOARDING_124af5ecbbd0cc30b35459763b2a254b2b3bdba2c1887770e8673539aec5b67e.json'
VIEW = 'SVIEW_ALFRED_CES0500000003_VINTAGE_DATE'
INDEX = 'storage/catalog/pit_store/index.sqlite'
ROLE = 'alfred_pit_changes'


def date_only(value):
    if not isinstance(value,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',value):
        raise ValueError('Expected a date YYYY-MM-DD; intraday timestamps are unsupported')
    dt.date.fromisoformat(value)
    return value


def inside(root, relative):
    root=Path(root).resolve();path=root/relative
    if Path(relative).is_absolute() or not path.resolve().is_relative_to(root):
        raise ValueError('Path leaves the platform root')
    return path


def validator(root, schema):
    return Draft202012Validator(strict_json(inside(root,'specs/schemas/'+schema).read_bytes()),format_checker=FormatChecker())


def load_onboarding(root):
    """Verify the entire frozen parent package without consulting legacy stores."""
    store=Store(root);run=strict_json(stable_read(inside(root,RUN)))
    if Path(RUN).stem!='ONBOARDING_'+sha(canonical(run)) or run['status']!='COMPLETE_BOUNDED_ONBOARDING':
        raise ValueError('Invalid onboarding completion marker')
    checks={name:validator(root,name) for name in ['onboarding.schema.json','platform.schema.json']}
    for path in run['record_paths']:
        record=strict_json(stable_read(inside(root,path)))
        checks['onboarding.schema.json' if record['schema_version']=='0.1.0' else 'platform.schema.json'].validate(record)
        key=(record['id'],record['version'])
        if key in store.records: raise ValueError('Duplicate parent record')
        store.records[key]=record;store.paths[key]=path
    for path in run['payload_paths']:
        data=stable_read(inside(root,path),Path(path).stem)
        store.blobs[path]=(sha(data),len(data))
    store.verify_closure()
    def resolve(binding):
        record=store.records[(binding['id'],binding['version'])]
        if ref(record)!=binding: raise ValueError('Parent immutable reference mismatch')
        return record
    raw=resolve(run['snapshots']['bounded_vintages']);view=resolve(run['source_view'])
    if raw['layer']!='raw' or view['id']!=VIEW or view['body']['dataset']!=raw['definition']:
        raise ValueError('Wrong raw/source-view binding')
    assessment=resolve(run['assessments']['historical_replay'])
    if assessment['body']['decision']!='ready' or assessment['body']['snapshot']!=ref(raw):
        raise ValueError('Parent historical assessment not ready for this raw snapshot')
    return store,run,raw,view


def member_bytes(root,member):
    path=f"storage/payloads/sha256/{member['blob_sha256'][:2]}/{member['blob_sha256']}.{member['format']}"
    data=stable_read(inside(root,path),member['blob_sha256'])
    if len(data)!=member['byte_count']: raise ValueError('Payload byte count mismatch')
    return data


def normalize(payload, raw_reference, view_reference, blob_hash):
    changes=parse_vintages(payload)
    rows=[]
    for i,change in enumerate(changes):
        next_date=None
        if i+1<len(changes) and changes[i+1]['observation_date']==change['observation_date']:
            next_date=changes[i+1]['vintage_date']
        rows.append(dict(change,entity_id='US',next_vintage_date=next_date,timing_precision='date',
                         raw_snapshot=raw_reference,source_view=view_reference,source_raw_blob_sha256=blob_hash,
                         source_field=SERIES+'_'+change['vintage_date'].replace('-','')))
    return rows


def validate_rows(rows, root, raw_reference, view_reference, blob_hash, require_full_window=True, pinned_schema=None):
    check=Draft202012Validator(pinned_schema,format_checker=FormatChecker()) if pinned_schema is not None else validator(root,'alfred_pit_rows.schema.json')
    previous=None
    for i,row in enumerate(rows):
        check.validate(row)
        key=(row['observation_date'],row['vintage_date'])
        if previous is not None and key<=previous: raise ValueError('Unsorted or duplicate PIT keys')
        previous=key
        if not '2018-01-01'<=row['observation_date']<'2019-01-01': raise ValueError('Outside reference window')
        if row['raw_snapshot']!=raw_reference or row['source_view']!=view_reference or row['source_raw_blob_sha256']!=blob_hash:
            raise ValueError('PIT row lineage mismatch')
        if row['source_field']!=SERIES+'_'+row['vintage_date'].replace('-',''): raise ValueError('Wrong original source field')
        successor=rows[i+1]['vintage_date'] if i+1<len(rows) and rows[i+1]['observation_date']==row['observation_date'] else None
        if row['next_vintage_date']!=successor: raise ValueError('PIT validity interval mismatch')
    if require_full_window and {r['observation_date'] for r in rows}!={f'2018-{m:02d}-01' for m in range(1,13)}:
        raise ValueError('Incomplete 12-month reference coverage')


def select_rows(rows,as_of_date,observation_date=None):
    """As-of projection omits successor dates inferred from future revisions."""
    date_only(as_of_date)
    if observation_date is not None: date_only(observation_date)
    from data.pit_selection import select_asof
    return select_asof(rows,as_of_date,reference_key='observation_date',
                       availability_key='vintage_date',successor_key='next_vintage_date',
                       reference=observation_date,sort=False)


def snapshot_path(snapshot_id):
    if not isinstance(snapshot_id,str) or not re.fullmatch(r'SNAPSHOT_[0-9a-f]{64}',snapshot_id): raise ValueError('Invalid snapshot ID')
    return f'storage/catalog/snapshots/{snapshot_id}/manifest.json'


def read_pit(root,snapshot_id):
    """Validate canonical data and its exact pinned parent on every read."""
    parent,run,raw,view=load_onboarding(root)
    record=strict_json(stable_read(inside(root,snapshot_path(snapshot_id))))
    validator(root,'platform.schema.json').validate(record)
    if record['id']!=snapshot_id or record['layer']!='pit' or record['definition']!=ref(view) or record['upstream_snapshots']!=[ref(raw)]:
        raise ValueError('PIT snapshot binding mismatch')
    projection={k:v for k,v in record.items() if k not in ('id','members')}
    if record['id']!='SNAPSHOT_'+sha(canonical(projection)): raise ValueError('PIT manifest ID mismatch')
    if record['period']!=raw['period'] or record['information_cutoff']!=raw['information_cutoff']:
        raise ValueError('PIT snapshot temporal binding mismatch')
    if len(record['members'])!=1 or record['members'][0]['role']!=ROLE or record['members'][0]['format']!='jsonl':
        raise ValueError('Unsupported PIT payload contract')
    def parent_policy(name): return ref(parent.records[('POL_ALFRED_DATE_'+name,'1.0.0')])
    expected_policies=[{'role':'availability','artifact':parent_policy('AVAILABILITY')},{'role':'revision','artifact':parent_policy('REVISION')},{'role':'quality','artifact':parent_policy('QUALITY')}]
    if record['policy_bindings']!=expected_policies or len(record['lineage'])!=1 or record['implementation'] is None:
        raise ValueError('PIT policy or provenance binding mismatch')
    def dependency(binding,folder,schema='platform.schema.json'):
        path=f"storage/catalog/{folder}/{binding['id']}/manifest.json" if folder in ['lineage','implementations'] else f"storage/catalog/{folder}/{binding['id']}.json"
        value=strict_json(stable_read(inside(root,path)));validator(root,schema).validate(value)
        if ref(value)!=binding: raise ValueError('PIT provenance digest mismatch')
        return value
    implementation=dependency(record['implementation'],'implementations')
    if implementation['determinism_policy']!=parent_policy('RANDOMNESS') or implementation['entrypoint_id']!='materialize_alfred_pit_2018':
        raise ValueError('PIT implementation policy mismatch')
    for field in ['code_artifacts','environment_artifacts']:
        for artifact in implementation[field]: member_bytes(root,artifact)
    lineage=dependency(record['lineage'][0],'lineage')
    if lineage['implementation']!=record['implementation'] or lineage['operation']!=parent_policy('SELECTION') or lineage['policy_bindings']!=expected_policies:
        raise ValueError('PIT lineage policies mismatch')
    inputs={item['role']:item['artifact'] for item in lineage['inputs']}
    if len(lineage['inputs'])!=3 or set(inputs)!={'raw_snapshot','row_schema','source_view'} or inputs['raw_snapshot']!=ref(raw) or inputs['source_view']!=ref(view):
        raise ValueError('PIT lineage input mismatch')
    evidence=dependency(inputs['row_schema'],'onboarding/evidence','onboarding.schema.json')
    if evidence['record_type']!='onboarding_evidence' or evidence['body']['kind']!='alfred_pit_row_schema' or evidence['body']['media_type']!='application/json':
        raise ValueError('Wrong pinned row schema record')
    schema_payload=evidence['body']['payload']
    pinned_bytes=member_bytes(root,{'blob_sha256':schema_payload['sha256'],'byte_count':schema_payload['byte_count'],'format':'json'})
    pinned_schema=strict_json(pinned_bytes);Draft202012Validator.check_schema(pinned_schema)
    member=record['members'][0];data=member_bytes(root,member)
    rows=[strict_json(line) for line in data.splitlines()]
    validate_rows(rows,root,ref(raw),ref(view),raw['members'][0]['blob_sha256'],pinned_schema=pinned_schema)
    if data!=b''.join(canonical(row)+b'\n' for row in rows): raise ValueError('Noncanonical PIT payload')
    if sha(canonical(rows))!=record['semantic_content_sha256'] or len(rows)!=record['record_count'] or len(rows)!=member['row_count']:
        raise ValueError('PIT semantic hash/count mismatch')
    expected=normalize(strict_json(member_bytes(root,raw['members'][0])),ref(raw),ref(view),raw['members'][0]['blob_sha256'])
    if rows!=expected: raise ValueError('PIT output differs from authoritative raw vintages')
    return record,rows


def index_tuples(snapshot,rows):
    return [(snapshot['id'],r['series_id'],r['observation_date'],r['vintage_date'],r['next_vintage_date'],canonical(r).decode()) for r in rows]


def rebuild_index(root):
    """Rebuild derived SQLite from verified PIT manifests, with one local writer."""
    index=inside(root,INDEX);index.parent.mkdir(parents=True,exist_ok=True)
    lock_path=inside(root,'storage/temporary/pit-index.lock');lock_path.parent.mkdir(parents=True,exist_ok=True)
    with lock_path.open('a+b') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        snapshots=[]
        for path in sorted(inside(root,'storage/catalog/snapshots').glob('SNAPSHOT_*/manifest.json')):
            candidate=strict_json(stable_read(path))
            if candidate.get('layer')=='pit' and candidate.get('definition',{}).get('id')==VIEW and candidate.get('definition',{}).get('version')=='1.0.0':
                snapshots.append(read_pit(root,candidate['id']))
        if not snapshots: raise ValueError('No verified ALFRED PIT snapshot exists')
        fd,temp=tempfile.mkstemp(prefix='.pit-index-',suffix='.sqlite',dir=index.parent);os.close(fd)
        try:
            with closing(sqlite3.connect(temp)) as conn:
                conn.executescript('''
                PRAGMA journal_mode=DELETE;
                PRAGMA synchronous=FULL;
                CREATE TABLE snapshots(snapshot_id TEXT PRIMARY KEY, content_sha256 TEXT NOT NULL, rows_sha256 TEXT NOT NULL, row_count INTEGER NOT NULL, information_cutoff TEXT NOT NULL);
                CREATE TABLE observations(snapshot_id TEXT NOT NULL,series_id TEXT NOT NULL,observation_date TEXT NOT NULL,vintage_date TEXT NOT NULL,next_vintage_date TEXT,row_json TEXT NOT NULL,PRIMARY KEY(snapshot_id,series_id,observation_date,vintage_date));
                CREATE INDEX as_of_lookup ON observations(snapshot_id,observation_date,vintage_date,next_vintage_date);
                ''')
                for snapshot,rows in snapshots:
                    conn.execute('INSERT INTO snapshots VALUES (?,?,?,?,?)',(snapshot['id'],ref(snapshot)['content_sha256'],snapshot['semantic_content_sha256'],len(rows),snapshot['information_cutoff']))
                    conn.executemany('INSERT INTO observations VALUES (?,?,?,?,?,?)',index_tuples(snapshot,rows))
                conn.commit()
                if conn.execute('PRAGMA integrity_check').fetchall()!=[('ok',)]: raise ValueError('SQLite integrity failure')
            with open(temp,'rb') as f: os.fsync(f.fileno())
            os.replace(temp,index)
            dfd=os.open(index.parent,os.O_RDONLY)
            try: os.fsync(dfd)
            finally: os.close(dfd)
        finally:
            if os.path.exists(temp): os.unlink(temp)
        return {'index_path':INDEX,'snapshot_count':len(snapshots),'vintage_rows':sum(len(rows) for _,rows in snapshots)}


def query(root,snapshot_id,as_of_date,observation_date=None):
    date_only(as_of_date)
    snapshot,rows=read_pit(root,snapshot_id)
    if as_of_date>snapshot['information_cutoff'][:10]: raise ValueError('As-of date exceeds the frozen archive capture date')
    if observation_date is not None:
        date_only(observation_date)
        if observation_date not in {r['observation_date'] for r in rows}: raise ValueError('Observation date is outside this snapshot coverage')
    index=inside(root,INDEX)
    if not index.is_file(): raise ValueError('PIT index missing; run rebuild-index')
    uri=index.as_uri()+'?mode=ro'
    with closing(sqlite3.connect(uri,uri=True)) as conn:
        conn.execute('PRAGMA query_only=ON')
        expected=(snapshot_id,ref(snapshot)['content_sha256'],snapshot['semantic_content_sha256'],len(rows),snapshot['information_cutoff'])
        if conn.execute('SELECT * FROM snapshots WHERE snapshot_id=?',(snapshot_id,)).fetchone()!=expected: raise ValueError('Stale PIT index; run rebuild-index')
        actual=conn.execute('SELECT * FROM observations WHERE snapshot_id=? ORDER BY series_id,observation_date,vintage_date',(snapshot_id,)).fetchall()
        if actual!=index_tuples(snapshot,rows): raise ValueError('PIT index differs from immutable observations; run rebuild-index')
        sql='SELECT row_json FROM observations WHERE snapshot_id=? AND vintage_date<=? AND (next_vintage_date IS NULL OR ?<next_vintage_date)'
        params=[snapshot_id,as_of_date,as_of_date]
        if observation_date is not None: sql+=' AND observation_date=?';params.append(observation_date)
        sql+=' ORDER BY observation_date'
        selected=[{k:v for k,v in strict_json(text).items() if k!='next_vintage_date'} for (text,) in conn.execute(sql,params)]
    if selected!=select_rows(rows,as_of_date,observation_date): raise ValueError('As-of query disagreement')
    return {'snapshot':ref(snapshot),'as_of_vintage_date':as_of_date,'archive_captured_at':snapshot['information_cutoff'],
            'reference_period':snapshot['period'],'timing_precision':'date','selected_count':len(selected),
            'limitations':['Frozen ALFRED archive; date-level state only.','No exact intraday availability or future freshness is implied.'], 'observations':selected}


def materialize(root):
    store,run,raw,view=load_onboarding(root)
    original={path:sha(stable_read(inside(root,path))) for path in run['record_paths']+run['payload_paths']+[RUN]}
    source=raw['members'][0];payload=strict_json(member_bytes(root,source))
    rows=normalize(payload,ref(raw),ref(view),source['blob_sha256'])
    validate_rows(rows,root,ref(raw),ref(view),source['blob_sha256'])
    if len(rows)!=run['counts']['current_vintage_values']: raise ValueError('Lost or extra native vintages')
    row_schema=stable_read(inside(root,'specs/schemas/alfred_pit_rows.schema.json'))
    schema_member=store.blob(row_schema,'json','pit_row_schema',None)
    evidence=identified('onboarding_evidence',{'kind':'alfred_pit_row_schema','payload':{'sha256':schema_member['blob_sha256'],'byte_count':schema_member['byte_count'],'row_count':None},'media_type':'application/json','description':'Versioned source-specific PIT change-event row schema; date-only intervals; historical projections omit future successor dates.'},'EVIDENCE_')
    schema_ref=store.record(evidence,f"storage/catalog/onboarding/evidence/{evidence['id']}.json")
    code=[store.blob(stable_read(inside(root,path)),'bin',path.replace('/','.'),None) for path in ['src/data/pit_selection.py','src/data/alfred_pit.py','src/data/alfred_onboarding.py','tools/materialize_alfred_pit.py']]
    env=store.blob(canonical({'python':__import__('platform').python_version(),'sqlite':sqlite3.sqlite_version,'jsonschema':__import__('importlib.metadata',fromlist=['version']).version('jsonschema')})+b'\n','json','environment',None)
    def policy(name): return ref(store.records[('POL_ALFRED_DATE_'+name,'1.0.0')])
    impl={'schema_version':'0.2.0','record_type':'implementation_manifest','version':'1.0.0','code_artifacts':code,'environment_artifacts':[env],'entrypoint_id':'materialize_alfred_pit_2018','determinism_policy':policy('RANDOMNESS')}
    impl['id']='IMPLEMENTATION_'+sha(canonical(impl));implementation=store.record(impl,f"storage/catalog/implementations/{impl['id']}/manifest.json")
    lineage={'schema_version':'0.2.0','record_type':'lineage_manifest','version':'1.0.0','inputs':[{'role':'raw_snapshot','artifact':ref(raw)},{'role':'row_schema','artifact':schema_ref},{'role':'source_view','artifact':ref(view)}],
        'operation':policy('SELECTION'),'implementation':implementation,'policy_bindings':[{'role':'availability','artifact':policy('AVAILABILITY')},{'role':'revision','artifact':policy('REVISION')},{'role':'quality','artifact':policy('QUALITY')}]}
    lineage['id']='LINEAGE_'+sha(canonical(lineage));lineage_ref=store.record(lineage,f"storage/catalog/lineage/{lineage['id']}/manifest.json")
    member=store.blob(b''.join(canonical(r)+b'\n' for r in rows),'jsonl',ROLE,len(rows))
    snapshot={'schema_version':'0.2.0','record_type':'snapshot_manifest','version':'1.0.0','layer':'pit','definition':ref(view),'period':raw['period'],'information_cutoff':raw['information_cutoff'],
        'members':[member],'semantic_content_sha256':sha(canonical(rows)),'record_count':len(rows),'upstream_snapshots':[ref(raw)],'policy_bindings':lineage['policy_bindings'],
        'implementation':implementation,'lineage':[lineage_ref]}
    snapshot['id']='SNAPSHOT_'+sha(canonical({k:v for k,v in snapshot.items() if k!='members'}))
    snap_ref=store.record(snapshot,snapshot_path(snapshot['id']))
    store.verify_closure()
    for path,digest in original.items(): stable_read(inside(root,path),digest)
    indexed=rebuild_index(root)
    probes=[]
    for day,expected in [('2018-02-01',None),('2018-02-02','26.74'),('2018-03-08','26.74'),('2018-03-09','26.71')]:
        result=query(root,snapshot['id'],day,'2018-01-01')
        actual=result['observations'][0]['value'] if result['observations'] else None
        if actual!=expected: raise ValueError('Historical replay acceptance failure')
        probes.append({'as_of':day,'value':actual})
    # Pin independent official as-of responses retained in the original onboarding.
    for day in ['2018-02-02','2018-03-09']:
        receipt_ref=run['ingestion_receipts']['asof_'+day];receipt=store.records[(receipt_ref['id'],receipt_ref['version'])]['body']
        blob=receipt['payload'];data=stable_read(inside(root,f"storage/payloads/sha256/{blob['sha256'][:2]}/{blob['sha256']}.json"),blob['sha256'])
        observed=strict_json(data)['observations'][0]
        if query(root,snapshot['id'],day,observed['date'])['observations'][0]['value']!=observed['value']: raise ValueError('Archived official as-of response mismatch')
    # Persist locators only for new immutable payloads, never rewriting old ones.
    check=validator(root,'platform.schema.json')
    for path,(digest,size) in store.blobs.items():
        relative=f'storage/catalog/locators/{digest}/PLATFORM_LOCAL/{sha(path.encode())}.json'
        if inside(root,relative).exists(): continue
        locator={'schema_version':'0.2.0','record_type':'payload_locator_record','blob_sha256':digest,'store_id':'PLATFORM_LOCAL','relative_path':path,'access':'managed','verified_byte_count':size,'verified_at':now()}
        check.validate(locator);store.install(relative,canonical(locator)+b'\n')
    completed={'schema_version':'0.1.0','status':'COMPLETE','pit_snapshot':snap_ref,'raw_snapshot':ref(raw),'source_view':ref(view),'row_schema':schema_ref,
        'index_path':INDEX,'record_count':len(rows),'reference_months':12,'historical_query_checks':probes,'onboarding_run_sha256':sha(canonical(run)),
        'raw_and_onboarding_unchanged':True,'timing_precision':'date','live_generation_certified':False}
    complete_path=f"storage/catalog/pit_store/completions/{snapshot['id']}.json"
    store.install(complete_path,canonical(completed)+b'\n')
    return dict(completed,completion_path=complete_path,payload_path=f"storage/payloads/sha256/{member['blob_sha256'][:2]}/{member['blob_sha256']}.jsonl",index=indexed)
