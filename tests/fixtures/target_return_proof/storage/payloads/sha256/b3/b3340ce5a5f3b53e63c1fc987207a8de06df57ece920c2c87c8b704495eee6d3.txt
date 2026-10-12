"""Bounded ALFRED ingestion primitives; no research engines or scheduler.

Historical selection reconstructs ALFRED vintage-DATE states. It does not infer
intraday release times or certify a trading decision clock.
"""
from __future__ import annotations
import datetime as dt
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import urllib.error
import urllib.parse
import urllib.request

SERIES = 'CES0500000003'
BASE_URL = 'https://api.stlouisfed.org/fred/'
PARAMS = {'series_id','file_type','observation_start','observation_end','realtime_start','realtime_end','output_type','sort_order','limit','offset'}
HEADERS = {'content-type','content-encoding','date','etag','last-modified','cache-control','retry-after','content-length'}

def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec='microseconds').replace('+00:00','Z')

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode()

def sha(data):
    return hashlib.sha256(data).hexdigest()

def strict_json(data):
    def pairs(items):
        out = {}
        for k,v in items:
            if k in out: raise ValueError('duplicate JSON field')
            out[k] = v
        return out
    def reject(value): raise ValueError('nonfinite JSON number')
    return json.loads(data, object_pairs_hook=pairs, parse_constant=reject)

def semantic(record):
    omit = {'display_name'}
    if record['record_type'] == 'snapshot_manifest': omit.add('members')
    if record['record_type'] == 'materialization_manifest': omit.add('partitions')
    return {k:v for k,v in record.items() if k not in omit}

def ref(record):
    return {'id':record['id'], 'version':record['version'], 'content_sha256':sha(canonical(semantic(record)))}

def identified(kind, body, prefix, schema='0.1.0'):
    base = {'schema_version':schema, 'record_type':kind, 'version':'1.0.0', 'body':body}
    return dict(base, id=prefix+sha(canonical(base)))

def stable_read(path, expected_sha=None):
    path = Path(path)
    before = path.stat(); data = path.read_bytes(); after = path.stat()
    if (before.st_ino,before.st_size,before.st_mtime_ns) != (after.st_ino,after.st_size,after.st_mtime_ns):
        raise ValueError('source changed during bounded read')
    if expected_sha is not None and sha(data) != expected_sha: raise ValueError('source checksum mismatch')
    return data

def parse_vintages(payload, series=SERIES, start='2018-01-01', end='2019-01-01'):
    """Parse only a complete output_type=3 page, preserving revisions/missingness."""
    dt.date.fromisoformat(start); dt.date.fromisoformat(end)
    if start >= end: raise ValueError('empty or reversed reference window')
    rows = payload.get('observations')
    if payload.get('output_type') != 3 or payload.get('units') != 'lin': raise ValueError('wrong output type or units')
    if not isinstance(rows,list) or payload.get('offset') != 0 or type(payload.get('count')) is not int or len(rows) != payload['count']:
        raise ValueError('incomplete or paginated response')
    pattern = re.compile(re.escape(series)+r'_(\d{8})\Z')
    out=[]; periods=set(); keys=set()
    for row in rows:
        date=row['date']; dt.date.fromisoformat(date)
        if date in periods: raise ValueError('duplicate reference period')
        periods.add(date)
        for name,value in row.items():
            if name=='date': continue
            match=pattern.fullmatch(name)
            if not match: raise ValueError('unexpected series or vintage column')
            vintage=dt.datetime.strptime(match[1],'%Y%m%d').date().isoformat()
            if not isinstance(value,str): raise ValueError('nontext scientific value')
            if value=='.': normalized=None
            else:
                try: number=Decimal(value)
                except InvalidOperation: raise ValueError('invalid decimal value') from None
                if not number.is_finite(): raise ValueError('nonfinite scientific value')
                normalized=format(number,'f').rstrip('0').rstrip('.') if '.' in format(number,'f') else format(number,'f')
                if normalized in ('-0',''): normalized='0'
            if start <= date < end:
                key=(date,vintage)
                if key in keys: raise ValueError('duplicate vintage')
                keys.add(key)
                out.append({'series_id':series,'observation_date':date,'vintage_date':vintage,'value':normalized,'status':'missing' if value=='.' else 'valid'})
    return sorted(out,key=lambda r:(r['observation_date'],r['vintage_date']))

def as_of(rows, vintage_date):
    """Latest change <= the given native ALFRED vintage date, including deletions."""
    dt.date.fromisoformat(vintage_date)
    result={}
    for row in sorted(rows,key=lambda r:(r['observation_date'],r['vintage_date'])):
        if row['vintage_date']<=vintage_date: result[row['observation_date']]=dict(row)
    return [result[k] for k in sorted(result)]

