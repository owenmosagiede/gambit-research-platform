#!/usr/bin/env python3
"""Quiescent copies, encrypted off-host backups, and isolated restore checks.

Deployment code only. Never changes scientific records or resumes jobs itself.
The service manager drains the worker; queued submissions survive the copy.
"""
import argparse
from contextlib import ExitStack, contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import sqlite3
import subprocess
import tempfile

VOLUME = Path('/srv/gambit')
STATE = Path('/var/lib/gambit-backup')
STAGE = STATE / 'staging/current'
CONFIGURATION = Path('/etc/gambit')
UNITS = ('gambit-worker.service', 'gambit-web.service')
LOCKS = ('research-worker-service', 'research-executor', 'research-writer')
MAX_QUIESCENT_SECONDS = 30 * 60


class SourceChanged(RuntimeError):
    pass


def tree(root, *, omit=False, volatile=False):
    """Stream directory entries without retaining a complete Path inventory."""
    root = Path(root)
    def visit(directory):
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    path = Path(entry.path)
                    if omit and omitted(path.relative_to(root)): continue
                    yield path
                    if entry.is_dir(follow_symlinks=False): yield from visit(path)
        except FileNotFoundError:
            if not volatile: raise
    yield from visit(root)


def signature(path):
    value = path.stat()
    return json.dumps([value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns,
                       value.st_ctime_ns, value.st_mode], separators=(',', ':'))


@contextmanager
def copy_deadline(seconds=MAX_QUIESCENT_SECONDS):
    """Bound only the stopped-services copy; never interrupt worker draining."""
    def expired(signum, frame):
        raise TimeoutError('Quiescent backup reconciliation exceeded its time limit')
    old_handler = signal.signal(signal.SIGALRM, expired)
    old_timer = signal.setitimer(signal.ITIMER_REAL, seconds)
    try: yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, *old_timer)
        signal.signal(signal.SIGALRM, old_handler)


def now():
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix='.status-')
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream, sort_keys=True)
            stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
        descriptor = os.open(path.parent, os.O_RDONLY)
        try: os.fsync(descriptor)
        finally: os.close(descriptor)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)


def digest(path):
    before = path.stat()
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    after = path.stat()
    if (before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns):
        raise SourceChanged('File changed while copying: ' + str(path))
    return value.hexdigest(), after.st_size


def omitted(path):
    # Runtime ownership must be re-established on recovery, never restored stale.
    return (any(p in {'__pycache__', '.git', '.venv', 'venv'} for p in path.parts)
            or path.suffix == '.pyc'
            or (path.parts[0] == 'storage' and path.suffix == '.lock')
            or path.name in {'worker_service.json', '.DS_Store'})


def copy_tree(source, destination, *, index=None, label='', reconcile=False):
    source = Path(source)
    if source.is_symlink() or not source.is_dir():
        raise RuntimeError('Backup source must be an ordinary directory: ' + str(source))
    destination.mkdir(parents=True, exist_ok=reconcile, mode=0o700)
    for path in tree(source, omit=True, volatile=index is not None and not reconcile):
        relative = path.relative_to(source)
        if path.is_symlink(): raise RuntimeError('Backup refuses symlinks: ' + str(path))
        target = destination / relative
        if target.is_symlink(): raise RuntimeError('Symlink in staged backup')
        if reconcile and target.exists() and target.is_dir() != path.is_dir():
            if target.is_dir(): shutil.rmtree(target)
            else: target.unlink()
        if path.is_dir():
            target.mkdir(exist_ok=True, mode=path.stat().st_mode & 0o777)
        elif path.is_file():
            key = (Path(label) / relative).as_posix()
            try:
                current = signature(path)
                previous = index.execute('select signature from files where path=?', (key,)).fetchone() if index is not None else None
                if reconcile and previous == (current,) and target.is_file():
                    index.execute('update files set seen=1 where path=?', (key,))
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                before = digest(path)
                shutil.copy2(path, target)
                if digest(target) != before or digest(path) != before:
                    raise SourceChanged('Backup copy mismatch: ' + str(path))
                if signature(path) != current:
                    raise SourceChanged('File changed while copying: ' + str(path))
                if index is not None:
                    index.execute('insert or replace into files values (?,?,?,?,?)',
                                  (key, current, before[0], before[1], int(reconcile)))
            except (SourceChanged, FileNotFoundError):
                if index is None or reconcile: raise
                # A live file can change during precopy. It is never accepted
                # until recopy/reconciliation under the existing writer locks.
                continue
        else:
            if path.exists(): raise RuntimeError('Backup refuses special files: ' + str(path))
            if reconcile or index is None: raise FileNotFoundError(path)


