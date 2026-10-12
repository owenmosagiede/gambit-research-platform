import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from web.health import healthy

spec = importlib.util.spec_from_file_location('health_cloud', Path(__file__).resolve().parents[1] / 'deploy/health_cloud.py')
monitor = importlib.util.module_from_spec(spec); spec.loader.exec_module(monitor)


class CloudHealthTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'status.json'
    def test_public_projection_rejects_stale_missing_invalid_and_future(self):
        self.assertFalse(healthy(self.path, now=200))
        for value in ({}, {'healthy': True, 'checked_at': 0}, {'healthy': True, 'checked_at': 300},
                      {'healthy': False, 'checked_at': 190}, {'healthy': 'true', 'checked_at': 190}):
            self.path.write_text(json.dumps(value)); self.assertFalse(healthy(self.path, now=200))
        self.path.write_text('invalid'); self.assertFalse(healthy(self.path, now=200))
        self.path.write_text(json.dumps({'healthy': True, 'checked_at': 190, 'checks': {'private': 'never returned'}}))
        self.assertTrue(healthy(self.path, now=200))
    def test_checks_fail_closed_for_missing_or_failed_backup_and_worker(self):
        def run(**kwargs):
            return monitor.checks(Path(self.temp.name), self.path, now=3600,
                worker=kwargs.get('worker', {'healthy': True}), mounted=kwargs.get('mounted', True),
                disk=lambda p: SimpleNamespace(free=kwargs.get('free', 10 * 1024 ** 3)))
        self.assertFalse(run()['backup'])
        self.path.write_text(json.dumps({'status': 'succeeded', 'finished_at': '1970-01-01T00:00:00+00:00'}))
        self.assertTrue(all(run().values()))
        self.assertFalse(run(worker={'healthy': False})['worker'])
        self.assertFalse(run(mounted=False)['volume'])
        self.assertFalse(run(free=10)['capacity'])
        self.path.write_text(json.dumps({'status': 'failed', 'finished_at': '1970-01-01T00:59:00+00:00'}))
        self.assertFalse(run()['backup'])
    def test_backup_age_and_in_progress_grace_are_bounded(self):
        for status, now, expected in [('succeeded', 129600, True), ('succeeded', 129601, False),
                                      ('uploading', 21600, True), ('uploading', 21601, False),
                                      ('staging', -1, False)]:
            self.path.write_text(json.dumps({'status': status, 'finished_at': '1970-01-01T00:00:00+00:00',
                                             'started_at': '1970-01-01T00:00:00+00:00'}))
            result = monitor.checks(Path(self.temp.name), self.path, now=now, worker={'healthy': True},
                mounted=True, disk=lambda p: SimpleNamespace(free=10 * 1024 ** 3))
            self.assertEqual(result['backup'], expected)
        self.path.write_text(json.dumps({'status': 'staging', 'started_at': '1970-01-01T00:00:00+00:00'}))
        result = monitor.checks(Path(self.temp.name), self.path, now=5, worker={'healthy': True},
            mounted=True, disk=lambda p: SimpleNamespace(free=10 * 1024 ** 3))
        self.assertTrue(result['backup'])
