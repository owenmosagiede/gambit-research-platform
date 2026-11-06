"""Closed, immutable SQLite generations with an atomic publication pointer."""
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile
import time

SCHEMA = 1
GENERATION = re.compile(r'[0-9a-f]{32}\Z')
# Production metadata already exceeds the original 256 MiB pilot allocation.
# Keep a bounded generation plus room for current, previous and the next build.
MAX_DATABASE_BYTES = 1024 * 1024 * 1024
MAX_DIRECTORY_BYTES = 4 * MAX_DATABASE_BYTES


def file_digest(path):
    """Hash a generation without loading its size into publisher memory."""
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(chunk)
    return result.hexdigest()

class Unavailable(ValueError):
    pass

class IntegrityFailure(Unavailable):
    pass

class CursorExpired(Unavailable):
    pass


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def signature(path):
    path = Path(path)
    if path.is_symlink():
        raise IntegrityFailure('Symlink is not a serving file')
    st = path.stat()
    return [st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns]


def confined(directory, name):
    directory = Path(directory).absolute()
    path = directory / name
    if directory.resolve() != directory or path.is_symlink() or path.resolve().parent != directory:
        raise IntegrityFailure('Serving path is not confined')
    return path


def read_document(path, maximum=1024 * 1024):
    before = signature(path)
    if before[2] > maximum:
        raise Unavailable('Serving document exceeds its bound')
    data = Path(path).read_bytes()
    if signature(path) != before:
        raise Unavailable('Serving document changed during read')
    return json.loads(data)


def atomic(directory, name, value):
    directory = Path(directory)
    destination = confined(directory, name)
    fd, temporary = tempfile.mkstemp(prefix='.publish-', dir=directory)
    try:
        with os.fdopen(fd, 'w') as stream:
            # The separate web account reads through the serving group. mkstemp
            # starts at 0600 regardless of the service's umask.
            os.fchmod(stream.fileno(), 0o640)
            stream.write(encoded(value) + '\n'); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, destination)
        sync_directory(directory)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)


def sync_directory(directory):
    fd = os.open(directory, os.O_RDONLY)
    try: os.fsync(fd)
    finally: os.close(fd)


def connect(path, *, writable=False):
    # Never use immutable=1: read-only mode also fails safely on unexpected files.
    connection = sqlite3.connect(Path(path).as_uri() + ('?mode=rw' if writable else '?mode=ro'), uri=True, timeout=1)
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA foreign_keys=ON')
    if not writable: connection.execute('PRAGMA query_only=ON')
    return connection


def initialize(db):
    db.executescript('''
    PRAGMA journal_mode=DELETE;
    PRAGMA foreign_keys=ON;
    CREATE TABLE IF NOT EXISTS sources(path TEXT PRIMARY KEY, signature TEXT NOT NULL, sha256 TEXT NOT NULL, checked REAL NOT NULL);
    CREATE TABLE IF NOT EXISTS units(kind TEXT, id TEXT, dependencies TEXT NOT NULL, value TEXT NOT NULL, PRIMARY KEY(kind,id));
    CREATE TABLE IF NOT EXISTS experiments(id TEXT PRIMARY KEY, status TEXT NOT NULL, queue_key TEXT NOT NULL, updated TEXT NOT NULL,
        recipe TEXT, scope TEXT, direction TEXT, search TEXT NOT NULL, value TEXT NOT NULL);
    CREATE INDEX IF NOT EXISTS experiment_queue ON experiments(status,queue_key,id);
    CREATE INDEX IF NOT EXISTS experiment_queue_order ON experiments(CASE WHEN status IN ('resolving','preparing','p1','p2') THEN 0 WHEN status='queued' THEN 1 ELSE 2 END,queue_key,id);
    CREATE INDEX IF NOT EXISTS experiment_history ON experiments(updated DESC,id);
    CREATE INDEX IF NOT EXISTS experiment_recipe ON experiments(recipe,scope,direction);
    CREATE TABLE IF NOT EXISTS aliases(id TEXT PRIMARY KEY, canonical_id TEXT NOT NULL, value TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS relationships(id TEXT PRIMARY KEY, value TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS trials(id TEXT PRIMARY KEY, value TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS decisions(id TEXT PRIMARY KEY, value TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS recipes(id TEXT PRIMARY KEY, name TEXT NOT NULL, search TEXT NOT NULL, value TEXT NOT NULL);
    CREATE INDEX IF NOT EXISTS recipe_name ON recipes(name,id);
    CREATE TABLE IF NOT EXISTS branches(id TEXT PRIMARY KEY, recipe TEXT NOT NULL REFERENCES recipes(id),
        relationship TEXT NOT NULL REFERENCES relationships(id), scope TEXT, direction TEXT, horizon INTEGER, outcome TEXT,
        value TEXT NOT NULL);
    CREATE INDEX IF NOT EXISTS branch_recipe ON branches(recipe,id);
    CREATE INDEX IF NOT EXISTS branch_outcome ON branches(outcome,scope,direction,horizon);
    CREATE TABLE IF NOT EXISTS issues(id INTEGER PRIMARY KEY, value TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
    ''')


def current(directory, generation=None):
    directory = Path(directory).absolute()
    try:
        status_path = confined(directory, 'status.json')
        status_signature = signature(status_path)
        status = read_document(status_path)
        if status.get('unavailable'):
            raise Unavailable('Projection verification failed; prior rows are not current certification')
        pointer = read_document(confined(directory, 'current.json'))
        selected = generation or pointer['generation']
        if not GENERATION.fullmatch(selected): raise ValueError('Invalid generation')
        manifest = read_document(confined(directory, 'generation-' + selected + '.json'))
        if manifest['schema_version'] != SCHEMA or manifest['generation'] != selected:
            raise Unavailable('Incompatible serving generation')
        path = confined(directory, 'generation-' + selected + '.sqlite')
        if signature(path) != manifest['database_signature']:
            raise Unavailable('Serving database changed')
        if signature(status_path) != status_signature:
            raise Unavailable('Integrity status changed')
        return path, manifest
    except FileNotFoundError as exc:
        if generation: raise CursorExpired('This page has expired; refresh to the latest records') from exc
        raise Unavailable('The dedicated read model is not available yet') from exc
    except (KeyError, TypeError, json.JSONDecodeError, sqlite3.Error) as exc:
        raise Unavailable('Invalid serving generation') from exc


def freshness(manifest, *, now=None):
    age = (time.time() if now is None else now) - manifest['observed_epoch']
    state = 'unknown' if age < -5 else 'stale' if age > 300 else 'delayed' if age > 60 else 'current'
    return {'generation': manifest['generation'], 'observed_at': manifest['observed_at'],
            'published_at': manifest['published_at'], 'age_seconds': max(0, round(age, 1)),
            'state': state, 'complete': manifest['issue_count'] == 0,
            'verification': 'stored metadata; numerical payloads are not revalidated by page reads'}
