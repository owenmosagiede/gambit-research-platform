#!/usr/bin/env python3
"""Separately installed migration runner and out-of-process recovery handler.

Run only with an explicitly reviewed attempt.json. This module does not stage
new scientific records or create approvals. Recovery never rolls back data.
"""
import argparse
from contextlib import ExitStack
from datetime import datetime,timezone
import hashlib,json,os
from pathlib import Path
import subprocess,sys,time
sys.path.insert(0,'/opt/gambit/release-control')
from release_server import Machine,guard,atomic,canonical,restart,stop_idle,UNITS

WORKER='gambit-fx-migration.service'


def stamp():return datetime.now(timezone.utc).isoformat()
def save(folder,phase,**fields):
    atomic(folder/'status.json',canonical(dict(phase=phase,at=stamp(),**fields)),mode=0o600)
def read(path):return json.loads(path.read_text())


def code_files(root):
    return {p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
        for area in ('src','tools') for p in (root/area).rglob('*')
        if p.is_file() and '__pycache__' not in p.parts and p.name!='.DS_Store'}


class MigrationMachine(Machine):
    def health(self):
        deadline=time.monotonic()+45
        while time.monotonic()<deadline:
            subprocess.run(['systemctl','start','gambit-health.service'],check=True)
            if all(self.status(u)=='active' for u in UNITS):
                r=subprocess.run(['curl','--fail','--silent','--max-time','5','https://gambitsystems.xyz/healthz'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                if r.returncode==0:return
            time.sleep(min(10,max(0,deadline-time.monotonic())))
        raise RuntimeError('Application health check failed')
    def worker_dead(self):
        values=subprocess.check_output(['systemctl','show',WORKER,'--property=MainPID,ActiveState'],text=True)
        state=dict(line.split('=',1) for line in values.splitlines())
        return state['MainPID']=='0' and state['ActiveState'] in ('inactive','failed')
    def child(self,folder,action):
        args=['/opt/gambit/venv/bin/python','-B',str(self.root/'tools/migrate_fx_currency.py'),'--root',str(self.root),action]
        if action=='resume-plan':args+=['--release',str(folder/'release.json'),'--request',str(folder/'request.json'),'--output',str(folder/'manifest.json')]
        else:
            args+=['--manifest',str(folder/'manifest.json')]
            if action=='apply':args+=['--expected-sha256',read(folder/'approval.json')['sha256']]
            if action!='verify':args+=['--output',str(folder/(action+'-result.json'))]
        if action=='verify':args=['runuser','-u','gambit','--',*args]
        with (folder/(action+'.log')).open('ab',buffering=0) as log:
            subprocess.run(args,stdout=log,stderr=log,check=True)
        if action=='verify':atomic(folder/'verify-result.json',canonical(read(folder/'verify.log')),mode=0o600)
    def scope_commitment(self):
        sys.path.insert(0,str(self.root/'src'))
        from data.scopes import list_scopes,PAIR_IDS,UNIVERSES
        result=list_scopes(self.root)
        if result['issues'] or {s['id'] for s in result['scopes']}!=set(PAIR_IDS)|{r[0] for r in UNIVERSES}:
            raise RuntimeError('Legacy registry is not intact')
        return {s['id']:{'reference':s['reference'],'membership':s['membership_snapshot']} for s in result['scopes']}
    def markers(self):
        base=self.root/'storage/catalog/operations/fx_currency_migration'
        return any(p.exists() for p in [base/'in_progress.json',base/'completed.json',self.root/'storage/catalog/fx_currency/active.json'])
    def pin_code(self,expected):
        if code_files(self.root)!=expected:raise RuntimeError('Migration code differs from reviewed attempt')
    def readable_manifest(self,folder):
        import grp
        gid=grp.getgrnam('gambit').gr_gid
        # Only operational attempt files, never broad production permissions.
        os.chown(folder,0,gid);os.chmod(folder,0o750)
        p=folder/'manifest.json';os.chown(p,0,gid);os.chmod(p,0o640)
    def replacement_permissions(self,folder):
        import grp,pwd
        uid=pwd.getpwnam('gambit').pw_uid;gid=grp.getgrnam('gambit').gr_gid
        names=set(read(folder/'manifest.json')['replace'])|{'storage/catalog/fx_currency/active.json','storage/catalog/operations/fx_currency_migration/completed.json','storage/catalog/operations/fx_currency_migration/manifest.json'}
        for name in names:
            p=self.root/name
            if p.is_symlink() or not p.resolve().is_relative_to(self.root.resolve()):raise RuntimeError('Unsafe replacement')
            os.chown(p,uid,gid);os.chmod(p,0o640)
            parent=p.parent
            if parent.name=='fx_currency_migration':os.chown(parent,uid,gid);os.chmod(parent,0o750)


def recover(machine,folder):
    """Called by a separate unit after OOM/SIGKILL, and at boot before intake."""
    if not (folder/'status.json').exists():
        if (folder.parent/'maintenance').exists():raise RuntimeError('Maintenance gate exists without a recovery receipt')
        return
    state=read(folder/'status.json')
    if state['phase'] in ('completed','restored'):return
    if not machine.worker_dead():raise RuntimeError('Migration worker still exists')
    with ExitStack() as stack:
        guard(stack,machine.state/'control.lock');guard(stack,machine.backup/'backup.lock')
        # Actual durable mutation evidence takes precedence over a stale phase.
        if machine.markers():
            atomic(folder.parent/'maintenance',b'migration recovery required\n',mode=0o600)
            for unit in UNITS:machine.stop(unit)
            save(folder,'recovery_required',reason='Apply may have started; preserve the exact manifest and keep intake stopped.')
            return
        if 'scopes' not in state:raise RuntimeError('Missing pre-maintenance registry commitment')
        if machine.scope_commitment()!=state['scopes']:raise RuntimeError('Registry changed; automatic restart refused')
        machine.idle()
        (folder.parent/'maintenance').unlink(missing_ok=True)
        restart(machine);machine.health()
        save(folder,'restored',scopes=state['scopes'],previous_phase=state['phase'],health_passed=True,migration_complete=False)


def run(machine,folder):
    request=read(folder/'attempt.json')
    if (folder/'status.json').exists():raise RuntimeError('Use a new attempt directory; never overwrite recovery evidence')
    if (folder/'approval.json').exists():raise RuntimeError('Approval must bind the newly computed plan')
    timeout=request.get('review_timeout_seconds',3600)
    if not 1<=timeout<=3600:raise ValueError('Review timeout must be at most one hour')
    scopes=None
    with ExitStack() as stack:
        guard(stack,machine.state/'control.lock');guard(stack,machine.backup/'backup.lock')
        machine.pin_code(request['code_sha256']);machine.backup_ready();machine.idle()
        if machine.markers():raise RuntimeError('Existing migration requires explicit recovery')
        scopes=machine.scope_commitment()
        save(folder,'stopping',scopes=scopes)
        atomic(folder.parent/'maintenance',b'migration in progress\n',mode=0o600)
        # No exception-only recovery: systemd launches recover even if this
        # entire worker cgroup is killed. Durable state precedes service stops.
        stop_idle(machine)
        save(folder,'planning',scopes=scopes)
        machine.child(folder,'resume-plan')
        sys.path.insert(0,str(machine.root/'src'))
        from data.fx_migration_manifest import manifest_digest
        proposal=read(folder/'manifest.json')
        sha=proposal['sha256']
        if proposal['blockers'] or manifest_digest({k:v for k,v in proposal.items() if k!='sha256'})!=sha:
            raise RuntimeError('Blocked or invalid plan')
        del proposal
        machine.readable_manifest(folder)
        save(folder,'awaiting_review',scopes=scopes,sha256=sha)
        deadline=time.monotonic()+timeout
        while not (folder/'approval.json').exists():
            if time.monotonic()>=deadline:raise TimeoutError('Plan review expired')
            time.sleep(2)
        if read(folder/'approval.json')!={'sha256':sha}:raise RuntimeError('Approval differs from computed plan')
        machine.pin_code(request['code_sha256']);machine.backup_ready();machine.idle()
        save(folder,'applying',scopes=scopes,sha256=sha)
        machine.child(folder,'apply')
        machine.replacement_permissions(folder)
        save(folder,'verifying',scopes=scopes,sha256=sha)
        machine.child(folder,'verify')
        save(folder,'restarting',scopes=scopes,sha256=sha)
        (folder.parent/'maintenance').unlink(missing_ok=True)
        restart(machine);machine.health()
        save(folder,'completed',sha256=sha,health_passed=True,migration_complete=True)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('run','recover'));p.add_argument('--attempt',type=Path,required=True)
    a=p.parse_args();folder=a.attempt.resolve()
    if not folder.is_relative_to(Path('/var/lib/gambit-fx-migration')):raise ValueError('Attempt must be in dedicated migration state')
    if a.action=='run':run(MigrationMachine(),folder)
    else:recover(MigrationMachine(),folder)

if __name__=='__main__':main()