def sqlite_checks(root):
    checked = []
    for path in tree(root):
        if path.is_symlink(): raise RuntimeError('Symlink in staged backup')
        if not path.is_file(): continue
        with path.open('rb') as stream:
            if stream.read(16) != b'SQLite format 3\x00': continue
        # SQLite may create SHM files even for read-only WAL access. Check a
        # temporary clone, preserving the exact backed-up database/WAL bytes.
        with tempfile.TemporaryDirectory(prefix='gambit-sqlite-check-') as folder:
            clone = Path(folder) / path.name
            shutil.copyfile(path, clone)
            for suffix in ('-wal', '-shm'):
                sidecar = Path(str(path) + suffix)
                if sidecar.exists(): shutil.copyfile(sidecar, Path(str(clone) + suffix))
            db = sqlite3.connect(clone.as_uri() + '?mode=ro', uri=True)
            try:
                result = db.execute('PRAGMA integrity_check').fetchall()
                if result != [('ok',)]: raise RuntimeError('SQLite integrity check failed: ' + str(path))
            finally: db.close()
        checked.append(path.relative_to(root).as_posix())
    return sorted(checked)


def seal(root, index=None):
    checked = sqlite_checks(root)
    count = total = 0
    # The spool is outside the sealed tree. Neither Paths nor manifest rows are
    # accumulated in RAM, including while restic subsequently runs.
    with tempfile.TemporaryFile(mode='w+t', dir=root.parent) as spool:
        for path in tree(root):
            if path.is_symlink(): raise RuntimeError('Symlink in staged backup')
            if not path.is_file() or path == root / 'backup-manifest.json': continue
            relative = path.relative_to(root).as_posix()
            sha, size = digest(path)
            if index is not None:
                expected = index.execute('select sha256,bytes from files where path=? and seen=1', (relative,)).fetchone()
                if expected != (sha, size): raise RuntimeError('Staged backup changed after verified copy: ' + relative)
            spool.write(json.dumps({'path': relative, 'sha256': sha, 'bytes': size}, separators=(',', ':')) + '\n')
            count += 1; total += size
        value = {'schema': 'gambit_backup_v1', 'created_at': now(), 'consistency': 'worker_drained_web_stopped_writer_locks_held',
                 'file_count': count, 'bytes': total, 'sqlite_checked': checked}
        fd, temporary = tempfile.mkstemp(dir=root, prefix='.manifest-')
        try:
            with os.fdopen(fd, 'w') as stream:
                stream.write('{"entries":[')
                spool.seek(0)
                for number, row in enumerate(spool):
                    if number: stream.write(',')
                    stream.write(row.rstrip('\n'))
                stream.write('],')
                stream.write(json.dumps(value, sort_keys=True)[1:] + '\n')
                stream.flush(); os.fsync(stream.fileno())
            os.replace(temporary, root / 'backup-manifest.json')
            descriptor = os.open(root, os.O_RDONLY)
            try: os.fsync(descriptor)
            finally: os.close(descriptor)
        finally:
            if os.path.exists(temporary): os.unlink(temporary)
    return value


