"""Physical storage for unchanged FX row-lineage records.

Immutable checksummed packs/catalogs are authoritative. SQLite is a disposable
locator, rebuilt under a lock after loss/corruption or catalog membership change.
No scientific identity, reference, policy or materialization schema changes.
"""
from collections import OrderedDict
from contextlib import contextmanager
from copy import deepcopy
import fcntl
import gzip
import hashlib
import json
import os
import re
import sqlite3
import tempfile
import zlib

from data.alfred_onboarding import stable_read, strict_json
from data.catalog_reads import reading
from research.performance import measure
from data.fx_feature_contracts import validate_record
from data.transformations.contracts import normalize_reference
from data.transformations.identity import canonical_bytes, digest, reference

CATALOG = 'storage/catalog/lineage_packs'
INDEX = 'storage/temporary/lineage-packs.sqlite3'
LOCK = 'storage/temporary/lineage-packs-index.lock'
MAX_ROWS = 1024
MAX_BYTES = 8 * 1024 * 1024
HEX = re.compile(r'[0-9a-f]{64}\Z')


def _error(message):
    from data.feature_store import PublicationError
    return PublicationError('Lineage pack: ' + message)


def _key(binding):
    normalize_reference(binding)
    return tuple(binding[k] for k in ('id', 'version', 'content_sha256'))


def _signature(path):
    value = path.stat()
    return (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns)


