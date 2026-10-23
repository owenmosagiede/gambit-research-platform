"""Disposable, disk-backed ownership index. Never archives research records."""
from collections.abc import Mapping
import hashlib
import logging
import os
import re
from pathlib import Path
import sqlite3
import tempfile
from data.alfred_onboarding import stable_read,strict_json

BASE='storage/catalog/operations/fx_currency_migration'
HEARTBEAT='storage/catalog/operations/worker_service.json'


def file_commitment(path):
    path=Path(path)
    if path.is_symlink():raise ValueError('Symbolic file is unsupported: '+str(path))
    before=path.stat();sha=hashlib.sha256();size=0
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):sha.update(block);size+=len(block)
    after=path.stat()
    if (before.st_ino,before.st_size,before.st_mtime_ns)!=(after.st_ino,after.st_size,after.st_mtime_ns):
        raise ValueError('Inventory changed during read: '+str(path))
    return {'sha256':sha.hexdigest(),'bytes':size}


def inventory(root,*,online=False):
    """Keep compact commitments only; never decode records during apply hashing."""
    root=Path(root).resolve();files={}
    for folder in ('definitions','storage/catalog','config'):
        for directory,dirs,names in os.walk(root/folder,followlinks=False):
            for name in dirs+names:
                p=Path(directory)/name
                if p.is_symlink():raise ValueError('Migration refuses symbolic links: '+p.relative_to(root).as_posix())
            for name in sorted(names):
                p=Path(directory)/name;relative=p.relative_to(root).as_posix()
                if not p.is_file() or relative.startswith(BASE+'/') or p.suffix=='.lock':continue
                if online and relative==HEARTBEAT:continue
                files[relative]=file_commitment(p)
    return files


class Records(Mapping):
    def __init__(self,root,files):
        self.root=Path(root);self.files=files;self.overlay={}
    def __iter__(self):
        return (p for p in self.files if p.endswith('.json') and not p.startswith('config/'))
    def __len__(self):return sum(1 for _ in self)
    def __getitem__(self,path):
        if path in self.overlay:return self.overlay[path]
        if path not in self.files or not path.endswith('.json') or path.startswith('config/'):raise KeyError(path)
        try:return strict_json(stable_read(self.root/path,self.files[path]['sha256']))
        except ValueError as exc:raise ValueError('Catalog record changed or invalid: '+path+': '+str(exc)) from exc


