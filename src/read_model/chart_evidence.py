"""Bounded, optional chart projection. HTTP reads only the serving cache.

The offline publisher opens exact referenced artifacts read-only. It never calls
research, locks a research writer, or changes source records. Charts are display
summaries, not new evaluations or validation decisions.
"""
from datetime import date, datetime, timezone
from contextlib import closing, contextmanager
from contextvars import ContextVar
import os
import sys
import hashlib
import json
import math
from pathlib import Path
import re
import time

from research.contracts import digest, ref
from . import query
from .storage import (Unavailable, atomic, confined, current, connect, encoded,
                      read_document, signature)

VERSION = 1
MAX_PAYLOAD = 64 * 1024 * 1024
MAX_TRIAL_BYTES = 128 * 1024 * 1024
MAX_CACHE = 512 * 1024
MAX_POINTS = 1200
MAX_AGE = 24 * 3600
HEX = re.compile(r'[0-9a-f]{64}\Z')
SMALL = {'stability', 'blocks', 'leaveouts', 'robustness_slices', 'scheduled_hac'}


_GUARD = ContextVar('chart_source_guard', default=None)
_HOOK_INSTALLED = False


def _audit(event, args):
    root = _GUARD.get()
    if root is None: return
    if event == 'open':
        name, mode, flags = args
        if isinstance(name, (str, bytes, os.PathLike)):
            if Path(os.fsdecode(name)).absolute().resolve().is_relative_to(root) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND):
                raise PermissionError('Chart projector cannot write research')
    elif event in ('os.remove','os.rename','os.mkdir','os.rmdir','os.link','os.symlink','os.chmod','os.chown','os.truncate'):
        for name in args[:2] if event in ('os.rename','os.link','os.symlink') else args[:1]:
            if isinstance(name,(str,bytes,os.PathLike)) and Path(os.fsdecode(name)).absolute().resolve().is_relative_to(root):
                raise PermissionError('Chart projector cannot mutate research')
    elif event in ('subprocess.Popen','os.system'):
        raise PermissionError('Chart projector cannot launch research')


@contextmanager
def source_read_only(root):
    global _HOOK_INSTALLED
    if not _HOOK_INSTALLED:
        sys.addaudithook(_audit); _HOOK_INSTALLED = True
    token=_GUARD.set(Path(root).resolve()); old=sys.dont_write_bytecode;sys.dont_write_bytecode=True
    try: yield
    finally: sys.dont_write_bytecode=old;_GUARD.reset(token)


def source_path(root, relative):
    path = Path(root).absolute() / relative
    if path.resolve() != path or not path.is_relative_to(Path(root).absolute()):
        raise Unavailable('Unconfined evidence path')
    return path


def number(value):
    if isinstance(value, bool) or value is None: raise ValueError('Missing number')
    n = float(value)
    if not math.isfinite(n): raise ValueError('Nonfinite evidence')
    return n


