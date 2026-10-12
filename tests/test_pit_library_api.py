"""Read-only PIT library/API checks using isolated published-package copies.

No provider requests or credentials are used. Every mutation, HTTP request and
server instance targets a temporary research_platform, never the real store.
"""
from contextlib import contextmanager
import hashlib
import http.client
import json
from pathlib import Path
import shutil
import tempfile
import threading
import unittest

from api import pit_library
from data.alfred_pit import snapshot_path


ROOT = Path(__file__).resolve().parents[1]
FULL_COMPLETIONS = 'storage/catalog/pit_store/full_history/completions'
PILOT_COMPLETIONS = 'storage/catalog/pit_store/completions'


def copy_file(source, destination, relative):
    relative = Path(relative)
    path = (source / relative).resolve()
    if relative.is_absolute() or not path.is_relative_to(source.resolve()):
        raise ValueError('Fixture path leaves the published platform')
    target = destination / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(path, target)


def collect_published_fixture(source, destination):
    """Copy only the surviving full-history package, never the retired sample."""
    completions = list((source / FULL_COMPLETIONS).glob('SNAPSHOT_*.json'))
    if len(completions) != 1:
        raise AssertionError('Expected exactly one published full-history fixture')
    full_path = completions[0]
    full = json.loads(full_path.read_text())
    run = json.loads((source / full['run_path']).read_text())
    paths = {str(full_path.relative_to(source)), full['run_path']}
    paths.update(run['record_paths'])
    paths.update(run['payload_paths'])
    paths.update(['specs/schemas/platform.schema.json', 'specs/schemas/onboarding.schema.json',
                  'specs/schemas/alfred_pit_rows.schema.json',
                  'ui/index.html', 'ui/library.css', 'ui/library.js'])
    for relative in sorted(paths):
        copy_file(source, destination, relative)
    return full


def inventory(root):
    return {path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in root.rglob('*') if path.is_file()}


@contextmanager
def running_server(root):
    server = pit_library.make_server(root, host='127.0.0.1', port=0)
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': 0.01}, daemon=True)
    thread.start()
    try:
        yield server.server_address
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
        if thread.is_alive():
            raise AssertionError('PIT library server did not stop')


def request(address, path, method='GET', headers=None):
    connection = http.client.HTTPConnection(*address, timeout=10)
    try:
        connection.request(method, path, headers=headers or {})
        response = connection.getresponse()
        return response.status, dict(response.getheaders()), response.read()
    finally:
        connection.close()


class PitLibraryApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture_temp = tempfile.TemporaryDirectory(prefix='pit_library_fixture_', dir='/private/tmp')
        cls.addClassCleanup(cls.fixture_temp.cleanup)
        cls.fixture = Path(cls.fixture_temp.name) / 'research_platform'
        cls.fixture.mkdir()
        cls.full = collect_published_fixture(ROOT, cls.fixture)

    def setUp(self):
        self.case = tempfile.TemporaryDirectory(prefix='pit_library_case_', dir='/private/tmp')
        self.addCleanup(self.case.cleanup)
        self.root = Path(self.case.name) / 'research_platform'
        shutil.copytree(self.fixture, self.root)
        self.assertNotEqual(self.root.resolve(), ROOT.resolve())

    def snapshots(self, response):
        return [snapshot for dataset in response['datasets'] for snapshot in dataset['snapshots']]

    def test_lists_only_verified_surviving_full_history(self):
        response = pit_library.list_pit_library(self.root)
        self.assertEqual(response['schema_version'], '1.0.0')
        self.assertEqual(response['dataset_count'], 1)
        self.assertEqual(response['snapshot_count'], 1)
        self.assertEqual(response['issues'], [])
        dataset = response['datasets'][0]
        self.assertEqual(dataset['series_id'], 'CES0500000003')
        for field in ['id', 'name', 'provider', 'frequency', 'units']:
            self.assertTrue(dataset[field])
        self.assertEqual(len(dataset['snapshots']), 1)
        full = dataset['snapshots'][0]
        self.assertEqual(full['scope'], 'full_history')
        self.assertEqual((full['observation_count'], full['event_count']), (247, 1587))
        self.assertEqual(full['id'], self.full['pit_snapshot']['id'])
        self.assertEqual((full['observation_start'], full['observation_end']), ('2006-03-01', '2026-09-01'))
        self.assertEqual((full['vintage_start'], full['vintage_end']), ('2011-03-04', '2026-10-02'))
        self.assertEqual(full['source_view_version'], '2.0.0')
        self.assertEqual(full['timing_precision'], 'date')
        self.assertTrue(full['label'])
        self.assertTrue(full['captured_at'].endswith('Z'))

    def test_raw_and_uncompleted_pit_are_not_ready_library_entries(self):
        for folder in [FULL_COMPLETIONS, PILOT_COMPLETIONS]:
            for path in (self.root / folder).glob('*.json'):
                path.unlink()
        # All definitions, raw packages and PIT payloads still exist. Publication
        # completion, rather than the mere presence of files, controls discovery.
        response = pit_library.list_pit_library(self.root)
        self.assertEqual(response['datasets'], [])
        self.assertEqual(response['dataset_count'], 0)
        self.assertEqual(response['snapshot_count'], 0)
        self.assertEqual(response['issues'], [])

    def test_missing_full_completion_has_no_retired_sample_fallback(self):
        (self.root / FULL_COMPLETIONS / (self.full['pit_snapshot']['id'] + '.json')).unlink()
        response = pit_library.list_pit_library(self.root)
        self.assertEqual(response['dataset_count'], 0)
        self.assertEqual(response['snapshot_count'], 0)
        self.assertEqual(self.snapshots(response), [])
        self.assertEqual(response['issues'], [])

    def test_corrupted_completed_payload_is_reported_and_never_ready(self):
        snapshot = json.loads((self.root / snapshot_path(self.full['pit_snapshot']['id'])).read_text())
        member = snapshot['members'][0]
        digest = member['blob_sha256']
        payload = self.root / f"storage/payloads/sha256/{digest[:2]}/{digest}.{member['format']}"
        payload.write_bytes(payload.read_bytes() + b' ')
        response = pit_library.list_pit_library(self.root)
        self.assertTrue(response['issues'])
        self.assertEqual(response['snapshot_count'], 0)
        self.assertEqual(self.snapshots(response), [])

    def test_duplicate_completion_cannot_duplicate_a_published_snapshot(self):
        existing = self.root / FULL_COMPLETIONS / (self.full['pit_snapshot']['id'] + '.json')
        duplicate = existing.with_name('SNAPSHOT_' + '0' * 64 + '.json')
        shutil.copyfile(existing, duplicate)
        response = pit_library.list_pit_library(self.root)
        snapshots = self.snapshots(response)
        self.assertEqual(len(snapshots), 1)
        self.assertEqual(len({value['id'] for value in snapshots}), 1)
        self.assertTrue(response['issues'])

    def test_malformed_completion_cannot_hide_other_verified_snapshots(self):
        path = self.root / FULL_COMPLETIONS / ('SNAPSHOT_' + 'f' * 64 + '.json')
        path.write_text('{"status":')
        response = pit_library.list_pit_library(self.root)
        self.assertEqual(response['snapshot_count'], 1)
        self.assertEqual(response['dataset_count'], 1)
        self.assertTrue(response['issues'])

    def test_catalog_is_read_only_and_does_not_require_sqlite_indexes(self):
        self.assertEqual(list(self.root.rglob('*.sqlite')), [])
        before = inventory(self.root)
        first = pit_library.list_pit_library(self.root)
        self.assertEqual(pit_library.list_pit_library(self.root), first)
        self.assertEqual(first['snapshot_count'], 1)
        self.assertEqual(inventory(self.root), before)

    def test_http_catalog_matches_verified_catalog_and_disables_cache(self):
        expected = pit_library.list_pit_library(self.root)
        before = inventory(self.root)
        with running_server(self.root) as address:
            status, headers, body = request(address, '/api/pit-library')
        self.assertEqual(status, 200)
        self.assertTrue(headers['Content-Type'].startswith('application/json'))
        self.assertIn('no-store', headers['Cache-Control'])
        self.assertEqual(headers['X-Content-Type-Options'], 'nosniff')
        self.assertEqual(json.loads(body), expected)
        self.assertEqual(inventory(self.root), before)

    def test_allowlisted_ui_has_expected_bytes_and_media_types(self):
        with running_server(self.root) as address:
            cases = [('/', 'index.html', 'text/html'), ('/index.html', 'index.html', 'text/html'),
                     ('/library.css', 'library.css', 'text/css'),
                     ('/library.js', 'library.js', 'javascript')]
            for path, filename, media in cases:
                with self.subTest(path=path):
                    status, headers, body = request(address, path)
                    self.assertEqual(status, 200)
                    self.assertIn(media, headers['Content-Type'])
                    self.assertIn('no-cache', headers['Cache-Control'])
                    self.assertEqual(headers['X-Content-Type-Options'], 'nosniff')
                    self.assertEqual(body, (self.root / 'ui' / filename).read_bytes())

    def test_arbitrary_files_and_encoded_traversal_are_json_not_found(self):
        (self.root / '.env.local').write_text('SYNTHETIC_SECRET=DO_NOT_SERVE')
        (self.root.parent / 'outside.txt').write_text('OUTSIDE_SENTINEL')
        paths = ['/.env.local', '/' + self.full['run_path'],
                 '/specs/schemas/platform.schema.json', '/../outside.txt', '/%2e%2e/outside.txt',
                 '/ui/../.env.local', '/ui/%2e%2e/.env.local', '/%252e%252e/outside.txt',
                 '/api/pit-library/../../.env.local', '/api/not-a-route']
        before = inventory(self.root)
        with running_server(self.root) as address:
            for path in paths:
                with self.subTest(path=path):
                    status, headers, body = request(address, path)
                    self.assertEqual(status, 404)
                    self.assertTrue(headers['Content-Type'].startswith('application/json'))
                    self.assertIsInstance(json.loads(body), dict)
                    self.assertNotIn(b'DO_NOT_SERVE', body)
                    self.assertNotIn(b'OUTSIDE_SENTINEL', body)
                    self.assertNotIn(str(self.root).encode(), body)
        self.assertEqual(inventory(self.root), before)

    def test_mutating_methods_are_json_method_not_allowed_without_writes(self):
        before = inventory(self.root)
        with running_server(self.root) as address:
            for method in ['POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS', 'TRACE', 'CONNECT']:
                with self.subTest(method=method):
                    status, headers, body = request(address, '/api/pit-library', method)
                    self.assertEqual(status, 405)
                    self.assertTrue(headers['Content-Type'].startswith('application/json'))
                    self.assertEqual(headers['Allow'], 'GET, HEAD')
                    self.assertIsInstance(json.loads(body), dict)
        self.assertEqual(inventory(self.root), before)

    def test_server_restricts_loopback_binding_host_and_origin(self):
        for host in ['0.0.0.0', '::', 'localhost', '192.0.2.1']:
            with self.subTest(host=host), self.assertRaises(ValueError):
                pit_library.make_server(self.root, host=host, port=0)
        with running_server(self.root) as address:
            for headers in [{'Host': 'attacker.invalid'}, {'Origin': 'https://attacker.invalid'}]:
                with self.subTest(headers=headers):
                    status, response_headers, body = request(address, '/api/pit-library', headers=headers)
                    self.assertEqual(status, 403)
                    self.assertTrue(response_headers['Content-Type'].startswith('application/json'))
                    self.assertIsInstance(json.loads(body), dict)
            status, _, body = request(address, '/api/pit-library', headers={'Host': f'localhost:{address[1]}'})
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(body)['snapshot_count'], 1)

    def test_unexpected_query_parameters_are_rejected(self):
        with running_server(self.root) as address:
            status, headers, body = request(address, '/api/pit-library?root=/private/tmp')
        self.assertEqual(status, 400)
        self.assertTrue(headers['Content-Type'].startswith('application/json'))
        self.assertIsInstance(json.loads(body), dict)


if __name__ == '__main__':
    unittest.main()
