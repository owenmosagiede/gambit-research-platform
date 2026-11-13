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
UNITS = ('gambit-worker.service', 'gambit-web.service')
LOCKS = ('research-worker-service', 'research-executor', 'research-writer')


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
        raise RuntimeError('File changed while copying: ' + str(path))
    return value.hexdigest(), after.st_size


def omitted(path):
    # Runtime ownership must be re-established on recovery, never restored stale.
    return (any(p in {'__pycache__', '.git', '.venv', 'venv'} for p in path.parts)
            or path.suffix == '.pyc'
            or (path.parts[0] == 'storage' and path.suffix == '.lock')
            or path.name in {'worker_service.json', '.DS_Store'})


def copy_tree(source, destination):
    source = Path(source)
    if source.is_symlink() or not source.is_dir():
        raise RuntimeError('Backup source must be an ordinary directory: ' + str(source))
    destination.mkdir(parents=True, exist_ok=False, mode=0o700)
    for path in sorted(source.rglob('*')):
        relative = path.relative_to(source)
        if omitted(relative): continue
        if path.is_symlink(): raise RuntimeError('Backup refuses symlinks: ' + str(path))
        target = destination / relative
        if path.is_dir():
            target.mkdir(exist_ok=True, mode=path.stat().st_mode & 0o777)
        elif path.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            before = digest(path)
            shutil.copy2(path, target)
            if digest(target) != before or digest(path) != before:
                raise RuntimeError('Backup copy mismatch: ' + str(path))
        else:
            raise RuntimeError('Backup refuses special files: ' + str(path))


def sqlite_checks(root):
    checked = []
    for path in sorted(root.rglob('*')):
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
    return checked


def seal(root):
    checked = sqlite_checks(root)
    entries = []
    for path in sorted(root.rglob('*')):
        if path.is_symlink(): raise RuntimeError('Symlink in staged backup')
        if not path.is_file() or path == root / 'backup-manifest.json': continue
        sha, size = digest(path)
        entries.append({'path': path.relative_to(root).as_posix(), 'sha256': sha, 'bytes': size})
    value = {'schema': 'gambit_backup_v1', 'created_at': now(), 'consistency': 'worker_drained_web_stopped_writer_locks_held',
             'file_count': len(entries), 'bytes': sum(x['bytes'] for x in entries),
             'sqlite_checked': checked, 'entries': entries}
    atomic_json(root / 'backup-manifest.json', value)
    return value


def verify(root):
    root = Path(root).resolve()
    value = json.loads((root / 'backup-manifest.json').read_text())
    if any(p.is_symlink() for p in root.rglob('*')):
        raise RuntimeError('Symlink in restored backup')
    seen = set()
    for entry in value['entries']:
        relative = Path(entry['path']); path = root / relative
        if (relative.is_absolute() or '..' in relative.parts or path.is_symlink()
                or not path.resolve().is_relative_to(root) or entry['path'] in seen):
            raise RuntimeError('Unsafe or duplicate backup manifest path')
        seen.add(entry['path'])
        if digest(path) != (entry['sha256'], entry['bytes']):
            raise RuntimeError('Restored byte mismatch: ' + entry['path'])
    actual = {p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file() and p != root / 'backup-manifest.json'}
    if actual != seen or len(seen) != value['file_count']:
        raise RuntimeError('Restored file inventory mismatch')
    if sqlite_checks(root) != value['sqlite_checked']:
        raise RuntimeError('Restored SQLite inventory mismatch')
    return {'files_verified': len(seen), 'bytes_verified': value['bytes'], 'sqlite_checked': value['sqlite_checked']}


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


def stage(sources, destination, services):
    root = sources['research_platform']
    with quiescent(root, services):
        destination.mkdir(parents=True, exist_ok=False, mode=0o700)
        for label, source in sources.items():
            if Path(label).name != label: raise RuntimeError('Unsafe backup label')
            copy_tree(source, destination / label)
    # The protected staging tree contains the checked bytes from the drained
    # services. Sealing and SQLite integrity checks read only that copy.
    return seal(destination)


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
            sources = {'research_platform': root, 'auth': VOLUME / 'auth', 'configuration': Path('/etc/gambit')}
            size = sum(p.stat().st_size for source in sources.values() for p in source.rglob('*')
                       if p.is_file() and not p.is_symlink() and not omitted(p.relative_to(source)))
            if shutil.disk_usage(STATE).free < size * 1.1 + 1024 ** 3:
                raise RuntimeError('Insufficient backup staging capacity; services were not stopped')
            manifest = stage(sources, STAGE, Services())
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
