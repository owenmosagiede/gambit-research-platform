from contextlib import contextmanager
import fcntl
import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

spec = importlib.util.spec_from_file_location('backup_cloud', Path(__file__).resolve().parents[1] / 'deploy/backup_cloud.py')
backup = importlib.util.module_from_spec(spec); spec.loader.exec_module(backup)


class FakeServices:
    def __init__(self, active=True):
        self.states = {u: 'active' if active else 'inactive' for u in backup.UNITS}
        self.events = []
    def state(self, unit): return self.states[unit]
    def stop(self, unit): self.events.append(('stop', unit)); self.states[unit] = 'inactive'
    def start(self, unit): self.events.append(('start', unit)); self.states[unit] = 'active'


class CloudBackupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name); self.root = self.base / 'research'; self.root.mkdir()
        (self.root / 'history.json').write_text('{"id":"preserved","status":"queued"}\n')
        self.auth = self.base / 'auth'; self.auth.mkdir()
        db = sqlite3.connect(self.auth / 'auth.sqlite3')
        db.execute('create table owners (username text)'); db.execute("insert into owners values ('fixture-owner')")
        db.commit(); db.close()
        self.sources = {'research_platform': self.root, 'auth': self.auth}
        self.output = self.base / 'staged'

    def test_consistent_copy_preserves_history_and_checks_sqlite(self):
        services = FakeServices()
        manifest = backup.stage(self.sources, self.output, services)
        self.assertEqual(services.events, [('stop', backup.UNITS[0]), ('stop', backup.UNITS[1]), ('start', backup.UNITS[1]), ('start', backup.UNITS[0])])
        self.assertEqual((self.output / 'research_platform/history.json').read_bytes(), (self.root / 'history.json').read_bytes())
        self.assertEqual(manifest['sqlite_checked'], ['auth/auth.sqlite3'])
        self.assertEqual(backup.verify(self.output)['files_verified'], 2)
        self.assertEqual(json.loads((self.output / 'research_platform/history.json').read_text())['status'], 'queued')

    def test_failure_restarts_only_previously_running_services(self):
        (self.root / 'escape').symlink_to(self.auth)
        services = FakeServices(); services.states[backup.UNITS[0]] = 'inactive'
        with self.assertRaisesRegex(RuntimeError, 'symlinks'):
            backup.stage(self.sources, self.output, services)
        self.assertEqual(services.events, [('stop', backup.UNITS[1]), ('start', backup.UNITS[1])])

    def test_held_writer_lock_rejects_copy_and_restores_services(self):
        path = self.root / 'storage/catalog/operations/research-writer.lock'; path.parent.mkdir(parents=True)
        services = FakeServices()
        with path.open('w') as stream:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaisesRegex(RuntimeError, 'Writer still owns'):
                backup.stage(self.sources, self.output, services)
        self.assertFalse(self.output.exists())
        self.assertTrue(all(v == 'active' for v in services.states.values()))

    def test_corruption_extra_files_and_path_escape_rejected(self):
        backup.stage(self.sources, self.output, FakeServices(False))
        file = self.output / 'research_platform/history.json'; original = file.read_bytes(); file.write_bytes(b'changed')
        with self.assertRaisesRegex(RuntimeError, 'byte mismatch'): backup.verify(self.output)
        file.write_bytes(original); extra = self.output / 'unexpected'; extra.write_text('extra')
        with self.assertRaisesRegex(RuntimeError, 'inventory mismatch'): backup.verify(self.output)
        extra.unlink(); path = self.output / 'backup-manifest.json'; value = json.loads(path.read_text())
        value['entries'][0]['path'] = '../outside'; path.write_text(json.dumps(value))
        with self.assertRaisesRegex(RuntimeError, 'Unsafe'): backup.verify(self.output)

    def test_wal_database_retains_committed_rows_and_exact_bytes(self):
        db = sqlite3.connect(self.auth / 'auth.sqlite3')
        try:
            db.execute('pragma journal_mode=wal'); db.execute("insert into owners values ('second')"); db.commit()
            before = {p.name: p.read_bytes() for p in self.auth.iterdir()}
            backup.stage(self.sources, self.output, FakeServices(False))
            self.assertEqual({p.name: p.read_bytes() for p in (self.output / 'auth').iterdir()}, before)
            backup.verify(self.output)
            restored = sqlite3.connect(self.output / 'auth/auth.sqlite3')
            self.assertEqual(restored.execute('select count(*) from owners').fetchone()[0], 2); restored.close()
        finally: db.close()

    def test_service_transition_refused_without_actions(self):
        services = FakeServices(); services.states[backup.UNITS[0]] = 'deactivating'
        with self.assertRaisesRegex(RuntimeError, 'transition'):
            backup.stage(self.sources, self.output, services)
        self.assertEqual(services.events, [])

    def test_dependency_lockfile_preserved_but_runtime_ownership_omitted(self):
        (self.root / 'requirements-cloud.lock').write_text('locked dependencies')
        backup.stage(self.sources, self.output, FakeServices(False))
        self.assertEqual((self.output / 'research_platform/requirements-cloud.lock').read_text(), 'locked dependencies')
        self.assertEqual(list((self.output / 'research_platform').rglob('research-writer.lock')), [])

    def test_recovery_journal_restarts_recorded_services_only(self):
        services = FakeServices(False)
        services.remember = lambda units: backup.atomic_json(self.base / 'services-to-restart.json', {'units': units})
        backup.atomic_json(self.base / 'services-to-restart.json', {'units': [backup.UNITS[1]]})
        with patch.object(backup, 'STATE', self.base), patch.object(backup, 'Services', return_value=services):
            backup.recover_services()
        self.assertEqual(services.events, [('start', backup.UNITS[1])])
        self.assertEqual(json.loads((self.base / 'services-to-restart.json').read_text())['units'], [])

    def test_backup_upload_failure_occurs_after_services_restart(self):
        services = FakeServices()
        backup.stage(self.sources, self.output, services)
        with patch.object(backup.subprocess, 'run', side_effect=RuntimeError('unavailable')):
            with self.assertRaises(RuntimeError): backup.restic('backup', str(self.output))
        self.assertTrue(all(v == 'active' for v in services.states.values()))

    def test_sealing_checks_the_frozen_copy_after_services_restart(self):
        services = FakeServices()
        source = self.root / 'history.json'
        original = source.read_bytes()
        seal = backup.seal

        def verify_copy(destination):
            self.assertTrue(all(v == 'active' for v in services.states.values()))
            source.write_text('{"id":"new-live-record"}\n')
            self.assertEqual((destination / 'research_platform/history.json').read_bytes(), original)
            return seal(destination)

        with patch.object(backup, 'seal', side_effect=verify_copy):
            manifest = backup.stage(self.sources, self.output, services)
        self.assertEqual(manifest['sqlite_checked'], ['auth/auth.sqlite3'])
        self.assertEqual(backup.verify(self.output)['files_verified'], 2)

    def test_failed_sealing_never_stops_restarted_services(self):
        services = FakeServices()
        with patch.object(backup, 'seal', side_effect=RuntimeError('Invalid staged copy')):
            with self.assertRaisesRegex(RuntimeError, 'Invalid staged copy'):
                backup.stage(self.sources, self.output, services)
        self.assertTrue(all(v == 'active' for v in services.states.values()))
        self.assertFalse((self.output / 'backup-manifest.json').exists())

    def test_low_staging_capacity_fails_before_stopping_services(self):
        volume = self.base / 'volume'; root = volume / 'research_platform'; root.mkdir(parents=True)
        (root / 'migration-manifest.json').write_text('{}')
        services = FakeServices()
        with patch.object(backup, 'VOLUME', volume), patch.object(backup, 'STATE', self.base / 'state'), \
             patch.object(backup, 'STAGE', self.base / 'staging'), \
             patch.object(backup.Path, 'is_mount', return_value=True), \
             patch.object(backup.shutil, 'disk_usage', return_value=SimpleNamespace(free=0)), \
             patch.object(backup, 'Services', return_value=services):
            with self.assertRaisesRegex(RuntimeError, 'staging capacity'): backup.run_backup()
        self.assertEqual(services.events, [])
        self.assertEqual(json.loads((self.base / 'state/status.json').read_text())['status'], 'failed')