def fetch_evidence(destination, credential_file):
    """Five official read-only requests. Secrets never enter saved receipts/errors."""
    destination=Path(destination); destination.mkdir(parents=True,exist_ok=True)
    key=None
    for line in Path(credential_file).read_text().splitlines():
        if line.startswith('FRED_API_KEY='): key=line.partition('=')[2].strip().strip('\"\'')
    if not key or not re.fullmatch('[a-z0-9]{32}',key): raise ValueError('FRED credential unavailable; value not logged')
    specs=[('metadata','series',{'series_id':SERIES,'file_type':'json'}),
           ('latest','series/observations',{'series_id':SERIES,'file_type':'json','sort_order':'desc','limit':'5','offset':'0'}),
           ('vintages_2018','series/observations',{'series_id':SERIES,'file_type':'json','observation_start':'2018-01-01','observation_end':'2018-12-31','realtime_start':'1776-07-04','realtime_end':'9999-12-31','output_type':'3','sort_order':'asc','limit':'100000','offset':'0'})]
    for vintage in ['2018-02-02','2018-03-09']:
        specs.append(('asof_'+vintage,'series/observations',{'series_id':SERIES,'file_type':'json','observation_start':'2018-01-01','observation_end':'2018-01-01','realtime_start':vintage,'realtime_end':vintage,'output_type':'1','limit':'10','offset':'0'}))
    for name,path,params in specs:
        endpoint=BASE_URL+path
        receipt={'endpoint':endpoint,'parameters':params,'started_at':now(),'finished_at':None,'http_status':None,'headers':{},'error':None,'payload_path':None}
        try:
            url=endpoint+'?'+urllib.parse.urlencode(dict(params,api_key=key))
            request=urllib.request.Request(url,headers={'User-Agent':'ResearchPlatformOnboarding/0.1','Accept-Encoding':'identity'})
            with urllib.request.urlopen(request,timeout=40) as response:
                content=response.read(2_000_001)
                if len(content)>2_000_000: raise ValueError('response exceeds bound')
                if key.encode() in content: raise ValueError('credential reflected; response not retained')
                strict_json(content)
                receipt.update(http_status=response.status,headers={k.lower():v for k,v in response.headers.items() if k.lower() in HEADERS})
                saved=destination/(name+'.json'); saved.write_bytes(content)
                receipt.update(payload_path=str(saved),sha256=sha(content),byte_count=len(content))
        except urllib.error.HTTPError as exc:
            receipt.update(http_status=exc.code,error={'code':'HTTP_ERROR','message':'Provider HTTP '+str(exc.code)})
        except Exception as exc:
            receipt['error']={'code':type(exc).__name__,'message':'Request failed; credential-bearing exception details omitted'}
        receipt['finished_at']=now()
        (destination/(name+'.receipt.json')).write_bytes(canonical(receipt)+b'\n')

class Store:
    """Immutable local files: install complete bytes before publishing references."""
    def __init__(self,root):
        self.root=Path(root).resolve(); self.records={}; self.paths={}; self.blobs={}
    def install(self,relative,data):
        path=self.root/relative
        if not path.resolve().is_relative_to(self.root): raise ValueError('path leaves platform root')
        path.parent.mkdir(parents=True,exist_ok=True)
        fd,temp=tempfile.mkstemp(prefix='.onboarding-',dir=path.parent)
        try:
            with os.fdopen(fd,'wb') as f: f.write(data); f.flush(); os.fsync(f.fileno())
            try: os.link(temp,path)
            except FileExistsError:
                if path.is_symlink() or path.read_bytes()!=data: raise ValueError('immutable content conflict')
            dfd=os.open(path.parent,os.O_RDONLY)
            try: os.fsync(dfd)
            finally: os.close(dfd)
        finally: os.unlink(temp)
        return str(path.relative_to(self.root))
    def blob(self,data,fmt='json',role='evidence',rows=None):
        if fmt not in {'json','jsonl','txt','bin','csv','parquet'}: raise ValueError('unsupported physical format')
        digest=sha(data)
        relative=f'storage/payloads/sha256/{digest[:2]}/{digest}.{fmt}'
        self.install(relative,data)
        self.blobs[relative]=(digest,len(data))
        return {'role':role,'blob_sha256':digest,'format':fmt,'byte_count':len(data),'row_count':rows}
    def record(self,record,relative):
        from jsonschema import Draft202012Validator, FormatChecker
        schema_name='onboarding.schema.json' if record['schema_version']=='0.1.0' else 'platform.schema.json'
        schema=strict_json((self.root/'specs/schemas'/schema_name).read_bytes())
        Draft202012Validator(schema,format_checker=FormatChecker()).validate(record)
        identity=(record['id'],record['version'])
        if identity in self.records and ref(self.records[identity])!=ref(record): raise ValueError('reference identity conflict')
        self.install(relative,canonical(record)+b'\n');self.records[identity]=record;self.paths[identity]=relative
        return ref(record)
    def verify_closure(self):
        for path,(digest,size) in self.blobs.items():
            data=stable_read(self.root/path,digest)
            if len(data)!=size: raise ValueError('published payload length mismatch')
        for identity,record in self.records.items():
            if (self.root/self.paths[identity]).read_bytes()!=canonical(record)+b'\n': raise ValueError('published record content mismatch')
        payloads={(digest,size) for digest,size in self.blobs.values()}
        def visit(value):
            if isinstance(value,dict):
                if 'blob_sha256' in value:
                    member_path=f"storage/payloads/sha256/{value['blob_sha256'][:2]}/{value['blob_sha256']}.{value['format']}"
                    if self.blobs.get(member_path)!=(value['blob_sha256'],value['byte_count']): raise ValueError('unresolved payload member')
                if set(value)=={'sha256','byte_count','row_count'} and (value['sha256'],value['byte_count']) not in payloads: raise ValueError('unresolved evidence payload')
                if set(value)=={'id','version','content_sha256'}:
                    target=self.records.get((value['id'],value['version']))
                    if target is None or ref(target)!=value: raise ValueError('unresolved or mismatched immutable reference')
                for item in value.values(): visit(item)
            elif isinstance(value,list):
                for item in value: visit(item)
        for record in self.records.values(): visit(record)