def _rows(stream):
    """Incremental JSON array decoder; no full aligned sample in memory."""
    decoder = json.JSONDecoder(parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite JSON')))
    buffer = ''; eof = False
    def more():
        nonlocal buffer, eof
        chunk = stream.read(65536); eof = not chunk; buffer += chunk
        if len(buffer) > 1024 * 1024: raise Unavailable('Evidence row exceeds bound')
    def space():
        nonlocal buffer
        buffer = buffer.lstrip()
        while not buffer and not eof: more(); buffer = buffer.lstrip()
    space()
    if not buffer.startswith('['): raise ValueError('Expected array')
    buffer = buffer[1:]; space()
    if buffer.startswith(']'): buffer = buffer[1:]
    else:
        while True:
            while True:
                try: row, end = decoder.raw_decode(buffer); break
                except json.JSONDecodeError:
                    if eof: raise
                    more()
            if not isinstance(row, dict): raise ValueError('Expected evidence row')
            buffer = buffer[end:]; yield row; space()
            if buffer.startswith(']'): buffer = buffer[1:]; break
            if not buffer.startswith(','): raise ValueError('Expected separator')
            buffer = buffer[1:]; space()
    space()
    if buffer: raise ValueError('Trailing evidence bytes')


def _chart(path, mode, check):
    points=[]; stride=1; count=0; total=0.; last=None; previous=None
    with path.open('r', encoding='utf-8') as stream:
        for row in _rows(stream):
            check()
            if mode == 'CS':
                stamp = row.get('anchor_date', row.get('date'))
                if date.fromisoformat(stamp).isoformat() != stamp or previous and stamp <= previous:
                    raise ValueError('Invalid IC date order')
                previous = stamp
                if row.get('rank_ic') is None: continue
                total += number(row['rank_ic'])
                if not math.isfinite(total): raise ValueError('Invalid chart sum')
                point={'x':stamp, 'y':total, 'date':stamp}
            else:
                if row.get('feature') is None or row.get('target') is None: continue
                point={'x':number(row['feature']), 'y':number(row['target']), 'date':row.get('date')}
            if count % stride == 0: points.append(point)
            count += 1; last = point
            if len(points) >= MAX_POINTS:
                points = points[::2]; stride *= 2
    if last is not None and (not points or points[-1] != last): points.append(last)
    return {'kind':'cumulative_rank_ic' if mode=='CS' else 'scatter', 'available':bool(count),
            'points':points, 'total_count':count, 'display_count':len(points),
            'display_reduction':'deterministic thinning; every usable IC contributes to the cumulative sum' if mode=='CS' else 'deterministic thinning; regression statistics are unchanged'}


def _small(value):
    if isinstance(value, list):
        if len(value) > 128: raise Unavailable('Block evidence exceeds bound')
        return [_small(v) for v in value]
    if isinstance(value, dict):
        return {k:_small(v) for k,v in value.items() if k not in ('usable_dates','lag_pair_counts')}
    return value


def project_trial(root, trial, *, deadline=None):
    """Verify selected artifact roles, including the same bytes used for charts."""
    mode = trial['body']['mode']
    if mode not in {'CS','TS'}: raise ValueError('Unsupported mode')
    def check():
        if deadline is not None and time.monotonic() >= deadline: raise TimeoutError('Chart work budget exhausted')
    authority = ref(trial)
    source = read_document(source_path(root, 'storage/catalog/trial_ledger/records/'+trial['id']+'.json'), 4*1024*1024)
    if source != trial or ref(source) != authority: raise ValueError('Trial differs from verified metadata')
    wanted = SMALL | ({'cross_sectional_ic_history'} if mode=='CS' else {'aligned_sample'})
    chart={'kind':'cumulative_rank_ic' if mode=='CS' else 'scatter','available':False,'points':[]}
    artifacts={}; seen=set(); checked=[]; consumed=0
    for reference in trial['body'].get('artifact_manifests', []):
        check()
        if not re.fullmatch(r'ARTIFACT_[0-9a-f]{64}', reference['id']): raise ValueError('Invalid artifact')
        manifest=read_document(source_path(root,'storage/catalog/trial_artifacts/'+reference['id']+'/manifest.json'))
        if ref(manifest)!=reference or manifest['id']!='ARTIFACT_'+digest({k:v for k,v in manifest.items() if k!='id'}):
            raise ValueError('Artifact mismatch')
        if manifest['scientific_key_sha256'] != digest(trial['scientific_key']): raise ValueError('Artifact belongs to another trial')
        for member in manifest['members']:
            role=member['role']
            if role in seen: raise ValueError('Ambiguous evidence role')
            seen.add(role)
            if role not in wanted: continue
            check(); sha=member['blob_sha256']; size=member['byte_count']
            if not HEX.fullmatch(sha) or member['format']!='json' or type(size) is not int or not 0<size<=MAX_PAYLOAD:
                raise Unavailable('Evidence exceeds bound or has invalid identity')
            consumed += size
            if consumed>MAX_TRIAL_BYTES: raise Unavailable('Trial evidence exceeds bound')
            path=source_path(root,f'storage/payloads/sha256/{sha[:2]}/{sha}.json'); before=signature(path)
            if before[2]!=size: raise ValueError('Evidence length mismatch')
            actual=hashlib.sha256()
            with path.open('rb') as stream:
                for chunk in iter(lambda:stream.read(65536),b''): check(); actual.update(chunk)
            if actual.hexdigest()!=sha: raise ValueError('Evidence hash mismatch')
            if role in SMALL:
                artifacts[role]=_small(read_document(path,1024*1024))
            else: chart=_chart(path,mode,check)
            if signature(path)!=before: raise ValueError('Evidence changed during projection')
            check(); checked.append({'role':role,'blob_sha256':sha})
    value={'version':VERSION,'authority':authority,'artifact_manifests':trial['body'].get('artifact_manifests',[]),
           'verified_at':datetime.now(timezone.utc).isoformat(), 'verified_epoch':time.time(),
           'chart':chart,'artifacts':artifacts,'verified_roles':checked,
           'verification':'Referenced chart roles only; saved research decisions are unchanged.'}
    if len(encoded(value).encode())>MAX_CACHE: raise Unavailable('Chart summary exceeds bound')
    return value


def read_evidence(directory, trial_id, generation=None):
    data=query.detail(directory,'trial',trial_id,generation)
    record=data.pop('record'); data.pop('numerical_evidence',None)
    path=confined(Path(directory)/'charts',trial_id+'.json')
    try:
        wrapper=read_document(path,MAX_CACHE+1024); value=wrapper['value']
        if wrapper['sha256']!=digest(value) or value['version']!=VERSION or value['authority']!=ref(record) or value['artifact_manifests']!=record['body'].get('artifact_manifests',[]):
            raise ValueError('Chart cache does not match exact trial')
        if not 0 <= time.time()-value['verified_epoch'] <= MAX_AGE: raise ValueError('Chart verification expired')
        if not value.get('available',True): raise ValueError('Chart evidence unavailable')
        return dict(data,**value)
    except (OSError,ValueError,KeyError,TypeError) as exc:
        raise Unavailable('Chart evidence has not been independently verified; stored metrics remain available') from exc


def build(root, directory, *, max_trials=4, seconds=30):
    """One bounded rotating pass; explicit opt-in, no scheduler."""
    import fcntl
    root=Path(root).resolve(); directory=Path(directory).absolute()
    if directory.resolve()!=directory or directory.is_relative_to(root) or root.is_relative_to(directory): raise ValueError('Serving output must be outside research root')
    if not 1<=max_trials<=100 or not 1<=seconds<=600: raise ValueError('Invalid work budget')
    chartdir=directory/'charts'
    if chartdir.resolve()!=chartdir: raise ValueError('Symlink chart directory')
    chartdir.mkdir(exist_ok=True, mode=0o750)
    total=0
    for count,p in enumerate(chartdir.iterdir()):
        total += p.stat().st_size
        if count>=20000 or total>512*1024*1024: raise Unavailable('Chart cache capacity reached')
    with confined(chartdir,'publisher.lock').open('a+b') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        path,_=current(directory); deadline=time.monotonic()+seconds; completed=0; issues=[]
        # Bound metadata iteration; a cursor rotates through older trial IDs.
        cursorpath=confined(chartdir,'cursor.json')
        try: after=read_document(cursorpath)['after']
        except FileNotFoundError: after=''
        with closing(connect(path)) as db:
            rows=db.execute('SELECT id,value FROM trials WHERE id>? ORDER BY id LIMIT ?', (after,max_trials)).fetchall()
            if not rows: rows=db.execute('SELECT id,value FROM trials ORDER BY id LIMIT ?', (max_trials,)).fetchall()
        for row in rows:
            if time.monotonic()>=deadline: break
            trial=json.loads(row['value'])
            try:
                try:
                    cached=read_evidence(directory,row['id'])
                    if time.time()-cached['verified_epoch']<MAX_AGE/2:
                        atomic(chartdir,'cursor.json',{'after':row['id']}); continue
                except Unavailable: pass
                with source_read_only(root):
                    value=project_trial(root,trial,deadline=deadline)
                atomic(chartdir,row['id']+'.json',{'value':value,'sha256':digest(value)}); completed+=1
            except (OSError,ValueError,KeyError,TypeError,TimeoutError) as exc:
                # Revoke previously published chart evidence on any failed refresh.
                value={'available':False,'error':type(exc).__name__}
                atomic(chartdir,row['id']+'.json',{'value':value,'sha256':digest(value)})
                issues.append({'trial':row['id'],'error':type(exc).__name__})
            atomic(chartdir,'cursor.json',{'after':row['id']})
        return {'published':completed,'issues':issues,'research_unchanged':True}
