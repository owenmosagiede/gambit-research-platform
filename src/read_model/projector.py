"""Explicitly invoked metadata projector. No import-time work or writer hooks."""
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
import fcntl
import hashlib
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
import time
import uuid

from read_model.storage import (SCHEMA, MAX_DATABASE_BYTES, MAX_DIRECTORY_BYTES, IntegrityFailure, file_digest,
    atomic, confined, connect, current, encoded, initialize, read_document, signature, sync_directory)

_GUARD = ContextVar('serving_source_guard', default=None)
_HOOK_INSTALLED = False


def _audit(event, args):
    root = _GUARD.get()
    if root is None: return
    if event == 'open':
        name, mode, flags = args
        if isinstance(name, (str, bytes, os.PathLike)):
            path = Path(os.fsdecode(name)).absolute().resolve()
            if path.is_relative_to(root):
                relative = path.relative_to(root).as_posix()
                if flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND):
                    raise PermissionError('Projector cannot write research storage')
                if relative.startswith(('storage/payloads/', 'storage/catalog/lineage/', 'storage/catalog/trial_artifacts/')):
                    raise PermissionError('Projector cannot inspect numerical evidence or lineage payloads')
    elif event in ('os.remove', 'os.rename', 'os.mkdir', 'os.rmdir', 'os.link', 'os.symlink', 'os.chmod', 'os.chown', 'os.truncate'):
        for name in args[:2] if event in ('os.rename', 'os.link', 'os.symlink') else args[:1]:
            if isinstance(name, (str, bytes, os.PathLike)) and Path(os.fsdecode(name)).absolute().resolve().is_relative_to(root):
                raise PermissionError('Projector cannot mutate research storage')
    elif event in ('subprocess.Popen', 'os.system'):
        raise PermissionError('Projector cannot launch research or repair commands')


@contextmanager
def source_read_only(root):
    global _HOOK_INSTALLED
    if not _HOOK_INSTALLED:
        sys.addaudithook(_audit); _HOOK_INSTALLED = True
    token = _GUARD.set(Path(root).resolve())
    old = sys.dont_write_bytecode; sys.dont_write_bytecode = True
    try: yield
    finally:
        sys.dont_write_bytecode = old; _GUARD.reset(token)


def stamp():
    return datetime.now(timezone.utc).isoformat()


def build(root, directory, *, timeout=600, max_bytes=MAX_DIRECTORY_BYTES, fail_at=None):
    root = Path(root).resolve(); directory = Path(directory).absolute()
    if directory.resolve() != directory or directory.is_relative_to(root) or root.is_relative_to(directory):
        raise ValueError('Serving output must be separate from the research tree')
    directory.mkdir(parents=True, exist_ok=True, mode=0o750)
    lock_path = confined(directory, 'projector.lock')
    with lock_path.open('a+b') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return _build(root, directory, timeout, max_bytes, fail_at)


