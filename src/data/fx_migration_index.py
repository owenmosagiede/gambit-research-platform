"""Disposable, disk-backed ownership index. Never archives research records."""
from collections.abc import Mapping
import hashlib
import logging
import os
from pathlib import Path
import sqlite3
import tempfile
from data.alfred_onboarding import stable_read,strict_json

BASE='storage/catalog/operations/fx_currency_migration'


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


def inventory(root):
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
        return strict_json(stable_read(self.root/path,self.files[path]['sha256']))


class MigrationIndex:
    def __init__(self,root):
        self.root=root
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
            ''')
            logging.getLogger(__name__).info('Migration inventory: hashing files')
            self.files=inventory(self.root);self.records=Records(self.root,self.files)
            logging.getLogger(__name__).info('Migration inventory: %s file commitments; indexing ownership',len(self.files))
            for n,path in enumerate(self.records):
                self.add(path,self.records[path],references=False)
                if n%1000==0:self.db.commit()
            self.db.commit()
            logging.getLogger(__name__).info('Migration inventory: indexing references')
            for n,path in enumerate(self.records):
                self.add_references(path,self.records[path])
                if n%1000==0:self.db.commit()
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
        # Retain only attributes used by eligibility checks, never full records.
        metadata={k:record[k] for k in ('id','record_type','schema_version','layer','canonical_request_id') if k in record}
        body=record.get('body',{});definition=record.get('definition',{})
        if record.get('layer')=='membership' and not isinstance(definition,dict):raise ValueError('Invalid membership definition')
        metadata['_body_is_mapping']=isinstance(body,dict)
        metadata['body']={'kind':body.get('kind') if isinstance(body,dict) else None}
        metadata['definition']={'id':definition.get('id') if isinstance(definition,dict) else None}
        self.db.execute('INSERT OR REPLACE INTO records VALUES(?,?)',(path,json.dumps(metadata)))
        for table,values in [('scopes',_scopes(record)),('owners',_identities(record)),('blobs',_blobs(record))]:
            self.db.execute('DELETE FROM '+table+' WHERE path=?',(path,))
            self.db.executemany('INSERT INTO '+table+' VALUES(?,?)',((path,v) for v in values))
        if references:self.add_references(path,record)
    def add_references(self,path,record):
        from data.fx_currency_migration import _strings
        self.db.execute('DELETE FROM refs WHERE path=?',(path,))
        values=list(_strings(record))
        # Only exact strings equal to a catalog ownership identity can affect
        # closure, artifact sharing or retained-consumer checks. This two-pass
        # semijoin avoids indexing millions of irrelevant observation values.
        for start in range(0,len(values),200):
            part=values[start:start+200]
            found=[r[0] for r in self.db.execute('SELECT DISTINCT value FROM owners WHERE value IN ('+','.join('?' for _ in part)+')',part)]
            self.db.executemany('INSERT OR IGNORE INTO refs VALUES(?,?)',((path,v) for v in found))
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
    def referenced(self,value,removed,artifact_prefix,index):
        if removed:
            query='SELECT 1 FROM refs r JOIN selected s ON s.path=r.path WHERE r.value=? LIMIT 1';args=(value,)
        else:
            query='''SELECT 1 FROM refs r WHERE r.value=? AND r.path!=? AND substr(r.path,1,?)!=?
                AND NOT EXISTS(SELECT 1 FROM selected s WHERE s.path=r.path) LIMIT 1'''
            args=(value,index,len(artifact_prefix),artifact_prefix)
        return self.db.execute(query,args).fetchone() is not None
    def removed_blobs(self):
        return (r[0] for r in self.db.execute('''SELECT DISTINCT b.value FROM blobs b JOIN selected s ON s.path=b.path
            WHERE NOT EXISTS(SELECT 1 FROM blobs k WHERE k.value=b.value AND NOT EXISTS
                (SELECT 1 FROM selected x WHERE x.path=k.path)) ORDER BY b.value'''))
