"""Versioned FX adapters to the shared registries, snapshots and payload store.

No FX-specific payload store: year partitions are deterministic gzip JSONL blobs
inside the existing content-addressed namespace. Legacy locators are read-only.
"""
from collections import defaultdict
from datetime import datetime, timezone
import gzip
import hashlib
from pathlib import Path
from functools import lru_cache
from jsonschema import Draft202012Validator, FormatChecker
from data.alfred_onboarding import stable_read, strict_json
from data.transformations.identity import canonical_bytes, digest, reference
from data.transformations.contracts import normalize_reference, normalize_time, token

PREFIXES={'provider_contract':'PROVIDER_', 'dataset_definition':'DATASET_',
 'source_view_definition':'SOURCE_VIEW_', 'policy_definition':'POLICY_',
 'transformation_definition':'TRANSFORM_', 'snapshot_manifest':'SNAPSHOT_',
 'onboarding_evidence':'EVIDENCE_', 'ingestion_receipt':'INGESTION_',
 'capability_assessment':'READINESS_'}


def make_record(kind, body, display_name=None, prefix=None):
    if kind not in PREFIXES: raise ValueError('Unsupported FX registry record')
    payload={'schema_version':'0.5.0','record_type':kind,'version':'1.0.0','body':body}
    payload['id']=(prefix or PREFIXES[kind])+digest(payload)
    if display_name is not None: payload['display_name']=display_name
    return payload


@lru_cache(maxsize=1)
def schema_validator():
    path=Path(__file__).resolve().parents[2]/"specs/schemas/fx.schema.json"
    return Draft202012Validator(strict_json(stable_read(path)),format_checker=FormatChecker())


def validate_record(record):
    schema_validator().validate(record)
    # Basic envelope plus the independently checked content address. Body profiles
    # are interpreted by their bounded source/construction/materialization adapter.
    allowed={'schema_version','record_type','version','id','body','display_name'}
    if set(record)-allowed or not allowed-{'display_name'} <= set(record):
        raise ValueError('Invalid FX record envelope')
    if record['schema_version']!='0.5.0' or record['version']!='1.0.0' or not isinstance(record['body'],dict):
        raise ValueError('Unsupported FX record profile')
    expected=make_record(record['record_type'],record['body'],record.get('display_name'))
    if expected!=record: raise ValueError('FX identity differs from canonical content')
    if record['record_type']=='snapshot_manifest':
        body=record['body']
        if 'members' in body:
            for member in body['members']: validate_member(member)
        if 'record_count' in body and (type(body['record_count']) is not int or body['record_count']<0):
            raise ValueError('Invalid snapshot record count')
    return record


def validate_member(member):
    for key in ('blob_sha256','format','byte_count','role','row_count'):
        if key not in member: raise ValueError('Missing payload field '+key)
    if member.get('codec') not in (None,'gzip_jsonl'): raise ValueError('Unsupported payload codec')
    if member.get('codec')=='gzip_jsonl' and member['format']!='bin': raise ValueError('Gzip payload requires binary format')


def write_rows(store, rows, role, partition_key='year'):
    groups=defaultdict(list)
    for row in rows:
        when=row.get('reference_time',row.get('observation_date',row.get('prediction_anchor')))
        key=when[:4] if partition_key=='year' and when else 'all'
        groups[key].append(row)
    members=[]
    for key,values in sorted(groups.items()):
        data=b''.join(canonical_bytes(row)+b'\n' for row in values)
        # gzip header has no current clock or host filename.
        member=store.io.blob(gzip.compress(data,compresslevel=6,mtime=0),'bin',role,len(values))
        dates=[r.get('reference_time',r.get('observation_date',r.get('prediction_anchor'))) for r in values]
        dates=[d for d in dates if d is not None]
        members.append(dict(member,codec='gzip_jsonl',partition=key,
            semantic_sha256=digest(values),coverage={'start':min(dates) if dates else None,'end':max(dates) if dates else None}))
    return members


def read_rows(store, members):
    result=[]
    for member in members:
        validate_member(member)
        data=store.payload(member)
        if member.get('codec')=='gzip_jsonl': data=gzip.decompress(data)
        values=[strict_json(line) for line in data.splitlines()]
        if len(values)!=member['row_count'] or member.get('semantic_sha256',digest(values))!=digest(values):
            raise ValueError('Partition semantic integrity mismatch')
        result.extend(values)
    return result


def register_locator(store, path, legacy_root):
    """Register only a configured read-only root, never trust an artifact's path."""
    path=Path(path).resolve(); legacy_root=Path(legacy_root).resolve()
    if not path.is_relative_to(legacy_root): raise ValueError('Legacy artifact leaves admitted root')
    config=strict_json(stable_read(store.path('config/storage.local.json')))
    candidates=[]
    for store_id,entry in config['stores'].items():
        root=Path(entry['path']).resolve()
        if entry.get('read_only') is True and path.is_relative_to(root): candidates.append((len(str(root)),store_id,root))
    if not candidates: raise ValueError('No configured read-only legacy locator root')
    _,store_id,root=max(candidates)
    data=stable_read(path); sha=hashlib.sha256(data).hexdigest(); relative=str(path.relative_to(root))
    locator={'schema_version':'0.2.0','record_type':'payload_locator_record','blob_sha256':sha,
        'store_id':store_id,'relative_path':relative,'access':'read_only_legacy',
        'verified_byte_count':len(data),'verified_at':datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%fZ')}
    target=f'storage/catalog/locators/{sha}/{store_id}/{digest(relative)}.json'
    if not store.path(target).exists():
        store._validate(locator);store.io.install(target,canonical_bytes(locator)+b'\n')
    return {'blob_sha256':sha,'format':'json','byte_count':len(data),'row_count':None,'role':'legacy_raw'}


def resolve_external_payload(store, member):
    config=strict_json(stable_read(store.path('config/storage.local.json')))
    sha=member['blob_sha256']
    errors=[]
    for file in sorted(store.path(f'storage/catalog/locators/{sha}').glob('*/*.json')):
        try:
            locator=strict_json(stable_read(file));store._validate(locator)
            entry=config['stores'][locator['store_id']];root=Path(entry['path']).resolve()
            path=root/locator['relative_path']
            if locator['access']!='read_only_legacy' or entry.get('read_only') is not True or path.is_symlink() or not path.resolve().is_relative_to(root):
                raise ValueError('Unsafe external locator')
            data=stable_read(path,sha)
            if len(data)!=locator['verified_byte_count'] or len(data)!=member['byte_count']:raise ValueError('External size mismatch')
            return data
        except (OSError,ValueError,KeyError) as error:errors.append(str(error))
    raise ValueError('No verified payload locator resolves '+sha+(': '+str(errors) if errors else ''))