class JsonReader:
    """Bounded JSON token reader for both historical and new v1 manifests."""
    def __init__(self, stream):
        self.stream, self.buffer, self.position, self.eof = stream, '', 0, False
        self.decoder = json.JSONDecoder()

    def fill(self):
        remaining = self.buffer[self.position:]
        if len(remaining) > 1024 * 1024: raise RuntimeError('Oversized backup manifest entry')
        chunk = self.stream.read(64 * 1024)
        self.buffer, self.position = remaining + chunk, 0
        self.eof = not chunk

    def peek(self):
        while True:
            while self.position < len(self.buffer) and self.buffer[self.position].isspace(): self.position += 1
            if self.position < len(self.buffer): return self.buffer[self.position]
            if self.eof: return ''
            self.fill()

    def take(self, token):
        if self.peek() != token: raise RuntimeError('Malformed backup manifest')
        self.position += 1

    def value(self):
        self.peek()
        while True:
            try: value, end = self.decoder.raw_decode(self.buffer, self.position)
            except json.JSONDecodeError:
                if self.eof: raise RuntimeError('Malformed backup manifest') from None
                self.fill(); continue
            # A scalar number may end exactly on a read boundary. Refill before
            # accepting it so 123 + 456 cannot be parsed as the value 123.
            if not self.eof and (end == len(self.buffer) or self.buffer[end] not in ' \t\r\n,}:]'):
                self.fill(); continue
            self.position = end
            return value


def manifest_entries(stream, metadata):
    reader = JsonReader(stream); reader.take('{'); keys = set()
    while reader.peek() != '}':
        if keys: reader.take(',')
        key = reader.value()
        if not isinstance(key, str) or key in keys: raise RuntimeError('Duplicate or invalid backup manifest key')
        keys.add(key); reader.take(':')
        if key == 'entries':
            reader.take('['); first = True
            while reader.peek() != ']':
                if not first: reader.take(',')
                first = False
                entry = reader.value()
                if not isinstance(entry, dict): raise RuntimeError('Invalid backup manifest entry')
                yield entry
            reader.take(']')
        else: metadata[key] = reader.value()
    reader.take('}')
    if reader.peek() or 'entries' not in keys or metadata.get('schema') != 'gambit_backup_v1':
        raise RuntimeError('Malformed or unsupported backup manifest')


def verify(root):
    root = Path(root).resolve(); value = {}; count = total = 0
    # Uniqueness is checked on disk; a Python set of every path also grows too
    # large on the real research store. The restored tree remains read-only.
    with tempfile.TemporaryDirectory(prefix='gambit-backup-inventory-') as folder:
        seen = sqlite3.connect(Path(folder) / 'inventory.sqlite3')
        try:
            seen.execute('pragma cache_size=-2048'); seen.execute('pragma journal_mode=off')
            seen.execute('create table paths (path text primary key) without rowid')
            with (root / 'backup-manifest.json').open() as stream:
                for entry in manifest_entries(stream, value):
                    relative = Path(entry['path']); path = root / relative
                    if (relative.is_absolute() or '..' in relative.parts or path.is_symlink()
                            or relative.as_posix() != entry['path'] or not path.resolve().is_relative_to(root)):
                        raise RuntimeError('Unsafe or duplicate backup manifest path')
                    try: seen.execute('insert into paths values (?)', (entry['path'],))
                    except sqlite3.IntegrityError: raise RuntimeError('Unsafe or duplicate backup manifest path') from None
                    if digest(path) != (entry['sha256'], entry['bytes']):
                        raise RuntimeError('Restored byte mismatch: ' + entry['path'])
                    count += 1; total += entry['bytes']
        finally: seen.close()
    actual = 0
    for path in tree(root):
        if path.is_symlink(): raise RuntimeError('Symlink in restored backup')
        if path.is_file() and path != root / 'backup-manifest.json': actual += 1
    if actual != count or count != value['file_count'] or total != value['bytes']:
        raise RuntimeError('Restored file inventory mismatch')
    if sqlite_checks(root) != value['sqlite_checked']:
        raise RuntimeError('Restored SQLite inventory mismatch')
    return {'files_verified': count, 'bytes_verified': total, 'sqlite_checked': value['sqlite_checked']}