class MigrationIndex:
    def __init__(self,root,*,watched_values=(),watched_name=None,watched_paths=(),online=False):
        self.root=root;self.online=online;self.watched_values=set(watched_values);self.watched_name=watched_name
        self.watched_paths=tuple(watched_paths)
    def __enter__(self):
        self.temp=tempfile.TemporaryDirectory(prefix='gambit-migration-index-')
        try:
            self.db=sqlite3.connect(str(Path(self.temp.name)/'index.sqlite'))
            self.db.executescript('''
                PRAGMA cache_size=-16384;
                PRAGMA temp_store=FILE;
                CREATE TABLE records(path TEXT PRIMARY KEY, metadata TEXT NOT NULL) WITHOUT ROWID;
                CREATE TABLE refs(path TEXT, value TEXT, PRIMARY KEY(path,value)) WITHOUT ROWID;
                CREATE INDEX refs_value ON refs(value,path);
                CREATE TABLE owners(path TEXT,value TEXT,PRIMARY KEY(path,value)) WITHOUT ROWID;
                CREATE INDEX owners_value ON owners(value,path);
                CREATE TABLE scopes(path TEXT,value TEXT,PRIMARY KEY(path,value)) WITHOUT ROWID;
                CREATE TABLE blobs(path TEXT,value TEXT,PRIMARY KEY(path,value)) WITHOUT ROWID;
                CREATE INDEX blobs_value ON blobs(value,path);
                CREATE TABLE selected(path TEXT PRIMARY KEY) WITHOUT ROWID;
                CREATE TABLE dependencies(path TEXT,value TEXT,PRIMARY KEY(path,value)) WITHOUT ROWID;
            ''')
            logging.getLogger(__name__).info('Migration inventory: hashing files')
            self.files=inventory(self.root,online=self.online);self.records=Records(self.root,self.files)
            logging.getLogger(__name__).info('Migration inventory: %s file commitments; indexing ownership',len(self.files))
            for n,path in enumerate(self.records):
                self.add(path,self.records[path],references=False)
                if n%1000==0:self.db.commit()
                if n and n%25000==0:logging.getLogger(__name__).info('Migration ownership: %s records',n)
            self.db.commit()
            logging.getLogger(__name__).info('Migration inventory: indexing references')
            for n,path in enumerate(self.records):
                self.add_references(path,self.records[path])
                if n%1000==0:self.db.commit()
                if n and n%25000==0:logging.getLogger(__name__).info('Migration references: %s records',n)
            # Configuration and operational logs can also name preparation inputs.
            for path in self.files:
                if path.endswith('.json') and not path.startswith('config/'):continue
                if self.watched_name or self.watched_values or self.watched_paths:
                    raw=stable_read(Path(self.root)/path,self.files[path]['sha256'])
                    self.watch(path,[raw.decode('utf-8',errors='replace')],text=True)
            self.db.commit()
            logging.getLogger(__name__).info('Migration inventory: index ready')
            return self
        except BaseException:
            self.__exit__(None,None,None);raise
    def __exit__(self,*args):
        if hasattr(self,'db'):self.db.close()
        self.temp.cleanup()
    def add(self,path,record,*,references=True):
        import json
        from data.fx_currency_migration import _strings,_scopes,_identities,_blobs
        from data.fx_operational_retirement import PILOT_FILES
        if isinstance(record,list):
            # These frozen operator tables own no identities. Their nested
            # references, scopes and payload references still enter the index.
            pattern=r'storage/catalog/operations/momentum-preparation-\d{4}-\d{2}-\d{2}/(?:instrument-preparation-matrix|scope-coverage-matrix|progress/[0-9a-f]{64}/scope-coverage)\.json'
            if not re.fullmatch(pattern,path) or not all(isinstance(row,dict) for row in record):
                raise ValueError('Unsupported catalog list: '+path)
            fields={}
        elif isinstance(record,dict):fields=record
        else:raise ValueError('Unsupported catalog root: '+path)
        # Retain only attributes used by eligibility checks, never full records.
        metadata={k:fields[k] for k in ('id','record_type','schema_version','layer','canonical_request_id') if k in fields}
        body=fields.get('body',{});definition=fields.get('definition',{})
        if fields.get('layer')=='membership' and not isinstance(definition,dict):raise ValueError('Invalid membership definition')
        metadata['_body_is_mapping']=isinstance(body,dict)
        metadata['body']={'kind':body.get('kind') if isinstance(body,dict) else None}
        metadata['definition']={'id':definition.get('id') if isinstance(definition,dict) else None}
        self.db.execute('INSERT OR REPLACE INTO records VALUES(?,?)',(path,json.dumps(metadata)))
        # Saved pilot input/preview copies refer to the authoritative batch;
        # their copied batch_id is not a second owner of that identity.
        owners=set() if path in PILOT_FILES else _identities(record)
        for table,values in [('scopes',_scopes(record)),('owners',owners),('blobs',_blobs(record))]:
            self.db.execute('DELETE FROM '+table+' WHERE path=?',(path,))
            self.db.executemany('INSERT INTO '+table+' VALUES(?,?)',((path,v) for v in values))
        if references:self.add_references(path,record)
    def add_references(self,path,record):
        from data.fx_currency_migration import _strings
        self.db.execute('DELETE FROM refs WHERE path=?',(path,))
        values=list(_strings(record))
        self.watch(path,values)
        if self.watched_name or self.watched_values or self.watched_paths:self.watch_keys(path,record)
        # Only exact strings equal to a catalog ownership identity can affect
        # closure, artifact sharing or retained-consumer checks. This two-pass
        # semijoin avoids indexing millions of irrelevant observation values.
        for start in range(0,len(values),200):
            part=values[start:start+200]
            found=[r[0] for r in self.db.execute('SELECT DISTINCT value FROM owners WHERE value IN ('+','.join('?' for _ in part)+')',part)]
            self.db.executemany('INSERT OR IGNORE INTO refs VALUES(?,?)',((path,v) for v in found))
    def watch(self,path,values,*,text=False):
        if not self.watched_values and not self.watched_name and not self.watched_paths:return
        for value in values:
            matches=self.watched_values.intersection([value,*re.findall(r'(?<![0-9a-f])[0-9a-f]{64}(?![0-9a-f])',value)])
            if self.watched_name and self.watched_name in value:matches.add(self.watched_name)
            if 'storage/catalog/operations/' in value:matches.update(p for p in self.watched_paths if p in value)
            self.db.executemany('INSERT OR IGNORE INTO dependencies VALUES(?,?)',((path,v) for v in matches))
    def watch_keys(self,path,value):
        if isinstance(value,dict):
            self.watch(path,value.keys())
            for v in value.values():self.watch_keys(path,v)
        elif isinstance(value,list):
            for v in value:self.watch_keys(path,v)
    def dependencies(self):
        return list(self.db.execute('SELECT path,value FROM dependencies ORDER BY path,value'))
    def replace(self,replacements):
        from data.fx_currency_migration import _identities
        for p,r in replacements.items():
            if _identities(r)!=_identities(self.records[p]):raise ValueError('Reconciliation changed ownership identities')
            self.records.overlay[p]=r;self.add(p,r)
    def metadata(self):
        import json
        for path,raw in self.db.execute('SELECT path,metadata FROM records ORDER BY path'):yield path,json.loads(raw)
    def scope(self,path):return {r[0] for r in self.db.execute('SELECT value FROM scopes WHERE path=?',(path,))}
    def select(self,paths):
        self.db.executemany('INSERT OR IGNORE INTO selected VALUES(?)',((p,) for p in paths))
    def related(self):
        return {r[0] for r in self.db.execute('''SELECT DISTINCT r.path FROM refs r JOIN owners o ON o.value=r.value
            JOIN selected s ON s.path=o.path WHERE NOT EXISTS(SELECT 1 FROM selected x WHERE x.path=r.path)''')}
    def referenced(self,value,removed,artifact_prefix,index,excluded_paths=()):
        if removed:
            extra=' AND r.path NOT IN ('+','.join('?' for _ in excluded_paths)+')' if excluded_paths else ''
            query='SELECT 1 FROM refs r JOIN selected s ON s.path=r.path WHERE r.value=?'+extra+' LIMIT 1';args=(value,*excluded_paths)
        else:
            query='''SELECT 1 FROM refs r WHERE r.value=? AND r.path!=? AND substr(r.path,1,?)!=?
                AND NOT EXISTS(SELECT 1 FROM selected s WHERE s.path=r.path) LIMIT 1'''
            args=(value,index,len(artifact_prefix),artifact_prefix)
        return self.db.execute(query,args).fetchone() is not None
    def removed_blobs(self,excluded_prefix="",excluded_paths=()):
        # Preparation tables reference published payloads; they never own them.
        extra=' AND b.path NOT IN ('+','.join('?' for _ in excluded_paths)+')' if excluded_paths else ''
        return (r[0] for r in self.db.execute('''SELECT DISTINCT b.value FROM blobs b JOIN selected s ON s.path=b.path
            WHERE (?='' OR substr(b.path,1,length(?))!=?)
            AND NOT EXISTS(SELECT 1 FROM blobs k WHERE k.value=b.value AND NOT EXISTS
                (SELECT 1 FROM selected x WHERE x.path=k.path))'''+extra+' ORDER BY b.value',(excluded_prefix,excluded_prefix,excluded_prefix,*excluded_paths)))
