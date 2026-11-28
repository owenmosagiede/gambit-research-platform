from contextlib import contextmanager
import fcntl
import importlib.util
import json
import io
import os
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import time
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
        self.assertEqual(services.events, [])  # Unsafe input fails during online precopy.

    def test_held_writer_lock_rejects_copy_and_restores_services(self):
        path = self.root / 'storage/catalog/operations/research-writer.lock'; path.parent.mkdir(parents=True)
        services = FakeServices()
        with path.open('w') as stream:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaisesRegex(RuntimeError, 'Writer still owns'):
                backup.stage(self.sources, self.output, services)
        self.assertFalse((self.output / 'backup-manifest.json').exists())
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

    def test_low_staging_capacity_fails_before_stopping_services(self):
        volume = self.base / 'volume'; root = volume / 'research_platform'; root.mkdir(parents=True)
        (root / 'migration-manifest.json').write_text('{}')
        (volume / 'auth').mkdir(); configuration = self.base / 'configuration'; configuration.mkdir()
        services = FakeServices()
        with patch.object(backup, 'VOLUME', volume), patch.object(backup, 'STATE', self.base / 'state'), \
             patch.object(backup, 'STAGE', self.base / 'staging'), \
             patch.object(backup, 'CONFIGURATION', configuration), \
             patch.object(backup.Path, 'is_mount', return_value=True), \
             patch.object(backup.shutil, 'disk_usage', return_value=SimpleNamespace(free=0)), \
             patch.object(backup, 'Services', return_value=services):
            with self.assertRaisesRegex(RuntimeError, 'staging capacity'): backup.run_backup()
        self.assertEqual(services.events, [])
        self.assertEqual(json.loads((self.base / 'state/status.json').read_text())['status'], 'failed')

    def test_online_precopy_reconciles_additions_changes_deletions_and_renames(self):
        (self.root / 'deleted').write_text('remove me')
        (self.root / 'renamed').write_text('rename me')
        services = FakeServices()
        original_stop = services.stop
        def change_before_freeze(unit):
            if unit == backup.UNITS[0]:
                (self.root / 'history.json').write_text('new committed version')
                (self.root / 'deleted').unlink()
                (self.root / 'renamed').rename(self.root / 'new-name')
                (self.root / 'added').write_text('new file')
            original_stop(unit)
        services.stop = change_before_freeze
        backup.stage(self.sources, self.output, services)
        actual = {p.name: p.read_bytes() for p in (self.output / 'research_platform').iterdir() if p.is_file()}
        expected = {p.name: p.read_bytes() for p in self.root.iterdir() if p.is_file()}
        self.assertEqual(actual, expected)
        backup.verify(self.output)

    def test_reconciliation_detects_same_size_change_with_restored_mtime(self):
        path = self.root / 'history.json'; old = path.stat()
        services = FakeServices(); stop = services.stop
        def change(unit):
            if unit == backup.UNITS[0]:
                path.write_bytes(b'x' * old.st_size)
                os.utime(path, ns=(old.st_atime_ns, old.st_mtime_ns))
            stop(unit)
        services.stop = change
        backup.stage(self.sources, self.output, services)
        self.assertEqual((self.output / 'research_platform/history.json').read_bytes(), path.read_bytes())

    def test_file_and_directory_type_changes_during_precopy(self):
        (self.root / 'file-to-dir').write_text('old')
        (self.root / 'dir-to-file').mkdir()
        (self.root / 'dir-to-file/old').write_text('old child')
        services = FakeServices(); stop = services.stop
        def change(unit):
            if unit == backup.UNITS[0]:
                (self.root / 'file-to-dir').unlink()
                (self.root / 'file-to-dir').mkdir()
                (self.root / 'file-to-dir/new').write_text('new child')
                (self.root / 'dir-to-file/old').unlink()
                (self.root / 'dir-to-file').rmdir()
                (self.root / 'dir-to-file').write_text('new file')
            stop(unit)
        services.stop = change
        backup.stage(self.sources, self.output, services)
        self.assertEqual((self.output / 'research_platform/file-to-dir/new').read_text(), 'new child')
        self.assertEqual((self.output / 'research_platform/dir-to-file').read_text(), 'new file')
        backup.verify(self.output)

    def test_database_and_mapped_sidecars_are_recopied_even_with_unchanged_stat_signature(self):
        original_signature = backup.signature
        for name in ['mapped.sqlite-shm', 'mapped.sqlite-wal', 'mapped.sqlite', 'mapped.db']:
            with self.subTest(name=name), tempfile.TemporaryDirectory(dir=self.base) as temp:
                source = Path(temp) / 'source'; source.mkdir()
                path = source / name; path.write_bytes(b'old mapping bytes')
                fixed = original_signature(path)
                services = FakeServices(); stop = services.stop
                def change(unit):
                    if unit == backup.UNITS[0]: path.write_bytes(b'new mapping bytes')
                    stop(unit)
                services.stop = change
                with patch.object(backup, 'signature', side_effect=lambda p: fixed if p == path else original_signature(p)):
                    target = Path(temp) / 'copy'
                    backup.stage({'research_platform': source}, target, services)
                self.assertEqual((target / 'research_platform' / name).read_bytes(), b'new mapping bytes')
                backup.verify(target)

    def test_sqlite_wal_changes_during_online_precopy_are_reconciled(self):
        db = sqlite3.connect(self.auth / 'auth.sqlite3')
        try:
            db.execute('pragma journal_mode=wal')
            services = FakeServices(); stop = services.stop
            def change(unit):
                if unit == backup.UNITS[0]:
                    db.execute("insert into owners values ('committed while online')"); db.commit()
                stop(unit)
            services.stop = change
            backup.stage(self.sources, self.output, services)
            restored = sqlite3.connect(self.output / 'auth/auth.sqlite3')
            try: self.assertEqual(restored.execute('select count(*) from owners').fetchone()[0], 2)
            finally: restored.close()
        finally: db.close()

    def test_heavy_verification_happens_after_restart_and_failure_keeps_services_up(self):
        services = FakeServices()
        def failed_check(root):
            self.assertTrue(all(state == 'active' for state in services.states.values()))
            raise RuntimeError('fixture integrity failure')
        with patch.object(backup, 'sqlite_checks', side_effect=failed_check):
            with self.assertRaisesRegex(RuntimeError, 'fixture integrity failure'):
                backup.stage(self.sources, self.output, services)
        self.assertTrue(all(state == 'active' for state in services.states.values()))
        self.assertFalse((self.output / 'backup-manifest.json').exists())

    def test_corrupted_precopy_is_never_sealed_as_success(self):
        services = FakeServices(); stop = services.stop
        def corrupt(unit):
            if unit == backup.UNITS[0]:
                (self.output / 'research_platform/history.json').write_text('corrupt')
            stop(unit)
        services.stop = corrupt
        with self.assertRaisesRegex(RuntimeError, 'changed after verified copy'):
            backup.stage(self.sources, self.output, services)
        self.assertTrue(all(state == 'active' for state in services.states.values()))
        self.assertFalse((self.output / 'backup-manifest.json').exists())

    def test_stopped_copy_timeout_restores_services_without_sealing(self):
        services = FakeServices(); original_copy = backup.copy_tree; deadline = backup.copy_deadline
        def slow_copy(*args, **kwargs):
            if kwargs.get('reconcile'): time.sleep(.1)
            return original_copy(*args, **kwargs)
        with patch.object(backup, 'copy_deadline', side_effect=lambda: deadline(.02)), \
             patch.object(backup, 'copy_tree', side_effect=slow_copy):
            with self.assertRaises(TimeoutError): backup.stage(self.sources, self.output, services)
        self.assertTrue(all(state == 'active' for state in services.states.values()))
        self.assertFalse((self.output / 'backup-manifest.json').exists())

    def test_streamed_manifest_is_legacy_v1_compatible_and_summary_does_not_retain_rows(self):
        summary = backup.stage(self.sources, self.output, FakeServices(False))
        value = json.loads((self.output / 'backup-manifest.json').read_text())
        self.assertEqual(value['schema'], 'gambit_backup_v1')
        self.assertNotIn('entries', summary)
        self.assertEqual(summary['file_count'], len(value['entries']))
        # The old json.dump(sort_keys=True) encoding remains readable too.
        (self.output / 'backup-manifest.json').write_text(json.dumps(value, sort_keys=True, indent=2))
        self.assertEqual(backup.verify(self.output)['files_verified'], len(value['entries']))

    def test_streaming_parser_handles_chunk_boundaries_and_rejects_truncated_or_duplicate_paths(self):
        backup.stage(self.sources, self.output, FakeServices(False))
        value = json.loads((self.output / 'backup-manifest.json').read_text())
        class TinyReader(io.StringIO):
            def read(self, size=-1): return super().read(min(size, 7))
        meta = {}
        self.assertEqual(list(backup.manifest_entries(TinyReader(json.dumps(value)), meta)), value['entries'])
        self.assertEqual(meta['file_count'], value['file_count'])
        with self.assertRaisesRegex(RuntimeError, 'Malformed'):
            list(backup.manifest_entries(TinyReader(json.dumps(value)[:-3]), {}))
        value['entries'].append(value['entries'][0])
        (self.output / 'backup-manifest.json').write_text(json.dumps(value))
        with self.assertRaisesRegex(RuntimeError, 'duplicate'):
            backup.verify(self.output)

    def test_progress_distinguishes_online_copy_paused_reconciliation_and_online_verification(self):
        services = FakeServices(); phases = []
        def progress(phase): phases.append((phase, dict(services.states)))
        backup.stage(self.sources, self.output, services, progress)
        self.assertEqual([p[0] for p in phases], ['precopy_services_online', 'quiescent_reconciliation', 'verifying_staged_copy_services_online'])
        self.assertTrue(all(state == 'active' for state in phases[0][1].values()))
        self.assertTrue(all(state == 'inactive' for state in phases[1][1].values()))
        self.assertTrue(all(state == 'active' for state in phases[2][1].values()))

    def run_backup_fixture(self, operator):
        volume = self.base / 'volume'; root = volume / 'research_platform'; root.mkdir(parents=True)
        (root / 'migration-manifest.json').write_text('{}')
        (root / 'history.json').write_text('immutable fixture history')
        (volume / 'auth').mkdir(); configuration = self.base / 'configuration'; configuration.mkdir()
        services = FakeServices(); state = self.base / 'state'
        with patch.object(backup, 'VOLUME', volume), patch.object(backup, 'STATE', state), \
             patch.object(backup, 'STAGE', self.base / 'staging'), patch.object(backup, 'CONFIGURATION', configuration), \
             patch.object(backup.Path, 'is_mount', return_value=True), patch.object(backup, 'Services', return_value=services), \
             patch.object(backup, 'restic', side_effect=lambda *args: operator(args, services, state)):
            backup.run_backup()
        return json.loads((state / 'status.json').read_text()), services

    def test_full_backup_cleans_only_stale_locks_and_finishes_after_retention_and_check(self):
        commands = []; phases = []
        def operator(args, services, state):
            commands.append(args)
            phases.append(json.loads((state / 'status.json').read_text())['phase'])
            self.assertTrue(all(value == 'active' for value in services.states.values()))
            if args[0] == 'backup': return json.dumps({'message_type': 'summary', 'snapshot_id': 'a' * 64}) + '\n'
            return ''
        status, services = self.run_backup_fixture(operator)
        self.assertEqual([args[0] for args in commands], ['unlock', 'backup', 'forget', 'check'])
        self.assertEqual(commands[0], ('unlock',))
        self.assertFalse(any('--remove-all' in args for args in commands))
        self.assertEqual(phases, ['unlocking_stale_repository_locks', 'encrypted_upload', 'retention', 'repository_integrity_check'])
        self.assertEqual(status['status'], 'succeeded')
        self.assertEqual(status['phase'], 'complete')
        self.assertEqual(status['snapshot_id'], 'a' * 64)

    def test_retention_failure_preserves_uploaded_snapshot_without_claiming_success(self):
        def operator(args, services, state):
            if args[0] == 'backup': return json.dumps({'message_type': 'summary', 'snapshot_id': 'b' * 64}) + '\n'
            if args[0] == 'forget': raise RuntimeError('fixture retention failure')
            return ''
        with self.assertRaisesRegex(RuntimeError, 'fixture retention failure'):
            self.run_backup_fixture(operator)
        status = json.loads((self.base / 'state/status.json').read_text())
        self.assertEqual(status['status'], 'failed')
        self.assertEqual(status['phase'], 'retention')
        self.assertEqual(status['uploaded_snapshot_id'], 'b' * 64)
        self.assertNotIn('snapshot_id', status)

    def test_repository_failure_happens_before_services_stop(self):
        observed = []
        def operator(args, services, state):
            observed.extend(services.events)
            raise RuntimeError('fixture repository unavailable')
        with self.assertRaisesRegex(RuntimeError, 'fixture repository unavailable'):
            self.run_backup_fixture(operator)
        self.assertEqual(observed, [])
        self.assertFalse((self.base / 'staging').exists())
        self.assertEqual(json.loads((self.base / 'state/status.json').read_text())['status'], 'failed')

    def test_restic_failure_details_are_retained_in_private_diagnostics(self):
        error = subprocess.CalledProcessError(1, ['restic', 'forget'], output='fixture output', stderr='fixture detail')
        with patch.object(backup, 'STATE', self.base), patch.object(backup.subprocess, 'run', side_effect=error):
            with self.assertRaises(subprocess.CalledProcessError): backup.restic('forget')
        path = self.base / 'last-restic-failure.json'; detail = json.loads(path.read_text())
        self.assertEqual(detail['command'], 'forget')
        self.assertEqual(detail['exit_code'], 1)
        self.assertEqual(detail['stderr'], 'fixture detail')
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