class Services:
    def remember(self, units):
        atomic_json(STATE / 'services-to-restart.json', {'units': units, 'updated_at': now()})

    def state(self, unit):
        return subprocess.check_output(['systemctl', 'show', '--property=ActiveState', '--value', unit], text=True).strip()

    def stop(self, unit):
        # No timeout/kill escalation: worker's unit has TimeoutStopSec=infinity.
        subprocess.run(['systemctl', 'stop', unit], check=True)

    def start(self, unit):
        subprocess.run(['systemctl', 'start', unit], check=True)


@contextmanager
def quiescent(root, services):
    original = {unit: services.state(unit) for unit in UNITS}
    if any(value not in {'active', 'inactive', 'failed'} for value in original.values()):
        raise RuntimeError('Service transition in progress; retry backup later')
    stopped = []
    try:
        # Drain while UI can still serve and accept durable queued submissions.
        for unit in UNITS:
            if original[unit] == 'active':
                stopped.append(unit)
                if hasattr(services, 'remember'): services.remember(stopped)
                services.stop(unit)
            if services.state(unit) not in {'inactive', 'failed'}:
                raise RuntimeError('Service did not stop: ' + unit)
        with ExitStack() as stack:
            for name in LOCKS:
                path = root / 'storage/catalog/operations' / (name + '.lock')
                path.parent.mkdir(parents=True, exist_ok=True)
                stream = stack.enter_context(path.open('a+b'))
                # The root-run first backup may create these before the worker.
                # Keep runtime locks accessible to the storage service owner.
                if os.geteuid() == 0:
                    owner = (root / 'storage').stat()
                    os.chown(path.parent, owner.st_uid, owner.st_gid)
                    os.fchown(stream.fileno(), owner.st_uid, owner.st_gid)
                    os.fchmod(stream.fileno(), 0o600)
                try: fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError as error: raise RuntimeError('Writer still owns ' + name) from error
            yield
    finally:
        errors = []
        for unit in reversed(stopped):
            try: services.start(unit)
            except Exception as error: errors.append(str(error))
        if errors: raise RuntimeError('Service restart failed: ' + '; '.join(errors))
        if hasattr(services, 'remember'): services.remember([])


def recover_services():
    """ExecStopPost also runs after process death, using the recorded active set."""
    path = STATE / 'services-to-restart.json'
    if not path.exists(): return
    value = json.loads(path.read_text())
    units = value['units']
    if not isinstance(units, list) or any(u not in UNITS for u in units):
        raise RuntimeError('Invalid backup service recovery journal')
    services = Services()
    for unit in reversed(units): services.start(unit)
    services.remember([])


def stage(sources, destination, services, progress=None):
    root = sources['research_platform']
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False, mode=0o700)
    def report(phase):
        if progress: progress(phase)
    with tempfile.TemporaryDirectory(prefix='gambit-precopy-', dir=destination.parent) as folder:
        index = sqlite3.connect(Path(folder) / 'verified.sqlite3')
        try:
            index.execute('pragma cache_size=-2048'); index.execute('pragma journal_mode=off')
            index.execute('create table files (path text primary key, signature text, sha256 text, bytes integer, seen integer) without rowid')
            report('precopy_services_online')
            for label, source in sources.items():
                if Path(label).name != label or label in {'.', '..', ''}: raise RuntimeError('Unsafe backup label')
                copy_tree(source, destination / label, index=index, label=label)
            index.commit()
            with quiescent(root, services):
                with copy_deadline():
                    report('quiescent_reconciliation')
                    for label, source in sources.items():
                        copy_tree(source, destination / label, index=index, label=label, reconcile=True)
                    for path in tree(destination):
                        if path.is_symlink(): raise RuntimeError('Symlink in staged backup')
                        if path.is_file() and not index.execute('select 1 from files where path=? and seen=1', (path.relative_to(destination).as_posix(),)).fetchone():
                            path.unlink()  # Disposable precopy only; never the authority.
                    index.commit()
            # All remaining reads are against the completed private copy. Source
            # writers and the website can run throughout SQLite/hash verification.
            report('verifying_staged_copy_services_online')
            return seal(destination, index)
        finally: index.close()


