#!/usr/bin/env python3
"""Read-only inventory, quiescent export, and hash verification. Never edits legacy bytes.

Inventory alone is not a consistent backup. Export requires no worker ownership,
no nonterminal requests, and the research writer lock. Stop web/onboarding before
export. The cloud remains disabled until full reference-closure/restore acceptance.
"""
from contextlib import ExitStack
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from data.feature_store import FeatureStore
from research.store import lock

FOLDERS = ('src', 'ui', 'tools', 'definitions', 'specs', 'config', 'storage', 'deploy')
RUNTIME_FILES = ('requirements-data.txt', 'requirements-cloud.lock')
OMIT = {'__pycache__', '.DS_Store', 'private'}
SHA = re.compile(r'[0-9a-f]{64}\Z')
FORMAT = re.compile(r'[a-z0-9][a-z0-9_.-]{0,40}\Z')

def digest(path):
    before = path.stat(); h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''): h.update(block)
    after = path.stat()
    if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
        raise ValueError('File changed during inventory: ' + str(path))
    return h.hexdigest(), after.st_size

def selected(root):
    for folder in FOLDERS:
        for path in sorted((root/folder).rglob('*')):
            relative = path.relative_to(root)
            if any(p in OMIT for p in relative.parts): continue
            if path.is_symlink(): raise ValueError('Symlink not permitted in migration: ' + str(relative))
            if not path.is_file() or path.name.startswith('.'): continue
            if path.suffix in ('.pyc', '.lock', '.log'): continue
            if path.name == 'worker_service.json': continue
            if relative.parts[0] == 'config' and '.local.' in path.name: continue
            if path.name.startswith(('credentials', 'secrets')) or path.suffix in ('.pem', '.key'):
                raise ValueError('Private credential-like file excluded; investigate before export: ' + str(relative))
            yield path
    for name in RUNTIME_FILES:
        if (root/name).is_file(): yield root/name

def members(value):
    if isinstance(value, dict):
        if {'blob_sha256','format','byte_count'} <= value.keys():
            if not SHA.fullmatch(value['blob_sha256']) or not FORMAT.fullmatch(value['format']):
                raise ValueError('Unsafe payload identity')
            yield {k:value[k] for k in ('blob_sha256','format','byte_count')}
        for child in value.values(): yield from members(child)
    elif isinstance(value, list):
        for child in value: yield from members(child)

def inventory(root, destination=None):
    root=Path(root).resolve(); entries=[]; externals={}; store=FeatureStore(root)
    if destination:
        destination=Path(destination).resolve()
        if destination.is_relative_to(root) or root.is_relative_to(destination):
            raise ValueError('Export must be separate from source')
        destination.mkdir(parents=True,exist_ok=False)
    paths=list(selected(root))
    for p in paths:
        relative=p.relative_to(root).as_posix(); sha,size=digest(p)
        entries.append({'path':relative,'sha256':sha,'bytes':size})
        if p.suffix == '.json' and relative.startswith(('storage/catalog/','definitions/')):
            for member in members(json.loads(p.read_bytes())):
                key=f"storage/payloads/sha256/{member['blob_sha256'][:2]}/{member['blob_sha256']}.{member['format']}"
                if not (root/key).is_file(): externals[key]=member
        if destination:
            target=destination/relative;target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(p,target)
            if digest(target)!=(sha,size): raise ValueError('Export mismatch: '+relative)
    relocated=[]
    for relative,member in sorted(externals.items()):
        data=store.payload(member)
        if hashlib.sha256(data).hexdigest()!=member['blob_sha256'] or len(data)!=member['byte_count']:
            raise ValueError('External payload verification failed')
        row={'path':relative,'sha256':member['blob_sha256'],'bytes':len(data)}
        if destination:
            target=destination/relative;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
        entries.append(row);relocated.append(row)
    result={'schema':'gambit_migration_manifest_v1','status':'quiescent_export' if destination else 'inventory_only_not_a_consistent_backup',
        'entries':entries,'external_payloads':relocated,'file_count':len(entries),'bytes':sum(x['bytes'] for x in entries)}
    if destination:
        (destination/'migration-manifest.json').write_text(json.dumps(result,sort_keys=True,separators=(',',':'))+'\n')
        verify(destination,result)
    return result

def verify(root,manifest):
    root=Path(root).resolve();seen=set()
    for row in manifest['entries']:
        relative=Path(row['path']);path=root/relative
        if relative.is_absolute() or '..' in relative.parts or path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ValueError('Unsafe manifest path')
        if row['path'] in seen:raise ValueError('Duplicate manifest path')
        seen.add(row['path'])
        if digest(path)!=(row['sha256'],row['bytes']):raise ValueError('Verification mismatch: '+row['path'])
    return len(seen)

def export(root,destination):
    root=Path(root).resolve()
    with ExitStack() as stack:
        for name in ('research-worker-service','research-executor','research-writer'):
            if not stack.enter_context(lock(root,name,nonblocking=True)):
                raise ValueError('Stop and drain services before export: '+name+' is owned')
        for p in (root/'storage/catalog/operations/jobs').glob('*.json'):
            if json.loads(p.read_bytes()).get('status') in {'queued','resolving','preparing','p1','p2'}:
                raise ValueError('Drain all accepted jobs before export')
        return inventory(root,destination)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['inventory','export','verify'])
    parser.add_argument('--root',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.action=='verify':
        value=json.loads(args.output.read_bytes());print('Verified files:',verify(args.root,value));return
    result=export(args.root,args.output) if args.action=='export' else inventory(args.root)
    if args.action=='inventory':
        args.output.write_text(json.dumps(result,sort_keys=True,separators=(',',':'))+'\n')
    print(json.dumps({key:result[key] for key in ('status','file_count','bytes')}))
    print('Referenced external payloads:',len(result['external_payloads']))
if __name__=='__main__':main()
