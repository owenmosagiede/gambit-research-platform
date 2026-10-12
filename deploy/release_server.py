#!/usr/bin/env python3
"""Explicit, idle-only code deployment. Never installs data or registry changes.

Installed with release_bundle.py in /opt/gambit/release-control, independently
of the application. Plan is read-only. Apply requires the reviewed plan hash.
"""
from contextlib import ExitStack
from datetime import datetime, timezone
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from release_bundle import verify, sha, canonical

ROOT = Path('/srv/gambit/research_platform')
STATE = Path('/var/lib/gambit-releases')
BACKUP = Path('/var/lib/gambit-backup')
UNITS = ('gambit-web.service', 'gambit-worker.service')
LOCKS = ('research-worker-service', 'research-executor', 'research-writer')
CODE_DIRS = {'src', 'ui', 'tools', 'specs', 'docs'}


def safe_target(root, name):
    path = root/name
    if (any(p.is_symlink() for p in (path, *path.parents) if p.is_relative_to(root))
            or not path.resolve().is_relative_to(root.resolve())):
        raise ValueError('Unsafe live path: '+name)
    return path


def plan(root, manifest, files):
    changes = []; blocked = []
    for row in manifest['files']:
        name = row['path']; folder = name.split('/')[0]; target = safe_target(root, name)
        old = sha(target.read_bytes()) if target.is_file() else None
        if old == row['sha256']: continue
        if folder in CODE_DIRS:
            changes.append({'path': name, 'before': old, 'after': row['sha256']})
        elif folder in {'definitions', 'config'} or name.startswith('requirements-'):
            blocked.append({'path': name, 'reason': 'Requires an explicit registry/configuration/runtime migration'})
        # Tests, documentation for operators, and service installers may travel
        # in the artifact but are never implicitly installed as service changes.
    expected = set(files)
    for directory in CODE_DIRS:
        for p in (root/directory).rglob('*'):
            if not p.is_file() or '__pycache__' in p.parts or p.name == '.DS_Store': continue
            name = p.relative_to(root).as_posix()
            if name not in expected:
                blocked.append({'path': name, 'reason': 'Removal requires a separately reviewed migration'})
    result = {'schema': 'gambit_code_deployment_plan_v1', 'commit': manifest['commit'],
              'changes': sorted(changes, key=lambda x:x['path']), 'blockers': sorted(blocked, key=lambda x:x['path']),
              'data_touched': False}
    result['plan_sha256'] = sha(canonical(result))
    return result


