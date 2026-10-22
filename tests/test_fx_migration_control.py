"""Recovery survives worker death; no production services are used."""
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT/'deploy'))
spec=importlib.util.spec_from_file_location('migration_control',PROJECT/'deploy/fx_migration_control.py')
control=importlib.util.module_from_spec(spec);spec.loader.exec_module(control)

class FakeMachine:
    def __init__(self,base):
        self.root=base/'root';self.state=base/'releases';self.backup=base/'backup'
        for p in (self.root,self.state,self.backup):p.mkdir(exist_ok=True,parents=True)
        self.live=dict.fromkeys(control.UNITS,'active');self.events=[];self.dead=True;self.mutated=False;self.scopes={'EURUSD':'original'};self.busy=False;self.bad_health=False
    def worker_dead(self):return self.dead
    def scope_commitment(self):return self.scopes
    def markers(self):return self.mutated
    def idle(self):
        if self.busy:raise RuntimeError('Active research')
    def status(self,u):return self.live[u]
    def stop(self,u):self.events.append(('stop',u));self.live[u]='inactive'
    def start(self,u):self.events.append(('start',u));self.live[u]='active'
    def health(self):
        if self.bad_health:raise RuntimeError('Health failed')
    def pin_code(self,expected):
        if expected!={'code':'pinned'}:raise RuntimeError('Code differs')
    def backup_ready(self):pass
    def readable_manifest(self,folder):pass
    def replacement_permissions(self,folder):pass

class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.base=Path(self.temp.name)
        self.folder=self.base/'attempt';self.folder.mkdir();self.m=FakeMachine(self.base)
        control.save(self.folder,'planning',scopes=self.m.scopes)
        (self.base/'maintenance').write_text('maintenance')
        self.m.live=dict.fromkeys(control.UNITS,'inactive')
    def status(self):return json.loads((self.folder/'status.json').read_text())
    def test_preapply_death_restores_and_is_idempotent(self):
        control.recover(self.m,self.folder)
        self.assertEqual(self.status()['phase'],'restored');self.assertFalse((self.base/'maintenance').exists())
        self.assertTrue(all(v=='active' for v in self.m.live.values()))
        events=list(self.m.events);control.recover(self.m,self.folder);self.assertEqual(events,self.m.events)
    def test_actual_sigkill_skips_worker_cleanup_but_external_recovery_runs(self):
        code='import os,signal;os.kill(os.getpid(),signal.SIGKILL)'
        result=subprocess.run([sys.executable,'-c',code])
        self.assertEqual(result.returncode,-signal.SIGKILL)
        control.recover(self.m,self.folder);self.assertEqual(self.status()['phase'],'restored')
    def test_memory_exhaustion_receipt_does_not_require_child_exception_handler(self):
        # Exact durable state left by a cgroup OOM kill: stale planning phase,
        # dead worker, no Python finally/exception receipt.
        control.recover(self.m,self.folder);self.assertEqual(self.status()['previous_phase'],'planning')
    def test_live_worker_or_changed_registry_never_restarts(self):
        self.m.dead=False
        with self.assertRaises(RuntimeError):control.recover(self.m,self.folder)
        self.m.dead=True;self.m.scopes={'EURUSD':'changed'}
        with self.assertRaises(RuntimeError):control.recover(self.m,self.folder)
        self.assertEqual(self.m.events,[]);self.assertTrue((self.base/'maintenance').exists())
    def test_marker_takes_precedence_over_stale_preapply_phase(self):
        self.m.mutated=True
        control.recover(self.m,self.folder)
        self.assertEqual(self.status()['phase'],'recovery_required')
        self.assertTrue((self.base/'maintenance').exists())
        self.assertFalse(any(action=='start' for action,u in self.m.events))
    def test_health_failure_is_not_reported_as_recovery_success(self):
        self.m.bad_health=True
        with self.assertRaisesRegex(RuntimeError,'Health'):control.recover(self.m,self.folder)
        self.assertNotEqual(self.status()['phase'],'restored')
    def test_recovery_lock_conflict_prevents_restart(self):
        from contextlib import ExitStack
        with ExitStack() as stack:
            control.guard(stack,self.m.state/'control.lock')
            with self.assertRaises(RuntimeError):control.recover(self.m,self.folder)
        self.assertEqual(self.m.events,[])
    def test_systemd_recovery_is_outside_worker_cgroup_and_boot_is_gated(self):
        unit=(PROJECT/'deploy/systemd/gambit-fx-migration.service').read_text()
        self.assertIn('OnFailure=gambit-fx-migration-recovery.service',unit)
        self.assertIn('MemoryMax=2G',unit);self.assertIn('MemorySwapMax=0',unit)
        recovery=(PROJECT/'deploy/systemd/gambit-fx-migration-recovery.service').read_text()
        self.assertIn('WantedBy=multi-user.target',recovery)
        for name in control.UNITS:
            gate=(PROJECT/'deploy/systemd'/f'{name}.d/migration.conf').read_text()
            self.assertIn('ConditionPathExists=!/var/lib/gambit-fx-migration/maintenance',gate)

class RunnerTests(unittest.TestCase):
    def test_resume_uses_saved_release_and_requires_fresh_exact_plan_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp);folder=base/'attempt';folder.mkdir();m=FakeMachine(base)
            (folder/'attempt.json').write_text(json.dumps({'code_sha256':{'code':'pinned'},'review_timeout_seconds':1}))
            def child(folder,action):
                self.assertEqual(action,'resume-plan')
                from data.fx_migration_manifest import manifest_digest
                proposal={'blockers':[],'release':{'id':'synthetic'}};proposal['sha256']=manifest_digest(proposal)
                (folder/'manifest.json').write_text(json.dumps(proposal))
            m.child=child
            with patch.object(control.time,'sleep'),patch.object(control.time,'monotonic',side_effect=[0,2]):
                with self.assertRaises(TimeoutError):control.run(m,folder)
            self.assertEqual(json.loads((folder/'status.json').read_text())['phase'],'awaiting_review')
            control.recover(m,folder)
            self.assertEqual(json.loads((folder/'status.json').read_text())['phase'],'restored')
