#!/usr/bin/env python3
"""Create a deterministic, source-only release. Does not upload or include live data."""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import tarfile

SECRET=re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|dop_v1_[0-9a-f]{64}|AKIA[0-9A-Z]{16}')

def build(root,output):
    root=Path(root).resolve();payloads={}
    for folder in ('src','ui','tools','deploy','tests'):
        for p in sorted((root/folder).rglob('*')):
            rel=p.relative_to(root)
            if '__pycache__' in p.parts or 'private' in rel.parts or p.suffix in ('.pyc','.log'):continue
            if p.is_symlink():raise ValueError('No symlinks allowed in release')
            if not p.is_file() or p.name.startswith('.'):continue
            if p.suffix in ('.key','.pem') or p.name.startswith(('credentials','secrets')):raise ValueError('Credential-like file in release')
            data=p.read_bytes()
            if SECRET.search(data):raise ValueError('Secret pattern flagged; review before releasing '+str(rel))
            payloads[rel.as_posix()]=data
    for name in ('requirements-data.txt','requirements-cloud.lock'):
        payloads[name]=(root/name).read_bytes()
    entries=[{'path':name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()} for name,data in sorted(payloads.items())]
    manifest={'schema':'gambit_source_release_v1','scope':'source_and_isolated_tests_no_live_storage_or_definitions',
              'python_target':'3.14.8','files':entries}
    manifest_bytes=json.dumps(manifest,sort_keys=True,separators=(',',':')).encode()+b'\n'
    payloads['release-manifest.json']=manifest_bytes
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('xb') as stream,gzip.GzipFile(filename='',mode='wb',fileobj=stream,mtime=0) as compressed,tarfile.open(fileobj=compressed,mode='w') as archive:
        for name,data in sorted(payloads.items()):
            info=tarfile.TarInfo(name);info.size=len(data);info.mode=0o644;info.mtime=0
            archive.addfile(info,io.BytesIO(data))
    sha=hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix(output.suffix+'.sha256').write_text(sha+'  '+output.name+'\n')
    print(json.dumps({'source_files':len(entries),'archive_bytes':output.stat().st_size,'sha256':sha}))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();build(a.root,a.output)