def atomic(path, data, mode=0o640, gid=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix='.release-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as out:
            out.write(data); out.flush(); os.fsync(out.fileno())
        os.chmod(temp, mode)
        if gid is not None: os.chown(temp, 0, gid)
        os.replace(temp, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try: os.fsync(directory)
        finally: os.close(directory)
    finally:
        if os.path.exists(temp): os.unlink(temp)


class Machine:
    def __init__(self, root=ROOT, state=STATE, backup=BACKUP):
        self.root, self.state, self.backup = root, state, backup

    def queue(self):
        sys.path.insert(0, str(self.root/'src'))
        from runtime.research_jobs import ResearchJobs, ACTIVE
        jobs = ResearchJobs(self.root)
        names = {p.stem for p in (self.root/'storage/catalog/submissions').glob('*.json')}
        names.update(p.stem for p in (self.root/'storage/catalog/operations/jobs').glob('*.json'))
        active = []
        for rid in sorted(names):
            # Validate immutable intent/event history directly. No projection
            # repair, quarantine writes, or recursive research-writer lock.
            if jobs._incident_path(jobs._submission_path(rid)).exists():
                raise RuntimeError('Resolve queue integrity issues before deployment')
            job = jobs._read_job(rid)
            if job is None: raise RuntimeError('Submission has no authoritative job event')
            if job['status'] in ACTIVE: active.append(rid)
        return active

    def idle(self):
        if self.queue(): raise RuntimeError('Queued or running research exists; no code was changed')

    def backup_ready(self):
        record = json.loads((self.backup/'status.json').read_text())
        age = time.time()-datetime.fromisoformat(record['finished_at']).timestamp()
        if record['status'] != 'succeeded' or not record.get('snapshot_id') or not 0 <= age <= 36*3600:
            raise RuntimeError('A successful backup within 36 hours is required')

    def status(self, unit):
        return subprocess.check_output(['systemctl', 'show', unit, '--property=ActiveState', '--value'], text=True).strip()

    def stop(self, unit):
        subprocess.run(['systemctl', 'stop', unit], check=True)

    def start(self, unit):
        subprocess.run(['systemctl', 'start', unit], check=True)

    def health(self):
        subprocess.run(['systemctl', 'start', 'gambit-health.service'], check=True)
        deadline = time.monotonic()+45
        while time.monotonic() < deadline:
            if all(self.status(u) == 'active' for u in UNITS):
                result = subprocess.run(['curl', '--fail', '--silent', '--max-time', '5',
                    'https://gambitsystems.xyz/healthz'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                if result.returncode == 0: return
            time.sleep(1)
            subprocess.run(['systemctl', 'start', 'gambit-health.service'], check=True)
        raise RuntimeError('Application health check failed')

    def write(self, path, data):
        import grp
        gid = grp.getgrnam('gambit').gr_gid
        missing = []; parent = path.parent
        while not parent.exists(): missing.append(parent); parent = parent.parent
        for p in reversed(missing): p.mkdir(mode=0o750); os.chown(p, 0, gid)
        atomic(path, data, gid=gid)


def guard(stack, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    stream = stack.enter_context(path.open('a+b'))
    try: fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError: raise RuntimeError('An operation already owns '+path.name)


def stop_idle(machine):
    machine.idle()
    if any(machine.status(u) != 'active' for u in UNITS):
        raise RuntimeError('Both services must be healthy before a normal release')
    # Close the Submit race: stop web, then check the authoritative queue again.
    machine.stop(UNITS[0])
    try:
        machine.idle()
        machine.stop(UNITS[1])
    except BaseException:
        machine.start(UNITS[0]); raise


def restart(machine):
    machine.start(UNITS[1]); machine.start(UNITS[0])


def restore(machine, folder, record):
    for row in reversed(record['changes']):
        path = safe_target(machine.root, row['path'])
        # Repeated recovery is safe; unrelated edits must never be overwritten.
        actual = sha(path.read_bytes()) if path.exists() else None
        if actual not in (row['before'], row['after']):
            raise RuntimeError('Rollback found unexpected live bytes: '+row['path'])
        if row['before'] is None:
            if path.exists(): path.unlink()  # only a release-created code file
        else:
            data = (folder/'before'/row['path']).read_bytes()
            if sha(data) != row['before']: raise RuntimeError('Rollback copy checksum mismatch')
            machine.write(path, data)


def apply(machine, manifest, files, expected_plan):
    machine.state.mkdir(parents=True, exist_ok=True)
    with ExitStack() as outer:
        guard(outer, machine.state/'control.lock'); guard(outer, machine.backup/'backup.lock')
        unfinished = [p for p in machine.state.glob('*/receipt.json')
                      if json.loads(p.read_text()).get('status') in {'installing', 'rollback_required'}]
        if unfinished: raise RuntimeError('Recover the unfinished release before another deployment')
        proposal = plan(machine.root, manifest, files)
        if proposal['plan_sha256'] != expected_plan: raise RuntimeError('The reviewed plan changed')
        if proposal['blockers']: raise RuntimeError('Deployment plan has migration blockers')
        if not proposal['changes']: return dict(proposal, status='already_installed')
        machine.backup_ready(); stop_idle(machine)
        release_id = manifest['commit']+'-'+uuid.uuid4().hex[:12]
        folder = machine.state/release_id
        receipt = dict(proposal, release_id=release_id, status='installing', started_at=datetime.now(timezone.utc).isoformat())
        can_restart = True
        try:
            with ExitStack() as locks:
                for name in LOCKS: guard(locks, machine.root/'storage/catalog/operations'/(name+'.lock'))
                machine.idle()
                if plan(machine.root, manifest, files) != proposal: raise RuntimeError('Live code changed after preflight')
                folder.mkdir(exist_ok=False)
                for row in proposal['changes']:
                    if row['before'] is not None:
                        p = folder/'before'/row['path']; p.parent.mkdir(parents=True, exist_ok=True)
                        data = safe_target(machine.root, row['path']).read_bytes()
                        if sha(data) != row['before']: raise RuntimeError('Code changed during rollback copy')
                        atomic(p, data, mode=0o600)
                atomic(folder/'receipt.json', canonical(receipt), mode=0o600)
                can_restart = False
                try:
                    for row in proposal['changes']:
                        machine.write(safe_target(machine.root, row['path']), files[row['path']])
                    for row in proposal['changes']:
                        if sha((machine.root/row['path']).read_bytes()) != row['after']:
                            raise RuntimeError('Post-install checksum mismatch')
                except BaseException:
                    try:
                        restore(machine, folder, receipt)
                        receipt['status'] = 'rolled_back'; can_restart = True
                    except BaseException:
                        receipt['status'] = 'rollback_required'
                        atomic(folder/'receipt.json', canonical(receipt), mode=0o600)
                        raise
                    atomic(folder/'receipt.json', canonical(receipt), mode=0o600)
                    raise
                can_restart = True
            # Worker is started first. Web is restored only after the idle code
            # transaction has completed; user submissions cannot see half a release.
            restart(machine)
            try: machine.health()
            except BaseException:
                # A new job must never be interrupted by automatic rollback.
                if machine.queue():
                    receipt['status'] = 'rollback_required'
                    atomic(folder/'receipt.json', canonical(receipt), mode=0o600)
                    raise RuntimeError('Health failed; new research exists. Rollback deferred safely')
                stop_idle(machine)
                can_restart = False
                with ExitStack() as locks:
                    for name in LOCKS: guard(locks, machine.root/'storage/catalog/operations'/(name+'.lock'))
                    restore(machine, folder, receipt)
                can_restart = True
                restart(machine); machine.health()
                receipt['status'] = 'rolled_back'
                atomic(folder/'receipt.json', canonical(receipt), mode=0o600)
                raise RuntimeError('Release health failed; previous code restored')
            receipt['status'] = 'succeeded'; receipt['finished_at'] = datetime.now(timezone.utc).isoformat()
            atomic(folder/'receipt.json', canonical(receipt), mode=0o600)
            return receipt
        finally:
            # Never terminate a worker or alter research records in cleanup.
            if can_restart:
                if all(machine.status(u) == 'inactive' for u in UNITS): restart(machine)
                elif machine.status(UNITS[0]) == 'inactive' and machine.status(UNITS[1]) == 'active': machine.start(UNITS[0])


def rollback(machine, release_id):
    if '/' in release_id or '..' in release_id: raise ValueError('Invalid release ID')
    folder = machine.state/release_id
    with ExitStack() as outer:
        guard(outer, machine.state/'control.lock'); guard(outer, machine.backup/'backup.lock')
        record = json.loads((folder/'receipt.json').read_text())
        machine.backup_ready(); machine.idle()
        states = [machine.status(u) for u in UNITS]
        if states == ['active', 'active']: stop_idle(machine)
        elif states != ['inactive', 'inactive']: raise RuntimeError('Inspect partial service state before recovery')
        try:
            with ExitStack() as locks:
                for name in LOCKS: guard(locks, machine.root/'storage/catalog/operations'/(name+'.lock'))
                machine.idle(); restore(machine, folder, record)
            restart(machine); machine.health()
            record['status'] = 'rolled_back'; atomic(folder/'receipt.json', canonical(record), mode=0o600)
            return record
        except BaseException:
            record['status'] = 'rollback_required'; atomic(folder/'receipt.json', canonical(record), mode=0o600)
            raise


def main():
    p = argparse.ArgumentParser(); p.add_argument('action', choices=['plan', 'apply', 'rollback'])
    p.add_argument('--archive', type=Path); p.add_argument('--sha256'); p.add_argument('--plan-sha256'); p.add_argument('--release-id')
    a = p.parse_args()
    if os.geteuid() != 0 or sys.platform != 'linux' or not ROOT.parent.is_mount():
        raise SystemExit('Run on the mounted Gambit cloud host as an authorized operator')
    machine = Machine()
    if a.action == 'rollback': result = rollback(machine, a.release_id)
    else:
        if not a.archive or not a.sha256: p.error('archive and sha256 are required')
        manifest, files = verify(a.archive, a.sha256)
        result = plan(ROOT, manifest, files) if a.action == 'plan' else apply(machine, manifest, files, a.plan_sha256)
        if a.action == 'plan':
            result['active_requests'] = machine.queue()
    print(json.dumps(result, indent=2))


if __name__ == '__main__': main()