def _build(root, directory, timeout, max_bytes, fail_at):
    from read_model.extract import Extractor
    started = time.monotonic(); observed = stamp(); epoch = time.time()
    total = sum(p.stat().st_size for p in directory.iterdir() if p.is_file())
    if total >= max_bytes: raise OSError('Serving directory budget exhausted; clean expired derived generations')
    fd, name = tempfile.mkstemp(prefix='.build-', suffix='.sqlite', dir=directory); os.close(fd)
    stage = Path(name); db = None
    generation = uuid.uuid4().hex; previous_generation = None; published = False
    final = confined(directory, 'generation-' + generation + '.sqlite')
    try:
        # Read even an unavailable previous generation for its immutable-source
        # baseline. Never discard that baseline to silently accept changed inputs.
        pointer = directory / 'current.json'
        if pointer.exists():
            old = read_document(pointer)
            previous_generation = old['generation']
            from read_model.storage import GENERATION
            if not GENERATION.fullmatch(old['generation']): raise IntegrityFailure('Invalid previous generation')
            previous = confined(directory, 'generation-' + old['generation'] + '.sqlite')
            manifest = read_document(confined(directory, 'generation-' + old['generation'] + '.json'))
            if signature(previous) != manifest['database_signature'] or file_digest(previous) != manifest['database_sha256']:
                raise IntegrityFailure('Previous derived generation is corrupt; recovery required')
            if manifest['schema_version'] != SCHEMA: raise IntegrityFailure('Incompatible previous generation')
            shutil.copyfile(previous, stage)
        db = sqlite3.connect(stage); db.row_factory = sqlite3.Row; initialize(db)
        code_root = Path(__file__).resolve().parents[1]
        extractor_fingerprint = hashlib.sha256(encoded({p.relative_to(code_root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
            for folder in ('read_model','api','research','runtime','data','contracts')
            for p in sorted((code_root/folder).rglob('*.py'))}).encode()).hexdigest()
        previous_extractor = db.execute("SELECT value FROM metadata WHERE key='extractor_fingerprint'").fetchone()
        if previous_extractor and previous_extractor[0] != encoded(extractor_fingerprint):
            db.execute('DELETE FROM units')  # Reverify, retaining immutable-source baselines.
        with source_read_only(root):
            extraction = Extractor(root, db, now=epoch, deadline=started + timeout).run()
        metadata = {'schema_version': SCHEMA, 'extractor_version': '1.0.0',
                    'extractor_fingerprint': extractor_fingerprint,
                    'generation': generation, 'observed_at': observed, 'observed_epoch': epoch,
                    'issue_count': len(extraction['issues']), 'source_inventory': extraction['inventory_sha256']}
        for key, value in metadata.items(): db.execute('INSERT OR REPLACE INTO metadata VALUES(?,?)', (key, encoded(value)))
        db.commit()
        if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok' or db.execute('PRAGMA foreign_key_check').fetchone():
            raise IntegrityFailure('Derived database failed integrity checks')
        counts = {table: db.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0] for table in
                  ('experiments', 'aliases', 'recipes', 'branches', 'trials', 'decisions', 'issues')}
        semantic = hashlib.sha256()
        for table in ('experiments','aliases','recipes','branches','relationships','trials','decisions'):
            semantic.update(table.encode())
            for record in db.execute('SELECT value FROM ' + table + ' ORDER BY id'):
                semantic.update(record[0].encode()); semantic.update(b'\n')
        metadata['projection_sha256'] = semantic.hexdigest()
        db.close(); db = None
        database_bytes = stage.stat().st_size
        if database_bytes > MAX_DATABASE_BYTES or total + database_bytes > max_bytes:
            raise OSError(f'Derived database exceeds serving disk budget: database={database_bytes}, '
                          f'database_limit={MAX_DATABASE_BYTES}, retained={total}, directory_limit={max_bytes}')
        if fail_at == 'database': raise RuntimeError('Injected pre-publication failure')
        with stage.open('rb') as stream: os.fsync(stream.fileno())
        os.chmod(stage, 0o440); os.replace(stage, final); sync_directory(directory)
        metadata.update(database_sha256=file_digest(final), database_bytes=database_bytes,
                        database_signature=signature(final), published_at=stamp(), counts=counts,
                        extraction={k:v for k,v in extraction.items() if k != 'issues'},
                        build_seconds=round(time.monotonic() - started, 3))
        atomic(directory, 'generation-' + generation + '.json', metadata)
        if fail_at == 'manifest': raise RuntimeError('Injected pre-pointer failure')
        # Keep a detected integrity failure fail-closed until a fully successful
        # build. Clearing status before pointer would briefly certify old rows.
        atomic(directory, 'current.json', {'generation': generation, 'previous_generation': previous_generation})
        published = True
        atomic(directory, 'status.json', {'unavailable': False, 'generation': generation, 'checked_at': stamp()})
        return metadata
    except IntegrityFailure as exc:
        atomic(directory, 'status.json', {'unavailable': True, 'checked_at': stamp(),
              'reason': 'SOURCE_OR_GENERATION_INTEGRITY', 'message': str(exc)})
        raise
    finally:
        if db is not None: db.close()
        if stage.exists(): stage.unlink()
        for suffix in ('-journal', '-wal', '-shm'):
            extra = Path(str(stage) + suffix)
            if extra.exists(): extra.unlink()
        if not published:
            try:
                referenced = pointer.exists() and read_document(pointer).get('generation') == generation
            except Exception:
                referenced = True  # Preserve evidence if pointer fsync/read failed.
            if not referenced:
                final.unlink(missing_ok=True)
                confined(directory, 'generation-' + generation + '.json').unlink(missing_ok=True)


def cleanup(directory, *, retention_seconds=3600, max_bytes=MAX_DIRECTORY_BYTES):
    """Only expired derived generations; current and previous are always retained."""
    directory = Path(directory).absolute()
    with confined(directory, 'projector.lock').open('a+b') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        pointer = read_document(confined(directory, 'current.json'))
        active = pointer['generation']
        manifests = sorted(directory.glob('generation-*.json'), key=lambda p:p.stat().st_mtime, reverse=True)
        keep = {active, pointer.get('previous_generation')}
        if 'previous_generation' not in pointer:
            keep.update(p.stem.removeprefix('generation-') for p in manifests[:2])
        total = sum(p.stat().st_size for p in directory.iterdir() if p.is_file())
        # Reserve room for the bounded next generation. Space pressure can expire
        # old cursors early, but must never erase the current/previous baseline.
        for manifest in reversed(manifests):
            generation = manifest.stem.removeprefix('generation-')
            from read_model.storage import GENERATION
            if not GENERATION.fullmatch(generation) or generation in keep: continue
            if time.time()-manifest.stat().st_mtime < retention_seconds and total <= max_bytes-MAX_DATABASE_BYTES: continue
            database = confined(directory, 'generation-' + generation + '.sqlite')
            total -= manifest.stat().st_size + (database.stat().st_size if database.exists() else 0)
            database.unlink(missing_ok=True)
            confined(directory, manifest.name).unlink()
        sync_directory(directory)