def restic(*args):
    # Credentials are supplied by the root-only service EnvironmentFile.
    result = subprocess.run(['restic', *args], check=True, text=True, capture_output=True)
    return result.stdout


def run_backup():
    if not VOLUME.is_mount(): raise RuntimeError('Research volume is not mounted')
    root = VOLUME / 'research_platform'
    if not (root / 'migration-manifest.json').is_file(): raise RuntimeError('Production migration is not installed')
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (STATE / 'backup.lock').open('a+b') as guard:
        fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
        status = {'started_at': now(), 'status': 'staging'}
        atomic_json(STATE / 'status.json', status)
        try:
            if STAGE.is_symlink(): raise RuntimeError('Unsafe staging directory')
            if STAGE.exists(): shutil.rmtree(STAGE)  # Disposable copy only; never the authority.
            sources = {'research_platform': root, 'auth': VOLUME / 'auth', 'configuration': CONFIGURATION}
            size = sum(p.stat().st_size for source in sources.values() for p in tree(source, omit=True)
                       if p.is_file() and not p.is_symlink())
            if shutil.disk_usage(STATE).free < size * 1.1 + 1024 ** 3:
                raise RuntimeError('Insufficient backup staging capacity; services were not stopped')
            def progress(phase):
                status.update(phase=phase, phase_started_at=now())
                atomic_json(STATE / 'status.json', status)
            manifest = stage(sources, STAGE, Services(), progress)
            status.update(status='uploading', staged_files=manifest['file_count'], staged_bytes=manifest['bytes'])
            atomic_json(STATE / 'status.json', status)
            output = restic('backup', '--json', '--tag', 'gambit-production', str(STAGE))
            summary = next(json.loads(line) for line in output.splitlines() if json.loads(line).get('message_type') == 'summary')
            snapshot = summary['snapshot_id']
            # Retention applies only to production snapshots from this stable path.
            restic('forget', '--tag', 'gambit-production', '--path', str(STAGE), '--keep-daily', '7', '--keep-weekly', '4', '--prune')
            restic('check')
            status.update(status='succeeded', finished_at=now(), snapshot_id=snapshot)
            atomic_json(STATE / 'status.json', status)
            print(json.dumps(status))
        except Exception as error:
            # Do not include subprocess output/environment: it may contain secrets.
            status.update(status='failed', finished_at=now(), error_type=type(error).__name__)
            atomic_json(STATE / 'status.json', status)
            raise


def restore_check(snapshot):
    if not snapshot or any(c not in '0123456789abcdef' for c in snapshot):
        raise ValueError('Use an exact snapshot ID, never an ambiguous latest selector')
    target = STATE / 'restores' / (snapshot + '-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S'))
    target.mkdir(parents=True, exist_ok=False, mode=0o700)
    restic('restore', snapshot, '--verify', '--target', str(target))
    result = verify(target / str(STAGE).lstrip('/'))
    result.update(snapshot_id=snapshot, restored_at=now(), restored_to=str(target))
    atomic_json(STATE / 'restore-status.json', result)
    print(json.dumps(result))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['run', 'restore-check', 'recover-services'])
    parser.add_argument('--snapshot')
    args = parser.parse_args()
    if os.geteuid() != 0: raise SystemExit('Run under the root-owned backup service')
    os.umask(0o077)
    def interrupted(signum, frame): raise InterruptedError('Backup interrupted')
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    if args.action == 'run': run_backup()
    elif args.action == 'restore-check': restore_check(args.snapshot)
    else: recover_services()


if __name__ == '__main__': main()