@contextmanager
def _locked(store):
    path = store.path(LOCK)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+b') as stream:
        with measure('lock.wait.lineage_index'):
            fcntl.flock(stream, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def _catalog(store, pack_id):
    if not isinstance(pack_id, str) or not HEX.fullmatch(pack_id):
        raise _error('invalid locator')
    path = store.path(f'{CATALOG}/{pack_id}.json')
    if path.stat().st_size > 512 * 1024:
        raise _error('catalog exceeds bound')
    value = strict_json(stable_read(path))
    if (set(value) != {'format', 'payload', 'raw_bytes', 'raw_sha256', 'references'}
            or value['format'] != 'fx_row_lineage_pack_v1' or digest(value) != pack_id):
        raise _error('catalog identity differs')
    refs = value['references']
    if not isinstance(refs, list) or not 1 <= len(refs) <= MAX_ROWS:
        raise _error('invalid record count')
    keys = [_key(r) for r in refs]
    if keys != sorted(set(keys)) or len({k[:2] for k in keys}) != len(keys):
        raise _error('duplicate, conflicting or unordered references')
    member = value['payload']
    if (set(member) != {'role', 'blob_sha256', 'format', 'byte_count', 'row_count'}
            or member['role'] != 'fx_row_lineage_pack' or member['format'] != 'bin'
            or not isinstance(member['blob_sha256'], str) or not HEX.fullmatch(member['blob_sha256'])
            or type(member['byte_count']) is not int or not 0 < member['byte_count'] <= MAX_BYTES
            or member['row_count'] != len(refs)
            or type(value['raw_bytes']) is not int or not 0 < value['raw_bytes'] <= MAX_BYTES
            or not isinstance(value['raw_sha256'], str) or not HEX.fullmatch(value['raw_sha256'])):
        raise _error('invalid payload bounds')
    return value


def _records(store, pack_id, value=None):
    value = _catalog(store, pack_id) if value is None else value
    member = value['payload']
    path = store.path(f"storage/payloads/sha256/{member['blob_sha256'][:2]}/{member['blob_sha256']}.bin")
    if path.stat().st_size != member['byte_count']:
        raise _error('compressed byte count differs')
    data = stable_read(path, member['blob_sha256'])
    decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
    try:
        raw = decoder.decompress(data, MAX_BYTES + 1)
    except zlib.error as exc:
        raise _error('invalid compressed payload') from exc
    if (len(raw) != value['raw_bytes'] or len(raw) > MAX_BYTES or not decoder.eof
            or decoder.unused_data or decoder.unconsumed_tail
            or hashlib.sha256(raw).hexdigest() != value['raw_sha256']):
        raise _error('uncompressed content differs or exceeds bound')
    lines = raw.splitlines()
    if len(lines) != len(value['references']):
        raise _error('record count differs')
    result = {}
    for line, binding in zip(lines, value['references']):
        row = strict_json(line)
        validate_record(row)
        if (row['record_type'] != 'fx_feature_lineage_record' or reference(row) != binding
                or canonical_bytes(row) != line):
            raise _error('record identity or canonical content differs')
        result[_key(binding)] = row
    if b''.join(canonical_bytes(r) + b'\n' for r in result.values()) != raw:
        raise _error('noncanonical record framing')
    return result


def _generation(store):
    path = store.path(CATALOG)
    with reading(path):
        return json.dumps(_signature(path))


def _rebuild_locked(store):
    """Publish a complete derived index atomically; never edit immutable records."""
    directory = store.path(CATALOG)
    generation = _generation(store)
    index = store.path(INDEX)
    index.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='lineage-index-', dir=index.parent)
    os.close(fd)
    db = None
    try:
        db = sqlite3.connect(temporary)
        db.execute('CREATE TABLE metadata (generation TEXT NOT NULL)')
        db.execute('CREATE TABLE records (id TEXT, version TEXT, hash TEXT, pack TEXT, '
                   'PRIMARY KEY(id,version)) WITHOUT ROWID')
        for path in sorted(directory.glob('*.json')):
            pack_id = path.stem
            value = _catalog(store, pack_id)
            for binding in value['references']:
                key = _key(binding)
                found = db.execute('SELECT hash FROM records WHERE id=? AND version=?', key[:2]).fetchone()
                if found and found[0] != key[2]:
                    raise _error('conflicting record identity across packs')
                db.execute('INSERT OR IGNORE INTO records VALUES (?,?,?,?)', (*key, pack_id))
        if _generation(store) != generation:
            raise _error('catalog changed during index reconstruction')
        db.execute('INSERT INTO metadata VALUES (?)', (generation,))
        db.commit(); db.close(); db = None
        with open(temporary, 'rb') as stream:
            os.fsync(stream.fileno())
        os.replace(temporary, index)
        descriptor = os.open(index.parent, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    finally:
        if db is not None:
            db.close()
        if os.path.exists(temporary):
            os.unlink(temporary)


class PackedLineage:
    def __init__(self, store):
        self.store = store
        self.packs = OrderedDict()
        self.locators = OrderedDict()
        self.index_signature = None

    def _find(self, binding, *, rebuild_missing):
        store = self.store
        if not store.path(CATALOG).exists():
            from data.verified_inputs import probe
            # A new pack catalog may introduce a conflicting lineage identity.
            # Unrelated trial/publication folders do not alter this absence.
            probe(store.path(CATALOG))
            parent = store.path('storage/catalog')
            if parent.exists():
                with reading(parent, scientific=False):
                    pass
            return None
        key = _key(binding)
        index = store.path(INDEX)
        for attempt in range(2):
            try:
                signature = (_signature(index), _generation(store))
                if signature != self.index_signature:
                    self.locators.clear()
                    self.index_signature = signature
                found = self.locators.get(key[:2])
                if found is None:
                    db = sqlite3.connect(index.as_uri() + '?mode=ro', uri=True)
                    try:
                        generation = db.execute('SELECT generation FROM metadata').fetchall()
                        if generation != [(signature[1],)]:
                            raise sqlite3.DatabaseError('stale locator')
                        found = db.execute('SELECT hash,pack FROM records WHERE id=? AND version=?', key[:2]).fetchone()
                    finally:
                        db.close()
                # Track only successfully read index states; reconstruction is
                # derived maintenance, not a dependency of the scientific data.
                with reading(index):
                    if _signature(index) != signature[0]:
                        raise sqlite3.DatabaseError('locator changed during read')
                if found:
                    if found[0] != key[2]:
                        raise _error('requested reference conflicts with stored identity')
                    return found[1]
                if not rebuild_missing or attempt:
                    return None
            except (sqlite3.Error, FileNotFoundError):
                if attempt:
                    raise _error('lookup index could not be recovered')
            with _locked(store):
                _rebuild_locked(store)
        return None

    def resolve(self, binding, *, rebuild_missing=True):
        pack_id = self._find(binding, rebuild_missing=rebuild_missing)
        if pack_id is None:
            return None
        catalog_path = self.store.path(f'{CATALOG}/{pack_id}.json')
        with reading(catalog_path):
            catalog_signature = _signature(catalog_path)
            cached = self.packs.pop(pack_id, None)
            catalog = cached[1] if cached and cached[0][0] == catalog_signature else _catalog(self.store, pack_id)
            member = catalog['payload']
            path = self.store.path(f"storage/payloads/sha256/{member['blob_sha256'][:2]}/{member['blob_sha256']}.bin")
            with reading(path):
                signature = (catalog_signature, _signature(path))
                records = cached[2] if cached and cached[0] == signature else _records(self.store, pack_id, catalog)
                self.packs[pack_id] = (signature, catalog, records)
                while len(self.packs) > 2:
                    self.packs.popitem(last=False)
        if _key(binding)[:2] not in self.locators:
            for key in records:
                self.locators[key[:2]] = (key[2], pack_id)
        while len(self.locators) > MAX_ROWS * 2:
            self.locators.popitem(last=False)
        row = records.get(_key(binding))
        if row is None:
            raise _error('locator does not resolve requested record')
        return deepcopy(row)


def storage_mode():
    """Operational rollout switch; never part of a scientific identity."""
    mode = os.environ.get('GAMBIT_FX_LINEAGE_STORAGE', 'loose')
    if mode not in ('loose', 'packed_v1'):
        raise _error('unknown GAMBIT_FX_LINEAGE_STORAGE mode')
    return mode


def install_records(store, records, *, fail_at=None):
    """Called under the Feature writer lock; index lock is always acquired second."""
    if not records or len(records) > MAX_ROWS:
        raise _error('invalid publication batch size')
    ordered = sorted(records, key=lambda r: _key(reference(r)))
    if len({_key(reference(r))[:2] for r in ordered}) != len(ordered):
        raise _error('duplicate publication identity')
    reader = PackedLineage(store)
    for row in ordered:
        validate_record(row)
        if row['record_type'] != 'fx_feature_lineage_record':
            raise _error('only FX row lineage may be packed')
        binding = reference(row)
        loose = store.path(f"storage/catalog/lineage/{row['id']}/manifest.json")
        if loose.exists() and strict_json(stable_read(loose)) != row:
            raise _error('conflicting loose record')
        existing = reader.resolve(binding, rebuild_missing=False)
        if existing is not None and existing != row:
            raise _error('conflicting packed record')
    raw = b''.join(canonical_bytes(r) + b'\n' for r in ordered)
    if len(raw) > MAX_BYTES:
        raise _error('publication exceeds byte bound')
    compressed = gzip.compress(raw, mtime=0)
    if len(compressed) > MAX_BYTES:
        raise _error('compressed publication exceeds byte bound')
    with _locked(store):
        previous_generation = _generation(store) if store.path(CATALOG).exists() else None
        payload = store.io.blob(compressed, 'bin', 'fx_row_lineage_pack', len(ordered))
        if fail_at == 'pack_payload':
            raise _error('injected interruption before pack catalog')
        catalog = {'format': 'fx_row_lineage_pack_v1', 'payload': payload,
                   'raw_bytes': len(raw), 'raw_sha256': hashlib.sha256(raw).hexdigest(),
                   'references': [reference(r) for r in ordered]}
        pack_id = digest(catalog)
        path = store.path(f'{CATALOG}/{pack_id}.json')
        existed = path.exists()
        store.io.install(str(path.relative_to(store.root)), canonical_bytes(catalog) + b'\n')
        _records(store, pack_id)
        if fail_at == 'pack_catalog':
            raise _error('injected interruption before index update')
        # Reconcile pre-existing orphan catalogs before marking this append
        # current. A prior interrupted writer must never become invisible.
        index = store.path(INDEX)
        try:
            db = sqlite3.connect(index.as_uri() + '?mode=rw', uri=True)
            try:
                generation = db.execute('SELECT generation FROM metadata').fetchall()
                expected = _generation(store) if existed else previous_generation
                if generation != [(expected,)]:
                    raise sqlite3.DatabaseError('stale locator')
                for row in catalog['references']:
                    key = _key(row)
                    old = db.execute('SELECT hash FROM records WHERE id=? AND version=?', key[:2]).fetchone()
                    if old and old[0] != key[2]:
                        raise _error('conflicting indexed identity')
                    db.execute('INSERT OR IGNORE INTO records VALUES (?,?,?,?)', (*key, pack_id))
                db.execute('DELETE FROM metadata')
                db.execute('INSERT INTO metadata VALUES (?)', (_generation(store),))
                db.commit()
            finally:
                db.close()
        except sqlite3.Error:
            _rebuild_locked(store)
        if fail_at == 'pack_index':
            raise _error('injected interruption after index update')
    return pack_id
